from fastapi.testclient import TestClient

from apps.api.app.main import create_app


def test_create_and_retrieve_job(test_settings) -> None:
    app = create_app(test_settings)
    with TestClient(app) as client:
        submitted: list[str] = []
        app.state.processor.submit = submitted.append
        response = client.post(
            "/jobs",
            json={
                "source_url": "https://www.twitch.tv/videos/123456789",
                "start": "00:10",
                "end": "00:20",
                "remove_silences": True,
                "normalize_audio": True,
                "generate_subtitles": False,
                "output_format": "horizontal",
                "demo": True,
            },
        )
        assert response.status_code == 202
        created = response.json()
        assert created["status"] == "queued"
        assert created["start_seconds"] == 10
        assert submitted == [created["id"]]
        assert "automatic_zooms" not in created

        fetched = client.get(f"/jobs/{created['id']}")
        assert fetched.status_code == 200
        assert fetched.json()["source_url"].startswith("https://www.twitch.tv/videos/")

        listed = client.get("/jobs")
        assert listed.status_code == 200
        assert [job["id"] for job in listed.json()] == [created["id"]]


def test_vertical_jobs_force_subtitles(test_settings) -> None:
    app = create_app(test_settings)
    with TestClient(app) as client:
        app.state.processor.submit = lambda job_id: None
        response = client.post(
            "/jobs",
            json={
                "source_url": "https://www.twitch.tv/videos/123456789",
                "start": "00:00",
                "end": "00:10",
                "generate_subtitles": False,
                "output_format": "vertical",
                "demo": True,
            },
        )
        assert response.status_code == 202
        assert response.json()["generate_subtitles"] is True
        assert response.json()["smart_vertical_layout"] is True


def test_horizontal_disables_smart_layout(test_settings) -> None:
    app = create_app(test_settings)
    with TestClient(app) as client:
        app.state.processor.submit = lambda job_id: None
        response = client.post(
            "/jobs",
            json={
                "source_url": "https://www.twitch.tv/videos/123456789",
                "start": "00:00",
                "end": "00:10",
                "output_format": "horizontal",
                "smart_vertical_layout": True,
            },
        )
        assert response.status_code == 202
        assert response.json()["smart_vertical_layout"] is False


def test_profiles_endpoint_and_invalid_profile(test_settings) -> None:
    app = create_app(test_settings)
    with TestClient(app) as client:
        assert client.get("/profiles").json() == []
        response = client.post(
            "/jobs",
            json={
                "source_url": "https://www.twitch.tv/videos/123456789",
                "start": "00:00",
                "end": "00:10",
                "output_format": "vertical",
                "streamer_profile": "missing",
            },
        )
        assert response.status_code == 422
        assert "does not exist" in response.json()["detail"]


def test_api_rejects_invalid_interval(test_settings) -> None:
    app = create_app(test_settings)
    with TestClient(app) as client:
        response = client.post(
            "/jobs",
            json={
                "source_url": "https://www.twitch.tv/videos/123456789",
                "start": "01:00",
                "end": "00:30",
            },
        )
        assert response.status_code == 422
        assert "after start" in response.json()["detail"]


def test_api_rejects_duration_over_configured_maximum(test_settings) -> None:
    app = create_app(test_settings)
    with TestClient(app) as client:
        response = client.post(
            "/jobs",
            json={
                "source_url": "https://www.twitch.tv/videos/123456789",
                "start": "00:00",
                "end": "02:01",
            },
        )
        assert response.status_code == 422
        assert "exceeds" in response.json()["detail"]


def test_setup_status_hides_paths_and_detects_missing_oauth(test_settings) -> None:
    app = create_app(test_settings)
    with TestClient(app) as client:
        response = client.get("/setup/status")
        assert response.status_code == 200
        payload = response.json()
        assert payload["youtube_ready"] is False
        assert payload["youtube_client_secret_present"] is False
        assert payload["data_writable"] is True
        assert payload["face_detector_name"] == "OpenCV YuNet"
        assert payload["smart_vertical_available"] is False
        assert payload["smart_vertical_ready"] is False
        assert str(test_settings.data_dir) not in response.text
