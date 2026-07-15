import numpy as np

from .audio import SAMPLE_RATE, basic_audio_features

VAD_VERSION = "faster-whisper-silero-v1"


def speech_regions(audio: np.ndarray) -> list[dict[str, int]]:
    try:
        from faster_whisper.vad import VadOptions, get_speech_timestamps

        return get_speech_timestamps(
            audio,
            VadOptions(
                threshold=0.5,
                min_speech_duration_ms=180,
                min_silence_duration_ms=250,
                speech_pad_ms=80,
            ),
            sampling_rate=SAMPLE_RATE,
        )
    except Exception as exc:
        raise RuntimeError(f"VAD failed: {exc}") from exc


def aggregate_speech_features(audio: np.ndarray, regions: list[dict[str, int]]) -> dict:
    duration = audio.size / SAMPLE_RATE
    intervals = sorted(
        (max(0, item["start"]) / SAMPLE_RATE, min(audio.size, item["end"]) / SAMPLE_RATE)
        for item in regions
        if item.get("end", 0) > item.get("start", 0)
    )
    voiced = sum(end - start for start, end in intervals)
    runs = [end - start for start, end in intervals]
    silences: list[float] = []
    cursor = 0.0
    for start, end in intervals:
        silences.append(max(0.0, start - cursor))
        cursor = max(cursor, end)
    silences.append(max(0.0, duration - cursor))
    audio_features = basic_audio_features(audio)
    voice_ratio = min(1.0, voiced / duration) if duration else 0.0
    speech_continuity = min(1.0, (max(runs, default=0.0) / duration) * 1.5) if duration else 0.0
    return {
        "voice_ratio": voice_ratio,
        "voiced_seconds": voiced,
        "longest_speech_run": max(runs, default=0.0),
        "number_of_speech_regions": len(intervals),
        "longest_silence": max(silences, default=duration),
        "speech_start_delay": intervals[0][0] if intervals else None,
        "speech_end_margin": duration - intervals[-1][1] if intervals else None,
        "silence_ratio": max(0.0, 1.0 - voice_ratio),
        "rms_mean": audio_features["rms_mean"],
        "rms_variance": audio_features["rms_variance"],
        "peak_level": audio_features["peak_level"],
        "dynamic_range": audio_features["dynamic_range"],
        "zero_crossing_rate": audio_features["zero_crossing_rate"],
        "spectral_flatness": audio_features["spectral_flatness"],
        "speech_continuity": speech_continuity,
        "music_likelihood_features": {
            "energy_continuity": audio_features["audio_energy_continuity"],
            "spectral_flatness": audio_features["spectral_flatness"],
            "voice_without_turns": voice_ratio * speech_continuity,
        },
    }


def measure_speech(audio: np.ndarray) -> dict:
    return aggregate_speech_features(audio, speech_regions(audio))
