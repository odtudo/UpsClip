import json
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest

from apps.api.app.database import VodAnalysisStore
from apps.api.app.services.process import ProcessError
from apps.api.app.services.smart_vertical.types import FaceDetection, Rect
from apps.api.app.services.vod_analysis.analyzer import VodAnalysisAnalyzer
from apps.api.app.services.vod_analysis.audio import basic_audio_features, extract_audio_sample
from apps.api.app.services.vod_analysis.cache import parse_source_identity
from apps.api.app.services.vod_analysis.fixtures import coarse_timeline_fixture
from apps.api.app.services.vod_analysis.layout_detection import build_layout_timeline, layout_cache_key
from apps.api.app.services.vod_analysis.metadata import (
    inspect_analysis_metadata,
    stream_access_from_metadata,
)
from apps.api.app.services.vod_analysis.profiles import ILLOJUAN
from apps.api.app.services.vod_analysis.schemas import (
    CoarseTimeline,
    CoarseVodMetadata,
    CoarseWindow,
    LayoutFrameSample,
)
from apps.api.app.services.vod_analysis.speech_features import aggregate_speech_features
from apps.api.app.services.vod_analysis.timeline import (
    load_timeline,
    persist_layout_timeline,
    persist_timeline,
)
from apps.api.app.services.vod_analysis.transcription import repeated_text_ratio, should_probe
from apps.api.app.services.vod_analysis.visual import CoarseVisualAnalyzer
from apps.api.app.services.vod_analysis.windows import generate_windows, group_windows_by_block


def test_generate_centered_windows_and_partial_last_window() -> None:
    windows = generate_windows(75, max_seconds=100, window_seconds=30, sample_seconds=10, block_seconds=60)
    assert [(item.start, item.end) for item in windows] == [(0, 30), (30, 60), (60, 75)]
    assert (windows[0].sample_start, windows[0].sample_end) == (10, 20)
    assert (windows[-1].sample_start, windows[-1].sample_end) == (62.5, 72.5)
    assert [len(block) for block in group_windows_by_block(windows)] == [2, 1]


@pytest.mark.parametrize(
    ("sample", "block"),
    [(31, 60), (0, 60), (10, 20)],
)
def test_window_configuration_limits(sample: float, block: int) -> None:
    with pytest.raises(ValueError):
        generate_windows(100, max_seconds=100, window_seconds=30, sample_seconds=sample, block_seconds=block)


def test_vad_aggregation_uses_real_regions() -> None:
    audio = np.full(160_000, 0.1, dtype=np.float32)
    regions = [{"start": 16_000, "end": 48_000}, {"start": 64_000, "end": 128_000}]
    result = aggregate_speech_features(audio, regions)
    assert result["voiced_seconds"] == pytest.approx(6.0)
    assert result["voice_ratio"] == pytest.approx(0.6)
    assert result["longest_speech_run"] == pytest.approx(4.0)
    assert result["longest_silence"] == pytest.approx(2.0)
    assert result["speech_start_delay"] == pytest.approx(1.0)


def test_audio_features_are_finite() -> None:
    time = np.arange(16_000) / 16_000
    audio = np.sin(2 * np.pi * 220 * time).astype(np.float32) * 0.2
    features = basic_audio_features(audio)
    assert 0 < features["rms_mean"] < 1
    assert 0 <= features["spectral_flatness"] <= 1
    assert 0 <= features["zero_crossing_rate"] <= 1


def test_probe_conditions_and_repetition(test_settings) -> None:
    settings = test_settings.model_copy(
        update={"vod_analysis_probe_voice_ratio": 0.2, "vod_analysis_probe_min_speech_seconds": 2}
    )
    assert should_probe({"voice_ratio": 0.7, "longest_speech_run": 3}, settings) == (True, None)
    assert should_probe({"voice_ratio": 0.1, "longest_speech_run": 3}, settings)[1] == (
        "voice_ratio_below_threshold"
    )
    assert repeated_text_ratio("hola chat hola chat hola chat hola chat") > 0.2


