from fastapi.testclient import TestClient

from apps.api.app.database import VodAnalysisStore
from apps.api.app.main import create_app
from apps.api.app.services.vod_analysis.analyzer import VodAnalysisAnalyzer
from apps.api.app.services.vod_analysis.cache import build_cache_key, parse_source_identity
from apps.api.app.services.vod_analysis.profiles import ILLOJUAN, get_analysis_profile
from apps.api.app.services.vod_analysis.schemas import PhasedAnalysisResult, PhaseWindow


def test_parse_twitch_and_youtube_urls() -> None:
    assert parse_source_identity("https://www.twitch.tv/videos/123456789").vod_id == "123456789"
    youtube = parse_source_identity("https://www.youtube.com/watch?v=abcdefghijk")
    assert (youtube.platform, youtube.vod_id) == ("youtube", "abcdefghijk")


def test_rejects_url_without_vod_identity() -> None:
    try:
        parse_source_identity("https://www.twitch.tv/illojuan")
    except ValueError as exc:
        assert "one VOD" in str(exc)
    else:
        raise AssertionError("invalid Twitch URL was accepted")


def test_illojuan_profile_is_centralized_and_validated() -> None:
    profile = get_analysis_profile("illojuan")
    assert profile.language == "es"
    assert profile.phase_window_seconds == 30
    assert profile.candidate_target_min_seconds == 600
    assert profile.candidate_max_duration_seconds == 1200


def test_phase_windows_validate_timestamps() -> None:
    value = PhaseWindow.model_validate(
        {
            "start": 0,
            "end": 30,
            "phase": "talking",
            "confidence": 0.8,
            "signals": {
                "voice_ratio": 0.7,
                "speech_continuity": 0.8,
                "word_density": 2.2,
                "transcript_quality": 0.75,
                "music_likelihood": 0.1,
                "visual_change_rate": 0.04,
            },
        }
    )
    assert value.end - value.start == 30


def test_cache_key_changes_with_relevant_configuration(test_settings) -> None:
    identity = parse_source_identity("https://www.twitch.tv/videos/123456789")
    first = build_cache_key(identity, ILLOJUAN, test_settings)
    changed = test_settings.model_copy(update={"whisper_model": "tiny"})
    assert build_cache_key(identity, ILLOJUAN, changed) != first
    assert build_cache_key(identity, ILLOJUAN, test_settings) == first


def test_fixture_analyzer_persists_result_and_debug_artifacts(test_settings) -> None:
    settings = test_settings.model_copy(update={"vod_analysis_fixture_mode": True})
    settings.ensure_directories()
    store = VodAnalysisStore(settings)
    store.initialize()
    identity = parse_source_identity("https://www.twitch.tv/videos/123456789")
    job = store.create(
        {
            "id": "analysis-fixture",
            "source_url": "https://www.twitch.tv/videos/123456789",
            "source_platform": identity.platform,
            "source_vod_id": identity.vod_id,
            "streamer_profile": "illojuan",
            "pipeline_version": settings.vod_analysis_pipeline_version,
            "cache_key": "fixture-key",
            "fixture_mode": True,
        }
    )
    VodAnalysisAnalyzer(store, settings).process(job["id"])
    completed = store.get(job["id"])
    assert completed is not None and completed["status"] == "completed"
    result = PhasedAnalysisResult.model_validate(completed["result"])
    assert result.phase_detection_strategy == "profile_layout_match"
    assert result.requires_coarse_timeline is False
    assert result.coarse_timeline is None
    assert [item.phase for item in result.phase_timeline.segments] == [
        "waiting_or_music",
        "talking",
        "gameplay",
    ]
    artifact_dir = settings.data_dir / "analysis" / job["id"]
    assert (artifact_dir / "phase_timeline.json").is_file()
    assert (artifact_dir / "layout_timeline.json").is_file()
    assert not (artifact_dir / "coarse_timeline.json").exists()


def test_vod_analysis_api_progress_result_and_cache(test_settings) -> None:
    settings = test_settings.model_copy(update={"vod_analysis_fixture_mode": True})
    app = create_app(settings)
    with TestClient(app) as client:
        submitted: list[str] = []
        app.state.processor.submit_vod_analysis = submitted.append
        response = client.post(
            "/vod-analysis",
            json={"url": "https://www.twitch.tv/videos/123456789", "streamer": "illojuan"},
        )
        assert response.status_code == 202
        job_id = response.json()["job_id"]
        assert submitted == [job_id]
        queued = client.get(f"/vod-analysis/{job_id}")
        assert queued.json()["stage"] == "queued"

        VodAnalysisAnalyzer(app.state.analysis_store, settings).process(job_id)
        completed = client.get(f"/vod-analysis/{job_id}")
        assert completed.status_code == 200
        assert completed.json()["status"] == "completed"
        assert completed.json()["result"]["phase"] == "visual_layout"
        assert completed.json()["result"]["requires_coarse_timeline"] is False
        assert str(settings.data_dir) not in completed.text

        cached = client.post(
            "/vod-analysis",
            json={"url": "https://www.twitch.tv/videos/123456789", "streamer": "illojuan"},
        )
        assert cached.json() == {"job_id": job_id, "cached": True}


def test_force_reanalyze_creates_new_job(test_settings) -> None:
    settings = test_settings.model_copy(update={"vod_analysis_fixture_mode": True})
    app = create_app(settings)
    with TestClient(app) as client:
        app.state.processor.submit_vod_analysis = lambda job_id: None
        first = client.post(
            "/vod-analysis",
            json={"url": "https://youtu.be/abcdefghijk", "streamer": "illojuan"},
        ).json()
        second = client.post(
            "/vod-analysis",
            json={
                "url": "https://youtu.be/abcdefghijk",
                "streamer": "illojuan",
                "force_reanalyze": True,
            },
        ).json()
        assert first["job_id"] != second["job_id"]


def test_legacy_render_jobs_remain_readable_with_analysis_table(test_settings) -> None:
    from apps.api.app.database import JobStore

    test_settings.ensure_directories()
    job_store = JobStore(test_settings)
    job_store.initialize()
    analysis_store = VodAnalysisStore(test_settings)
    analysis_store.initialize()
    assert job_store.list() == []
    assert analysis_store.get("missing") is None


def test_fixture_files_stay_under_analysis_directory(test_settings) -> None:
    assert (test_settings.data_dir / "analysis").resolve().parent == test_settings.data_dir.resolve()
