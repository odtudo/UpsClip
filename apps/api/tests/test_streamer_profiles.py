import json

import pytest

from apps.api.app.services.smart_vertical.profiles import (
    ProfileValidationError,
    list_profiles,
    load_profile,
    scaled_profile_regions,
)


def profile() -> dict:
    return {
        "version": 1,
        "id": "test_streamer",
        "display_name": "Test Streamer",
        "source_resolution": {"width": 1920, "height": 1080},
        "layouts": [
            {
                "id": "top_left",
                "type": "small_facecam",
                "facecam_region": {"x": 20, "y": 20, "width": 400, "height": 300},
                "position": "top_left",
            }
        ],
        "vertical": {"layout": "face_top_content_bottom", "facecam_height_ratio": 0.38},
    }


def test_profile_loading_listing_and_scaling(tmp_path) -> None:
    directory = tmp_path / "profiles"
    directory.mkdir()
    (directory / "test_streamer.json").write_text(json.dumps(profile()))
    loaded = load_profile(directory, "test_streamer")
    assert list_profiles(directory) == [{"id": "test_streamer", "display_name": "Test Streamer"}]
    region, _ = scaled_profile_regions(loaded, 1280, 720)[0]
    assert region.width == 266 and region.height == 200


def test_profile_rejects_traversal_and_out_of_bounds(tmp_path) -> None:
    with pytest.raises(ProfileValidationError):
        load_profile(tmp_path, "../../etc/passwd")
    directory = tmp_path / "profiles"
    directory.mkdir()
    invalid = profile()
    invalid["layouts"][0]["facecam_region"]["width"] = 5000
    (directory / "test_streamer.json").write_text(json.dumps(invalid))
    with pytest.raises(ProfileValidationError, match="exceeds"):
        load_profile(directory, "test_streamer")