def test_audio_subprocess_is_bounded_and_safe(test_settings, tmp_path: Path) -> None:
    destination = tmp_path / "sample.wav"
    with patch("apps.api.app.services.vod_analysis.audio.run_command") as command:
        command.side_effect = lambda *args, **kwargs: destination.write_bytes(b"x" * 100)
        extract_audio_sample("https://media.invalid/audio", 123.5, 10, destination, test_settings)
    args = command.call_args.args[0]
    assert args[0] == test_settings.ffmpeg_path
    assert "-ss" in args and "123.500" in args
    assert "-t" in args and "10.000" in args
    assert "shell" not in command.call_args.kwargs


def test_metadata_is_sanitized_and_streams_are_selected(test_settings) -> None:
    raw = {
        "id": "123",
        "title": "Test VOD",
        "duration": 3600,
        "extractor": "twitch:vod",
        "webpage_url": "https://www.twitch.tv/videos/123",
        "formats": [
            {"format_id": "a", "url": "https://secret/audio", "acodec": "aac", "vcodec": "none", "abr": 64},
            {
                "format_id": "v",
                "url": "https://secret/video",
                "acodec": "none",
                "vcodec": "h264",
                "height": 360,
                "tbr": 600,
            },
        ],
    }
    identity = parse_source_identity("https://www.twitch.tv/videos/123")
    with patch("apps.api.app.services.vod_analysis.metadata._run_ytdlp_json", return_value=raw):
        metadata, returned = inspect_analysis_metadata(
            "https://www.twitch.tv/videos/123", identity, test_settings
        )
    assert metadata.duration_seconds == 3600
    assert "url" not in metadata.audio_formats[0]
    assert stream_access_from_metadata(returned).audio_url == "https://secret/audio"
    assert "secret" not in metadata.model_dump_json()


def test_metadata_subprocess_error_is_clear(test_settings) -> None:
    identity = parse_source_identity("https://youtu.be/abcdefghijk")
    error = ProcessError("metadata", ["yt-dlp"], 1, "private video")
    with patch("apps.api.app.services.vod_analysis.metadata.run_command", side_effect=error):
        with pytest.raises(RuntimeError, match="metadata unavailable"):
            inspect_analysis_metadata("https://youtu.be/abcdefghijk", identity, test_settings)


def test_timeline_atomic_serialization_and_cache_guard(tmp_path: Path) -> None:
    value = CoarseTimeline.model_validate(coarse_timeline_fixture("expected"))
    path = tmp_path / "coarse_timeline.json"
    persist_timeline(path, value)
    assert load_timeline(path, "expected") == value
    assert load_timeline(path, "different") is None
    assert not path.with_suffix(".tmp").exists()


def _audio_signals() -> dict:
    return {
        "voice_ratio": 0.7,
        "voiced_seconds": 7,
        "longest_speech_run": 5,
        "speech_continuity": 0.75,
        "number_of_speech_regions": 2,
        "longest_silence": 1,
        "speech_start_delay": 0.2,
        "speech_end_margin": 0.3,
        "silence_ratio": 0.3,
        "rms_mean": 0.1,
        "rms_variance": 0.01,
        "peak_level": 0.5,
        "dynamic_range": 0.2,
        "zero_crossing_rate": 0.1,
        "spectral_flatness": 0.2,
        "music_likelihood_features": {},
    }


def _metadata() -> CoarseVodMetadata:
    return CoarseVodMetadata(
        platform="twitch",
        extractor="twitch:vod",
        vod_id="123",
        title="Mock VOD",
        duration_seconds=60,
        original_url="https://www.twitch.tv/videos/123",
        audio_formats=[{"format_id": "a"}],
        video_formats=[{"format_id": "v"}],
    )


