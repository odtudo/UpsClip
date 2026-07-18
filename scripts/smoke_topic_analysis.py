#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

from apps.api.app.config import Settings
from apps.api.app.database import VodAnalysisStore
from apps.api.app.services.vod_analysis.analyzer import VodAnalysisAnalyzer
from apps.api.app.services.vod_analysis.topic_audio import chunk_ranges, extract_audio_chunk
from apps.api.app.services.vod_analysis.topic_cache import write_json_atomic
from apps.api.app.services.vod_analysis.spanish_text import NORMALIZED_SPANISH_STOPWORDS, normalize_text
from apps.api.app.services.vod_analysis.topic_candidates import build_candidate_outputs, build_candidates
from apps.api.app.services.vod_analysis.topic_semantic import (
    LocalEmbeddingAnalyzer,
    detect_topic_blocks,
    semantic_windows,
)
from apps.api.app.services.vod_analysis.topic_transcription import (
    AnalysisTranscriber,
    clean_transcript,
    merge_chunk_transcripts,
)


def fixture_smoke(output: Path) -> None:
    settings = Settings(
        data_dir=output, database_url=f"sqlite:///{output / 'app.db'}", vod_analysis_fixture_mode=True
    )
    settings.ensure_directories()
    store = VodAnalysisStore(settings)
    store.initialize()
    job = store.create(
        {
            "id": "topic-smoke",
            "source_url": "https://www.twitch.tv/videos/123456789",
            "source_platform": "twitch",
            "source_vod_id": "123456789",
            "streamer_profile": "illojuan",
            "pipeline_version": settings.vod_topic_analysis_pipeline_version,
            "cache_key": "fixture",
            "fixture_mode": True,
            "phase_detection_strategy": "transcript_topics",
            "requires_coarse_timeline": False,
        }
    )
    VodAnalysisAnalyzer(store, settings).process(job["id"])
    completed = store.get(job["id"])
    if not completed or completed["status"] != "completed" or not completed["result"]["candidates"]:
        raise RuntimeError(f"Fixture smoke failed: {completed}")
    directory = output / "analysis" / job["id"]
    for name in ("transcript_clean.json", "topic_blocks.json", "candidates.json"):
        if not (directory / name).is_file():
            raise RuntimeError(f"Missing {name}")
    print(
        json.dumps(
            {
                "status": "completed",
                "topics": len(completed["result"]["topics"]),
                "candidates": len(completed["result"]["candidates"]),
                "output": str(directory),
            },
            indent=2,
        )
    )


def audio_smoke(audio: Path, output: Path, maximum: float) -> None:
    settings = Settings(
        transcription_chunk_seconds=max(60, min(1800, int(maximum))),
        transcription_overlap_seconds=5,
    )
    settings.ensure_directories()
    transcriber = AnalysisTranscriber(settings)
    chunks = []
    for index, (start, end) in enumerate(
        chunk_ranges(maximum, settings.transcription_chunk_seconds, settings.transcription_overlap_seconds)
    ):
        path = output / "chunks" / f"{index:04d}.wav"
        extract_audio_chunk(audio, start, end, path, settings)
        values, _ = transcriber.transcribe_chunk(path, start)
        chunks.append(values)
    raw = merge_chunk_transcripts(chunks, settings.transcription_overlap_seconds)
    clean, warnings = clean_transcript(raw)
    windows = semantic_windows(clean, settings)
    analyzer = LocalEmbeddingAnalyzer(
        settings.semantic_embedding_model,
        str(settings.data_dir / "models" / "fastembed"),
    )
    for item, embedding in zip(windows, analyzer.encode([item["text"] for item in windows]), strict=True):
        item["embedding"] = embedding
        item.pop("segments", None)
    topics = detect_topic_blocks(windows, settings)
    candidates = build_candidates(topics, clean, settings)
    write_json_atomic(output / "transcript_clean.json", {"segments": clean, "warnings": warnings})
    write_json_atomic(output / "topic_blocks.json", topics)
    write_json_atomic(output / "candidates.json", candidates)
    print(
        json.dumps(
            {
                "segments": len(clean),
                "topics": len(topics),
                "candidates": len(candidates),
                "semantic_backend": analyzer.backend,
            },
            indent=2,
        )
    )


def real_transcript_smoke(job_dir: Path, output: Path) -> None:
    """Re-score a real cached transcript without downloading media or invoking Whisper."""
    clean_payload = json.loads((job_dir / "transcript_clean.json").read_text(encoding="utf-8"))
    windows = json.loads((job_dir / "semantic_windows.json").read_text(encoding="utf-8"))
    settings = Settings()
    topics = detect_topic_blocks(windows, settings)
    candidates, rejected = build_candidate_outputs(topics, clean_payload["segments"], settings)
    banned = {"sabes", "vale", "esta", "verdad", "entonces", "aqui", "mira"}
    for candidate in candidates:
        normalized_keywords = {normalize_text(value) for value in candidate["keywords"]}
        if normalized_keywords & banned:
            raise RuntimeError(f"Filler keyword escaped quality gate: {normalized_keywords & banned}")
        if candidate["unsupported_terms"] or candidate["grounding_score"] < 0.85:
            raise RuntimeError(f"Ungrounded candidate escaped quality gate: {candidate['id']}")
        if "gta vi" in normalize_text(candidate["title"]) and "gta" not in normalize_text(
            " ".join(candidate["opening_preview"] + candidate["representative_sentences"] + candidate["closing_preview"])
        ):
            raise RuntimeError("Unsupported GTA VI title escaped quality gate")
        if any(normalize_text(term) in NORMALIZED_SPANISH_STOPWORDS for term in candidate["keywords"]):
            raise RuntimeError(f"Stopword keyword escaped quality gate: {candidate['keywords']}")
    write_json_atomic(output / "topic_blocks.json", topics)
    write_json_atomic(output / "candidates.json", candidates)
    write_json_atomic(output / "rejected_candidates.json", rejected)
    print(json.dumps({"real_job": job_dir.name, "topics": len(topics), "accepted": len(candidates), "rejected": len(rejected), "titles": [item["title"] for item in candidates], "output": str(output)}, indent=2, ensure_ascii=False))


def main() -> None:
    parser = argparse.ArgumentParser(description="Smoke-test transcript-first VOD topic analysis")
    parser.add_argument("--audio", type=Path, help="Optional local audio/video file for real Whisper")
    parser.add_argument("--job-dir", type=Path, help="Real completed job artifacts; never downloads or transcribes")
    parser.add_argument("--max-seconds", type=float, default=300)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    output = args.output or Path(tempfile.mkdtemp(prefix="vod-topic-smoke-"))
    output.mkdir(parents=True, exist_ok=True)
    if args.job_dir:
        real_transcript_smoke(args.job_dir.resolve(), output)
    elif args.audio:
        audio_smoke(args.audio.resolve(), output, args.max_seconds)
    else:
        fixture_smoke(output)


if __name__ == "__main__":
    main()
