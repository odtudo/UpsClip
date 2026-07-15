import wave
from pathlib import Path

import numpy as np

from ...config import Settings
from ..process import run_command

SAMPLE_RATE = 16000


def extract_audio_sample(
    stream_url: str,
    start: float,
    duration: float,
    destination: Path,
    settings: Settings,
    *,
    user_agent: str | None = None,
    referer: str | None = None,
) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    input_options: list[str] = []
    if user_agent:
        input_options.extend(["-user_agent", user_agent])
    if referer:
        input_options.extend(["-referer", referer])
    run_command(
        [
            settings.ffmpeg_path,
            "-y",
            "-ss",
            f"{start:.3f}",
            *input_options,
            "-i",
            stream_url,
            "-t",
            f"{duration:.3f}",
            "-vn",
            "-ac",
            "1",
            "-ar",
            str(SAMPLE_RATE),
            "-c:a",
            "pcm_s16le",
            destination,
        ],
        label="Coarse audio sample extraction",
        timeout=settings.vod_analysis_sample_timeout_seconds,
    )
    if not destination.is_file() or destination.stat().st_size <= 44:
        raise RuntimeError("Audio sample extraction failed: FFmpeg produced no PCM audio")
    return destination


def load_pcm16_wav(path: Path) -> np.ndarray:
    with wave.open(str(path), "rb") as source:
        if source.getnchannels() != 1 or source.getframerate() != SAMPLE_RATE:
            raise RuntimeError("VAD failed: audio sample is not mono 16 kHz PCM")
        if source.getsampwidth() != 2:
            raise RuntimeError("VAD failed: audio sample is not 16-bit PCM")
        frames = source.readframes(source.getnframes())
    return np.frombuffer(frames, dtype="<i2").astype(np.float32) / 32768.0


def basic_audio_features(audio: np.ndarray) -> dict[str, float]:
    if audio.size == 0:
        raise RuntimeError("VAD failed: audio sample is empty")
    frame_size = 400
    usable = audio[: (audio.size // frame_size) * frame_size]
    frames = usable.reshape(-1, frame_size) if usable.size else audio.reshape(1, -1)
    rms_frames = np.sqrt(np.mean(np.square(frames), axis=1) + 1e-12)
    rms_mean = float(np.mean(rms_frames))
    rms_variance = float(np.var(rms_frames))
    peak = float(np.max(np.abs(audio)))
    percentile_95 = float(np.percentile(rms_frames, 95))
    percentile_10 = float(np.percentile(rms_frames, 10))
    dynamic_range = max(0.0, percentile_95 - percentile_10)
    crossings = float(np.mean(np.signbit(audio[1:]) != np.signbit(audio[:-1]))) if audio.size > 1 else 0.0
    spectrum = np.abs(np.fft.rfft(audio[: min(audio.size, SAMPLE_RATE * 4)])) + 1e-12
    flatness = float(np.exp(np.mean(np.log(spectrum))) / np.mean(spectrum))
    continuity = 1.0 - min(1.0, rms_variance / max(rms_mean * rms_mean, 1e-8))
    return {
        "rms_mean": rms_mean,
        "rms_variance": rms_variance,
        "peak_level": peak,
        "dynamic_range": dynamic_range,
        "zero_crossing_rate": min(1.0, crossings),
        "spectral_flatness": min(1.0, max(0.0, flatness)),
        "audio_energy_continuity": min(1.0, max(0.0, continuity)),
    }