def test_real_analyzer_persists_progress_and_resumes(test_settings, tmp_path: Path) -> None:
    settings = test_settings.model_copy(
        update={
            "vod_analysis_fixture_mode": False,
            "vod_analysis_max_seconds": 60,
            "vod_analysis_fetch_block_seconds": 60,
            "layout_sample_seconds": 2,
        }
    )
    settings.ensure_directories()
    store = VodAnalysisStore(settings)
    store.initialize()
    identity = parse_source_identity("https://www.twitch.tv/videos/123")
    cache_key = layout_cache_key(identity.platform, identity.vod_id, ILLOJUAN.id, settings)
    partial = build_layout_timeline(
        [
            LayoutFrameSample(
                index=index,
                frame_timestamp=index * 2,
                layout="no_face",
                phase="waiting_or_music",
                confidence=0.9,
                face_area_ratio=0,
            )
            for index in range(5)
        ],
        60,
        cache_key,
        None,
        settings,
    )
    cache_path = settings.data_dir / "analysis" / "cache" / cache_key / "layout_timeline.json"
    persist_layout_timeline(cache_path, partial)
    job = store.create(
        {
            "id": "resume-job",
            "source_url": "https://www.twitch.tv/videos/123",
            "source_platform": "twitch",
            "source_vod_id": "123",
            "streamer_profile": "illojuan",
            "pipeline_version": settings.vod_analysis_phase_pipeline_version,
            "cache_key": cache_key,
            "fixture_mode": False,
            "phase_detection_strategy": "profile_layout_match",
            "requires_coarse_timeline": False,
        }
    )
    raw = {
        "formats": [
            {"url": "https://audio", "acodec": "aac", "vcodec": "none", "abr": 64},
            {"url": "https://video", "acodec": "none", "vcodec": "h264", "height": 360, "tbr": 500},
        ]
    }

    def fake_frames(_url, _start, _duration, _interval, destination, _settings, **_kwargs):
        import cv2

        destination.mkdir(parents=True, exist_ok=True)
        paths = []
        for index in range(30):
            path = destination / f"layout_{index:06d}.jpg"
            cv2.imwrite(str(path), np.zeros((180, 320, 3), dtype=np.uint8))
            paths.append(path)
        return paths

    class NoFaceDetector:
        def __init__(self, _settings):
            pass

        def detect(self, _frame, _timestamp):
            return []

    with (
        patch(
            "apps.api.app.services.vod_analysis.analyzer.inspect_analysis_metadata",
            return_value=(_metadata(), raw),
        ),
        patch("apps.api.app.services.vod_analysis.analyzer.extract_layout_frames", fake_frames),
        patch(
            "apps.api.app.services.smart_vertical.face_detection.OpenCVFaceDetector",
            NoFaceDetector,
        ),
        patch(
            "apps.api.app.services.vod_analysis.audio.extract_audio_sample",
            side_effect=AssertionError("visual strategy called audio extraction"),
        ),
        patch(
            "apps.api.app.services.vod_analysis.speech_features.measure_speech",
            side_effect=AssertionError("visual strategy called VAD"),
        ),
        patch(
            "apps.api.app.services.vod_analysis.transcription.ProbeTranscriber",
            side_effect=AssertionError("visual strategy loaded Whisper"),
        ),
    ):
        VodAnalysisAnalyzer(store, settings).process(job["id"])

    completed = store.get(job["id"])
    assert completed is not None and completed["status"] == "completed"
    assert completed["completed_windows"] == 30
    assert completed["result"]["phase"] == "visual_layout"
    assert completed["result"]["requires_coarse_timeline"] is False
    assert completed["result"]["coarse_timeline"] is None
    assert (settings.data_dir / "analysis" / job["id"] / "metadata.json").is_file()
    assert (settings.data_dir / "analysis" / job["id"] / "phase_timeline.json").is_file()
    assert (settings.data_dir / "analysis" / job["id"] / "layout_timeline.json").is_file()
    assert not (settings.data_dir / "analysis" / job["id"] / "coarse_timeline.json").exists()


def test_failed_window_can_be_serialized_without_aborting() -> None:
    value = CoarseWindow(
        index=0,
        start=0,
        end=30,
        sample_start=10,
        sample_end=20,
        warnings=["audio_sample_failed", "visual_sample_failed"],
    )
    assert json.loads(value.model_dump_json())["audio"] is None


def test_visual_analyzer_reuses_smart_face_detection(test_settings, tmp_path: Path) -> None:
    import cv2

    frame = np.zeros((180, 320, 3), dtype=np.uint8)
    first = tmp_path / "one.jpg"
    second = tmp_path / "two.jpg"
    cv2.imwrite(str(first), frame)
    cv2.imwrite(str(second), frame)
    detection = FaceDetection(0, Rect(10, 10, 80, 80), 0.9, 320, 180)
    analyzer = CoarseVisualAnalyzer(test_settings)
    detector = analyzer._face_detector = lambda: type(
        "Detector", (), {"detect": lambda self, image, timestamp: [detection]}
    )()
    result = analyzer.analyze([first, second])
    assert detector is not None
    assert result["sampled"] is True
    assert result["face_present"] is True
    assert result["layout_hint"] == "fullscreen_camera_hint"
