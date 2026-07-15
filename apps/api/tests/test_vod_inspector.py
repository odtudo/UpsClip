import json
import zipfile
from datetime import UTC, datetime

from fastapi.testclient import TestClient

from apps.api.app.database import VodAnalysisStore
from apps.api.app.main import create_app
from apps.api.app.services.vod_analysis.analyzer import VodAnalysisAnalyzer
from apps.api.app.services.vod_analysis.fixtures import phase_detection_fixture
from apps.api.app.services.vod_analysis.layout_detection import build_layout_timeline
from apps.api.app.services.vod_analysis.phase_detection import build_phase_timeline
from apps.api.app.services.vod_analysis.profiles import ILLOJUAN
from apps.api.app.services.vod_analysis.schemas import (
    CoarseTimeline,
    CoarseVodMetadata,
    LayoutFrameSample,
    ValidationNotes,
)
from apps.api.app.services.vod_analysis.timeline import (
    persist_layout_timeline,
    persist_phase_timeline,
    persist_timeline,
)
from apps.api.app.services.vod_inspector import (
    build_report,
    calculate_metrics,
    compare_notes,
    export_report,
    load_notes,
    prepare_inspector,
    save_notes,
    timestamp_url,
)


def metadata() -> CoarseVodMetadata:
    return CoarseVodMetadata(
        platform="twitch",
        extractor="fixture",
        vod_id="123",
        title="Inspector fixture",
        uploader="IlloJuan",
        duration_seconds=2040,
        original_url="https://www.twitch.tv/videos/123",
    )


def completed_job(job_id: str = "inspector-job") -> dict:
    now = datetime.now(UTC).isoformat()
    return {
        "id": job_id,
        "source_url": "https://www.twitch.tv/videos/123",
        "source_platform": "twitch",
        "source_vod_id": "123",
        "streamer_profile": "illojuan",
        "pipeline_version": "vod-analysis-v3-phases.1",
        "cache_key": "inspector-cache",
        "fixture_mode": False,
        "status": "completed",
        "stage": "phase_analysis_completed",
        "progress": 100,
        "cached": False,
        "warnings": [],
        "result": {},
        "error_message": None,
        "created_at": now,
        "updated_at": now,
        "phase_detection_strategy": "legacy_heuristic",
        "requires_coarse_timeline": True,
    }


def write_artifacts(settings, job: dict):
    directory = settings.data_dir / "analysis" / job["id"]
    directory.mkdir(parents=True, exist_ok=True)
    coarse = CoarseTimeline.model_validate(phase_detection_fixture(cache_key=job["cache_key"]))
    phase = build_phase_timeline(coarse, metadata(), ILLOJUAN, "vod-analysis-v3-phases.1")
    (directory / "metadata.json").write_text(metadata().model_dump_json(indent=2), encoding="utf-8")
    persist_timeline(directory / "coarse_timeline.json", coarse)
    persist_phase_timeline(directory / "phase_timeline.json", phase)
    samples = [
        LayoutFrameSample(
            index=0,
            frame_timestamp=0,
            layout="no_face",
            phase="waiting_or_music",
            confidence=0.9,
            face_area_ratio=0,
        )
    ]
    layout = build_layout_timeline(samples, 2040, "layout-cache", None, settings)
    persist_layout_timeline(directory / "layout_timeline.json", layout)
    return directory, coarse, phase, layout


def test_timestamp_urls_open_exact_vod_position() -> None:
    assert timestamp_url("https://www.twitch.tv/videos/123", 6150) == (
        "https://www.twitch.tv/videos/123?t=1h42m30s"
    )
    assert timestamp_url("https://www.youtube.com/watch?v=abcdefghijk", 6150) == (
        "https://www.youtube.com/watch?v=abcdefghijk&t=6150"
    )
    assert timestamp_url("https://youtu.be/abcdefghijk", 65).endswith("?t=65")


def test_validation_comparison_and_metrics(test_settings) -> None:
    _, _, phase, _ = write_artifacts(test_settings, completed_job())
    notes = ValidationNotes(
        talking_start=170,
        talking_end=910,
        gameplay_start=905,
        gameplay_end=1130,
        talking_block_2_start=1150,
        talking_block_2_end=1850,
    )
    comparisons = compare_notes(phase, notes)
    assert next(item for item in comparisons if item.transition == "talking_start").error_seconds == 10
    metrics = calculate_metrics(phase, notes, comparisons)
    assert metrics.mean_absolute_error_seconds is not None
    assert metrics.maximum_absolute_error_seconds == 10
    assert metrics.detected_phase_count == 5
    assert metrics.omitted_phase_count == 0
    assert 0 < metrics.mean_confidence <= 1


def test_validation_notes_round_trip(test_settings) -> None:
    directory = test_settings.data_dir / "analysis" / "notes"
    notes = ValidationNotes(talking_start=100, gameplay_start=900)
    save_notes(directory, notes)
    assert load_notes(directory) == notes
    assert json.loads((directory / "validation_notes.json").read_text())["talking_start"] == 100


