from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import time
from typing import Any

from ...config import Settings
from ...database import VodAnalysisStore
from .cache import SourceIdentity
from .fixtures import illojuan_fixture
from .metadata import inspect_analysis_metadata, stream_access_from_metadata
from .topic_audio import chunk_ranges, extract_analysis_audio, extract_audio_chunk
from .topic_cache import cache_directory, copy_artifact, topic_cache_keys, write_json_atomic
from .topic_candidates import build_candidate_outputs
from .topic_semantic import LocalEmbeddingAnalyzer, detect_topic_blocks, semantic_windows
from .topic_transcription import AnalysisTranscriber, clean_transcript, merge_chunk_transcripts
from .visual_analyzer import VisualVodAnalysisAnalyzer

logger = logging.getLogger(__name__)


class VodAnalysisAnalyzer:
    """Dispatch Automatic Analysis to transcript topics and legacy/Inspector jobs to vision."""

    def __init__(self, store: VodAnalysisStore, settings: Settings):
        self.store = store
        self.settings = settings

    def process(self, job_id: str) -> None:
        job = self.store.get(job_id)
        if job is None:
            return
        strategy = job.get("phase_detection_strategy")
        if strategy != "transcript_topics":
            VisualVodAnalysisAnalyzer(self.store, self.settings).process(job_id)
            return
        try:
            self._process_fixture(job) if job["fixture_mode"] else self._process_real(job)
        except Exception as exc:
            logger.exception("Topic analysis %s failed", job_id)
            self.store.update(job_id, status="failed", stage="failed", error_message=str(exc)[:1000])

    def _update(self, job_id: str, stage: str, progress: int, **values: Any) -> None:
        self.store.update(
            job_id,
            status="processing",
            stage=stage,
            progress=min(99, max(0, progress)),
            error_message=None,
            **values,
        )

    def _process_fixture(self, job: dict[str, Any]) -> None:
        legacy = illojuan_fixture(
            job["source_url"],
            job["source_platform"],
            job["source_vod_id"],
            self.settings.vod_topic_analysis_pipeline_version,
        )
        job_dir = self.settings.data_dir / "analysis" / job["id"]
        job_dir.mkdir(parents=True, exist_ok=True)
        for stage, progress in (
            ("reading_metadata", 5),
            ("extracting_audio", 15),
            ("transcribing_audio", 45),
            ("cleaning_transcript", 55),
            ("creating_semantic_windows", 65),
            ("detecting_topics", 78),
            ("building_candidates", 88),
            ("ranking_candidates", 96),
        ):
            self._update(job["id"], stage, progress)
        segments = _fixture_transcript()
        clean, warnings = clean_transcript(segments)
        topics = legacy["topics"]
        candidates = legacy["candidates"]
        metadata = {
            "platform": job["source_platform"],
            "extractor": "fixture",
            "vod_id": job["source_vod_id"],
            "title": "Fixture editorial de IlloJuan",
            "uploader": "IlloJuan",
            "channel": "IlloJuan",
            "duration_seconds": 7200,
            "chapters": [],
            "original_url": job["source_url"],
            "availability": "public",
            "audio_formats": [],
            "video_formats": [],
        }
        artifacts = {
            "metadata.json": metadata,
            "transcript_raw.json": {"segments": segments},
            "transcript_clean.json": {"segments": clean, "warnings": warnings},
            "semantic_windows.json": [],
            "topic_blocks.json": topics,
            "candidates.json": candidates,
        }
        for name, value in artifacts.items():
            write_json_atomic(job_dir / name, value)
        result = {
            "pipeline_version": self.settings.vod_topic_analysis_pipeline_version,
            "fixture": True,
            "analysis_strategy": "transcript_topics",
            "phase_detection_strategy": "not_required",
            "requires_coarse_timeline": False,
            "vod": metadata,
            "transcription": {
                "duration_seconds": 7200,
                "language": "es",
                "model": self.settings.whisper_analysis_model,
                "segment_count": len(clean),
                "chunk_count": 4,
            },
            "topics": topics,
            "candidates": candidates,
            "semantic_backend": "fixture-multilingual",
            "cache_keys": {},
            "warnings": warnings,
            "timings": {},
        }
        self.store.update(
            job["id"],
            status="completed",
            stage="completed",
            progress=100,
            completed_windows=4,
            total_windows=4,
            current_timestamp=7200,
            warnings=warnings,
            result=result,
            error_message=None,
        )

    def _process_real(self, job: dict[str, Any]) -> None:
        started = time.monotonic()
        job_id = job["id"]
        identity = SourceIdentity(job["source_platform"], job["source_vod_id"])
        keys = topic_cache_keys(
            identity,
            job["streamer_profile"],
            self.settings,
            source_url=job["source_url"],
        )
        request_cache_key = keys["candidates"]
        previous_result = job.get("result") if isinstance(job.get("result"), dict) else {}
        previous_keys = previous_result.get("cache_keys", {})
        job_dir = self.settings.data_dir / "analysis" / job_id
        job_dir.mkdir(parents=True, exist_ok=True)
        self._update(job_id, "reading_metadata", 3)
        metadata, raw_metadata = inspect_analysis_metadata(job["source_url"], identity, self.settings)
        write_json_atomic(job_dir / "metadata.json", metadata.model_dump(mode="json"))
        duration = min(metadata.duration_seconds, self.settings.vod_topic_analysis_max_seconds)

        audio_dir = cache_directory(self.settings, "audio", keys["audio"])
        audio_path = audio_dir / "analysis_audio.wav"
        cached_metadata_path = audio_dir / "metadata.json"
        if not cached_metadata_path.is_file():
            write_json_atomic(cached_metadata_path, metadata.model_dump(mode="json"))
        previous_audio = cache_directory(
            self.settings, "audio", previous_keys.get("audio", "missing")
        ) / "analysis_audio.wav"
        if not audio_path.is_file() and previous_audio.is_file():
            audio_path.parent.mkdir(parents=True, exist_ok=True)
            os.link(previous_audio, audio_path)
        if not audio_path.is_file():
            self._update(job_id, "extracting_audio", 10)
            access = stream_access_from_metadata(raw_metadata)
            extract_analysis_audio(access, duration, audio_path, self.settings)
        copy_artifact(audio_path, job_dir / "analysis_audio.wav")

        transcript_dir = cache_directory(self.settings, "transcription", keys["transcription"])
        previous_transcript_dir = cache_directory(
            self.settings, "transcription", previous_keys.get("transcription", "missing")
        )
        if not (transcript_dir / "chunks").is_dir() and (previous_transcript_dir / "chunks").is_dir():
            shutil.copytree(previous_transcript_dir / "chunks", transcript_dir / "chunks")
        ranges = chunk_ranges(
            duration, self.settings.transcription_chunk_seconds, self.settings.transcription_overlap_seconds
        )
        transcriber = AnalysisTranscriber(self.settings)
        chunk_values: list[list[dict[str, Any]]] = []
        language = "es"
        for index, (chunk_start, chunk_end) in enumerate(ranges):
            chunk_json = transcript_dir / "chunks" / f"chunk_{index:04d}.json"
            self._update(
                job_id,
                "transcribing_audio",
                20 + round(40 * index / max(1, len(ranges))),
                completed_windows=index,
                total_windows=len(ranges),
                current_timestamp=chunk_start,
            )
            if chunk_json.is_file():
                payload = json.loads(chunk_json.read_text(encoding="utf-8"))
            else:
                temporary = job_dir / "tmp" / f"chunk_{index:04d}.wav"
                extract_audio_chunk(audio_path, chunk_start, chunk_end, temporary, self.settings)
                segments, language = transcriber.transcribe_chunk(temporary, chunk_start)
                payload = {
                    "index": index,
                    "start": chunk_start,
                    "end": chunk_end,
                    "language": language,
                    "segments": segments,
                }
                write_json_atomic(chunk_json, payload)
                temporary.unlink(missing_ok=True)
            language = payload.get("language") or language
            chunk_values.append(payload["segments"])
        raw_segments = merge_chunk_transcripts(chunk_values, self.settings.transcription_overlap_seconds)
        raw_payload = {
            "version": 1,
            "model": self.settings.whisper_analysis_model,
            "language": language,
            "duration_seconds": duration,
            "chunks": len(ranges),
            "segments": raw_segments,
        }
        write_json_atomic(transcript_dir / "transcript_raw.json", raw_payload)
        copy_artifact(transcript_dir / "transcript_raw.json", job_dir / "transcript_raw.json")
        if not raw_segments:
            raise RuntimeError("Empty transcript: Whisper found no usable speech in the selected range")

        self._update(job_id, "cleaning_transcript", 64)
        clean_segments, warnings = clean_transcript(raw_segments)
        if not clean_segments:
            raise RuntimeError("Empty transcript after conservative cleaning")
        clean_payload = {
            **raw_payload,
            "cleaning_version": "transcript-clean-v1",
            "segments": clean_segments,
            "warnings": warnings,
        }
        write_json_atomic(transcript_dir / "transcript_clean.json", clean_payload)
        copy_artifact(transcript_dir / "transcript_clean.json", job_dir / "transcript_clean.json")

        transcript_hash = hashlib.sha256(
            json.dumps(clean_segments, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        keys = topic_cache_keys(
            identity,
            job["streamer_profile"],
            self.settings,
            source_url=job["source_url"],
            transcript_hash=transcript_hash,
        )

        segmentation_dir = cache_directory(self.settings, "segmentation", keys["segmentation"])
        topic_path = segmentation_dir / "topic_blocks.json"
        windows_path = segmentation_dir / "semantic_windows.json"
        semantic = LocalEmbeddingAnalyzer(
            self.settings.semantic_embedding_model,
            str(self.settings.data_dir / "models" / "fastembed"),
        )
        if topic_path.is_file() and windows_path.is_file():
            topics = json.loads(topic_path.read_text(encoding="utf-8"))
            windows = json.loads(windows_path.read_text(encoding="utf-8"))
            backend = windows[0].get("embedding_backend", "cached") if windows else "cached"
            backend_details_path = segmentation_dir / "semantic_backend.json"
            backend_details = (
                json.loads(backend_details_path.read_text(encoding="utf-8"))
                if backend_details_path.is_file()
                else {
                    "requested_backend": self.settings.semantic_embedding_model,
                    "effective_backend": backend,
                    "model_loaded": backend == self.settings.semantic_embedding_model,
                    "fallback_used": backend != self.settings.semantic_embedding_model,
                    "fallback_reason": "legacy_cached_backend_metadata_missing",
                }
            )
        else:
            self._update(job_id, "creating_semantic_windows", 70)
            windows = semantic_windows(clean_segments, self.settings)
            embeddings = semantic.encode([item["text"] for item in windows])
            for item, embedding in zip(windows, embeddings, strict=True):
                item["embedding"] = embedding
                item["embedding_backend"] = semantic.backend
                item.pop("segments", None)
            backend = semantic.backend
            backend_details = semantic.details()
            write_json_atomic(windows_path, windows)
            write_json_atomic(segmentation_dir / "semantic_backend.json", backend_details)
            self._update(job_id, "detecting_topics", 80)
            topics = detect_topic_blocks(windows, self.settings)
            write_json_atomic(topic_path, topics)
        copy_artifact(windows_path, job_dir / "semantic_windows.json")
        copy_artifact(topic_path, job_dir / "topic_blocks.json")

        candidate_dir = cache_directory(self.settings, "candidates", keys["candidates"])
        candidate_path = candidate_dir / "candidates.json"
        self._update(job_id, "building_candidates", 89)
        if candidate_path.is_file():
            candidates = json.loads(candidate_path.read_text(encoding="utf-8"))
        else:
            candidates, rejected = build_candidate_outputs(topics, clean_segments, self.settings)
            write_json_atomic(candidate_path, candidates)
            write_json_atomic(candidate_dir / "rejected_candidates.json", rejected)
            write_json_atomic(
                candidate_dir / "score_breakdowns.json",
                {item["id"]: item["score_breakdown"] for item in candidates},
            )
        rejected_path = candidate_dir / "rejected_candidates.json"
        rejected = json.loads(rejected_path.read_text(encoding="utf-8")) if rejected_path.is_file() else []
        copy_artifact(candidate_path, job_dir / "candidates.json")
        if rejected_path.is_file():
            copy_artifact(rejected_path, job_dir / "rejected_candidates.json")
        score_path = candidate_dir / "score_breakdowns.json"
        if score_path.is_file():
            copy_artifact(score_path, job_dir / "score_breakdowns.json")
        self._update(job_id, "ranking_candidates", 97)
        if not candidates:
            warnings.append("no_candidates_found")
        result = {
            "pipeline_version": self.settings.vod_topic_analysis_pipeline_version,
            "fixture": False,
            "analysis_strategy": "transcript_topics",
            "phase_detection_strategy": "not_required",
            "requires_coarse_timeline": False,
            "vod": metadata.model_dump(mode="json"),
            "transcription": {
                "duration_seconds": duration,
                "language": language,
                "model": self.settings.whisper_analysis_model,
                "segment_count": len(clean_segments),
                "chunk_count": len(ranges),
            },
            "topics": topics,
            "candidates": candidates,
            "semantic_backend": backend,
            "semantic_backend_details": backend_details,
            "cache_keys": keys,
            "timings": {"total_seconds": round(time.monotonic() - started, 3)},
            "warnings": list(dict.fromkeys(warnings)),
        }
        self.store.update(
            job_id,
            status="completed",
            stage="completed",
            progress=100,
            completed_windows=len(ranges),
            total_windows=len(ranges),
            current_timestamp=duration,
            warnings=result["warnings"],
            result=result,
            error_message=None,
            pipeline_version=self.settings.vod_topic_analysis_pipeline_version,
            cache_key=request_cache_key,
        )
        shutil.rmtree(job_dir / "tmp", ignore_errors=True)


def _fixture_transcript() -> list[dict[str, Any]]:
    topics = [
        (870, "Bueno chat, el tema de GTA VI es el precio, Rockstar y lo que espero del lanzamiento."),
        (1800, "Os voy a contar la anécdota del aeropuerto durante mi último viaje, porque fue increíble."),
        (3100, "Cambiando de tema, creo que crear contenido en directo depende mucho de hablar con el chat."),
    ]
    values: list[dict[str, Any]] = []
    for base, text in topics:
        for index in range(12):
            start = base + index * 60
            values.append(
                {
                    "start": start,
                    "end": start + 55,
                    "text": f"{text} Parte {index + 1} de la explicación.",
                    "words": [],
                    "avg_logprob": -0.18,
                    "no_speech_probability": 0.02,
                }
            )
    return values
