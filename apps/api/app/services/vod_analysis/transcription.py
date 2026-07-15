import os
import re
from pathlib import Path
from typing import Any

from ...config import Settings


def should_probe(audio: dict[str, Any], settings: Settings) -> tuple[bool, str | None]:
    if audio["voice_ratio"] < settings.vod_analysis_probe_voice_ratio:
        return False, "voice_ratio_below_threshold"
    if audio["longest_speech_run"] < settings.vod_analysis_probe_min_speech_seconds:
        return False, "speech_run_too_short"
    return True, None


def repeated_text_ratio(text: str) -> float:
    words = re.findall(r"\w+", text.lower())
    if len(words) < 4:
        return 0.0
    trigrams = [tuple(words[index : index + 3]) for index in range(len(words) - 2)]
    return 1.0 - len(set(trigrams)) / len(trigrams) if trigrams else 0.0


class ProbeTranscriber:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._model = None

    def _load(self):
        if self._model is not None:
            return self._model
        model_root = self.settings.data_dir / "models"
        os.environ.setdefault("HF_HOME", str(model_root / "huggingface"))
        os.environ.setdefault("XDG_CACHE_HOME", str(model_root / "cache"))
        os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
        try:
            import ctranslate2
            from faster_whisper import WhisperModel
        except ImportError as exc:
            raise RuntimeError("Probe transcription failed: faster-whisper is unavailable") from exc
        device = self.settings.whisper_device
        if device == "auto":
            device = "cuda" if ctranslate2.get_cuda_device_count() > 0 else "cpu"
        compute = self.settings.whisper_compute_type
        if compute == "auto":
            compute = "float16" if device == "cuda" else "int8"
        self._model = WhisperModel(
            self.settings.vod_analysis_probe_model,
            device=device,
            compute_type=compute,
            download_root=str(model_root),
        )
        return self._model

    def transcribe(self, sample: Path, duration: float) -> dict[str, Any]:
        model = self._load()
        try:
            segments, info = model.transcribe(
                str(sample),
                language="es",
                beam_size=1,
                best_of=1,
                temperature=0,
                condition_on_previous_text=False,
                vad_filter=False,
                word_timestamps=False,
            )
            values = list(segments)
        except Exception as exc:
            raise RuntimeError(f"Probe transcription failed: {exc}") from exc
        text = " ".join(item.text.strip() for item in values if item.text.strip()).strip()
        word_count = len(re.findall(r"\w+", text))
        avg_logprob = sum(item.avg_logprob for item in values) / len(values) if values else None
        no_speech = sum(item.no_speech_prob for item in values) / len(values) if values else None
        repetition = repeated_text_ratio(text)
        logprob_quality = min(1.0, max(0.0, 1.0 + (avg_logprob or -1.0)))
        no_speech_quality = 1.0 - (no_speech if no_speech is not None else 1.0)
        density_quality = min(1.0, word_count / max(1.0, duration * 1.5))
        quality = max(
            0.0,
            min(
                1.0,
                0.4 * logprob_quality + 0.3 * no_speech_quality + 0.3 * density_quality - repetition * 0.4,
            ),
        )
        return {
            "attempted": True,
            "text": text,
            "word_count": word_count,
            "words_per_second": word_count / duration if duration else 0.0,
            "avg_logprob": avg_logprob,
            "no_speech_probability": no_speech,
            "language": getattr(info, "language", "es"),
            "repeated_text_ratio": repetition,
            "transcript_quality_score": quality,
            "skip_reason": None,
        }