def test_report_png_and_whitelisted_zip(test_settings) -> None:
    job = completed_job("export-job")
    directory, coarse, phase, layout = write_artifacts(test_settings, job)
    notes = ValidationNotes(talking_start=180, talking_end=900)
    save_notes(directory, notes)
    comparisons = compare_notes(phase, notes)
    metrics = calculate_metrics(phase, notes, comparisons)
    report = build_report(job, test_settings, metadata(), layout, phase, notes, comparisons, metrics)
    assert "Pipeline version" in report and "Thresholds used" in report
    archive_path = export_report(job, test_settings)
    with zipfile.ZipFile(archive_path) as archive:
        names = set(archive.namelist())
        assert {
            "metadata.json",
            "coarse_timeline.json",
            "layout_timeline.json",
            "phase_timeline.json",
            "timeline.png",
            "summary.md",
            "validation_report.md",
        } <= names
        assert "validation_notes.json" not in names
        assert archive.read("timeline.png").startswith(b"\x89PNG\r\n\x1a\n")
        assert not any("token" in name or "cookie" in name or "credential" in name for name in names)


def test_validation_debug_export(test_settings) -> None:
    settings = test_settings.model_copy(update={"validation_debug": True})
    job = completed_job("debug-export-job")
    write_artifacts(settings, job)
    archive_path = export_report(job, settings)
    with zipfile.ZipFile(archive_path) as archive:
        assert {"raw_phase_scores.json", "smoothed_windows.json", "transition_graph.json"} <= set(
            archive.namelist()
        )


def test_inspector_response_contains_timeline_links_and_metrics(test_settings) -> None:
    job = completed_job("response-job")
    write_artifacts(test_settings, job)
    response = prepare_inspector(job, test_settings)
    assert response.segments[0].open_url.endswith("t=0h0m0s")
    assert response.phase_timeline is not None
    assert response.metrics is not None
    assert response.export_url == "/vod-inspector/response-job/export"


def test_visual_inspector_does_not_require_coarse_timeline(test_settings) -> None:
    job = completed_job("visual-no-coarse") | {
        "phase_detection_strategy": "visual_layout",
        "requires_coarse_timeline": False,
    }
    directory, _coarse, _phase, _layout = write_artifacts(test_settings, job)
    (directory / "coarse_timeline.json").unlink()
    response = prepare_inspector(job, test_settings)
    assert response.status == "completed"
    assert response.requires_coarse_timeline is False
    assert response.phase_timeline is not None
    archive_path = export_report(job, test_settings)
    with zipfile.ZipFile(archive_path) as archive:
        names = set(archive.namelist())
        assert "layout_timeline.json" in names
        assert "coarse_timeline.json" not in names


def test_polling_states_never_require_pending_artifacts(test_settings) -> None:
    for status, stage in (
        ("queued", "queued"),
        ("processing", "sampling_layout_frames"),
        ("failed", "failed"),
    ):
        job = completed_job(f"poll-{status}") | {
            "status": status,
            "stage": stage,
            "progress": 0 if status == "queued" else 40,
            "phase_detection_strategy": "visual_layout",
            "requires_coarse_timeline": False,
            "error_message": "visual stream failed" if status == "failed" else None,
        }
        response = prepare_inspector(job, test_settings)
        assert response.status == status
        assert response.phase_timeline is None
        if status == "failed":
            assert response.error_message == "visual stream failed"


def test_legacy_job_with_coarse_timeline_remains_supported(test_settings) -> None:
    job = completed_job("legacy-compatible")
    directory, _coarse, _phase, _layout = write_artifacts(test_settings, job)
    (directory / "layout_timeline.json").unlink()
    response = prepare_inspector(job, test_settings)
    assert response.status == "completed"
    assert response.phase_detection_strategy == "legacy_heuristic"


def test_inspector_api_reuses_fixture_analysis_and_exports(test_settings) -> None:
    settings = test_settings.model_copy(update={"vod_analysis_fixture_mode": True})
    app = create_app(settings)
    with TestClient(app) as client:
        app.state.processor.submit_vod_analysis = lambda job_id: None
        started = client.post(
            "/vod-inspector",
            json={"url": "https://www.twitch.tv/videos/123456789", "streamer": "illojuan"},
        )
        job_id = started.json()["job_id"]
        VodAnalysisAnalyzer(app.state.analysis_store, settings).process(job_id)
        response = client.get(f"/vod-inspector/{job_id}")
        assert response.status_code == 200
        assert response.json()["segments"][0]["open_url"].startswith("https://www.twitch.tv/")
        compared = client.put(
            f"/vod-inspector/{job_id}/validation-notes",
            json={"talking_start": 60, "talking_end": 90},
        )
        assert compared.status_code == 200
        exported = client.get(f"/vod-inspector/{job_id}/export")
        assert exported.status_code == 200
        assert exported.headers["content-type"] == "application/zip"


def test_inspector_polling_http_200_for_queued_processing_and_failed(test_settings) -> None:
    app = create_app(test_settings)
    client = TestClient(app)
    store = VodAnalysisStore(test_settings)
    for status, stage in (
        ("queued", "queued"),
        ("processing", "detecting_faces"),
        ("failed", "failed"),
    ):
        job_id = f"http-{status}"
        store.create(
            {
                "id": job_id,
                "source_url": "https://www.twitch.tv/videos/123",
                "source_platform": "twitch",
                "source_vod_id": "123",
                "streamer_profile": "illojuan",
                "pipeline_version": "vod-analysis-visual-layout.1",
                "cache_key": f"cache-{status}",
                "fixture_mode": False,
                "phase_detection_strategy": "visual_layout",
                "requires_coarse_timeline": False,
            }
        )
        if status != "queued":
            store.update(
                job_id,
                status=status,
                stage=stage,
                error_message="stream unavailable" if status == "failed" else None,
            )
        response = client.get(f"/vod-inspector/{job_id}")
        assert response.status_code == 200
        assert response.json()["status"] == status
    client.close()
