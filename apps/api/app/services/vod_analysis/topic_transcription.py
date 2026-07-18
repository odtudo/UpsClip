from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from ...config import Settings


class AnalysisTranscriber:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._model: Any = None

    def _load(self) -> Any:
        if self._model is not None:
            return self._model
        root = self.settings.data_dir / "models"
        os.environ.setdefault("HF_HOME", str(root / "huggingface"))
        os.environ.setdefault("XDG_CACHE_HOME", str(root / "cache"))
        os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
        try:
            import ctranslate2
            from faster_whisper import WhisperModel
        except ImportError as exc:
            raise RuntimeError("Whisper model unavailable: faster-whisper is not installed") from exc
        device = self.settings.whisper_device
        if device == "auto":
            device = "cuda" if ctranslate2.get_cuda_device_count() else "cpu"
        compute = self.settings.whisper_compute_type
        if compute == "auto":
            compute = "float16" if device == "cuda" else "int8"
        self._model = WhisperModel(
            self.settings.whisper_analysis_model,
            device=device,
            compute_type=compute,
            download_root=str(root),
        )
        return self._model

    def transcribe_chunk(self, path: Path, offset: float) -> tuple[list[dict[str, Any]], str]:
        try:
            values, info = self._load().transcribe(
                str(path),
                language="es",
                beam_size=5,
                temperature=0,
                vad_filter=True,
                word_timestamps=True,
                condition_on_previous_text=True,
            )
            segments = []
            for item in values:
                text = item.text.strip()
                if not text:
                    continue
                words = [
                    {
                        "start": offset + float(word.start),
                        "end": offset + float(word.end),
                        "word": word.word,
                        "probability": getattr(word, "probability", None),
                    }
                    for word in (item.words or [])
                    if word.start is not None and word.end is not None
                ]
                segments.append(
                    {
                        "start": offset + float(item.start),
                        "end": offset + float(item.end),
                        "text": text,
                        "words": words,
                        "avg_logprob": float(item.avg_logprob),
                        "no_speech_probability": float(item.no_speech_prob),
                    }
                )
            return segments, str(getattr(info, "language", "es"))
        except RuntimeError:
            raise
        except Exception as exc:
            raise RuntimeError(f"Transcription failed: {exc}") from exc


def _normalized_words(text: str) -> list[str]:
    return re.findall(r"\w+", text.casefold())


def merge_chunk_transcripts(
    chunks: list[list[dict[str, Any]]], overlap_seconds: float
) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    for chunk in chunks:
        for segment in sorted(chunk, key=lambda value: (value["start"], value["end"])):
            duplicate = False
            for previous in reversed(merged[-8:]):
                if previous["end"] < segment["start"] - overlap_seconds:
                    break
                first = set(_normalized_words(previous["text"]))
                second = set(_normalized_words(segment["text"]))
                similarity = len(first & second) / max(1, len(first | second))
                time_overlap = max(
                    0.0, min(previous["end"], segment["end"]) - max(previous["start"], segment["start"])
                )
                if similarity >= 0.72 and time_overlap > 0:
                    duplicate = True
                    if segment.get("avg_logprob", -99) > previous.get("avg_logprob", -99):
                        previous.update(segment)
                    break
            if not duplicate:
                merged.append(segment)
    return sorted(merged, key=lambda value: (value["start"], value["end"]))


def clean_transcript(segments: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[str]]:
    clean: list[dict[str, Any]] = []
    warnings: list[str] = []
    prior_text = ""
    repeated_run = 0
    for source in segments:
        raw = str(source.get("text") or "")
        normalized = re.sub(r"\s+", " ", raw).strip()
        if not normalized:
            continue
        no_speech = float(source.get("no_speech_probability") or 0)
        if no_speech > 0.92 and len(_normalized_words(normalized)) < 5:
            warnings.append("high_no_speech_segment_removed")
            continue
        comparable = " ".join(_normalized_words(normalized))
        repeated_run = repeated_run + 1 if comparable == prior_text else 0
        if repeated_run >= 2:
            warnings.append("repeated_whisper_hallucination_removed")
            continue
        prior_text = comparable
        item = dict(source)
        item["raw_text"] = raw
        item["text"] = normalized
        item["cleaning_flags"] = []
        clean.append(item)
    return clean, list(dict.fromkeys(warnings))
