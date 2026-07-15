from pathlib import Path

import cv2
import numpy as np
import pytest

from apps.api.app.services.smart_vertical.types import FaceDetection, Rect
from apps.api.app.services.vod_analysis.layout_detection import annotate_debug_frame, layout_cache_key
from apps.api.app.services.vod_analysis.visual_profiles import ProfileLayoutMatcher, load_visual_profile


def face(x=300, y=180, w=140, h=180):
    return FaceDetection(0, Rect(x, y, w, h), 0.95, 640, 360)


def patterned(color):
    image = np.full((360, 640, 3), color, dtype=np.uint8)
    inverse = tuple(255 - item for item in color)
    cv2.rectangle(image, (0, 0), (190, 360), inverse, -1)
    cv2.line(image, (0, 40), (640, 310), (255, 255, 255), 8)
    return image


def make_profile(tmp_path: Path):
    refs = tmp_path / "refs"
    refs.mkdir()
    full = patterned((100, 80, 60))
    gameplay = patterned((20, 40, 160))
    cv2.imwrite(str(refs / "full.jpg"), full)
    cv2.imwrite(str(refs / "game.jpg"), gameplay)
    profile = tmp_path / "profile.json"
    profile.write_text("""{"version":1,"id":"test","display_name":"Test","ambiguity_margin":0.001,"minimum_frame_sharpness":1,"layouts":[
      {"id":"full_camera","phase":"talking","source_resolution":{"width":640,"height":360},"expected_face_region":{"id":"face","x":240,"y":100,"width":300,"height":250},"expected_face_area_ratio":{"min":0.05,"max":0.16},"expected_position":"center","stable_background_regions":[{"id":"left","x":0,"y":0,"width":190,"height":360}],"reference_images":["refs/full.jpg"],"weights":{"face_position":0.1,"face_size":0.1,"background_similarity":0.3,"reference_similarity":0.4,"temporal_stability":0.1},"minimum_match_score":0.72,"enabled":true},
      {"id":"gameplay_left","phase":"gameplay","source_resolution":{"width":640,"height":360},"expected_face_region":{"id":"face","x":0,"y":100,"width":190,"height":250},"expected_webcam_region":{"id":"webcam","x":0,"y":0,"width":190,"height":360},"expected_face_area_ratio":{"min":0.02,"max":0.10},"expected_position":"left","stable_background_regions":[{"id":"left","x":0,"y":0,"width":190,"height":360}],"reference_images":["refs/game.jpg"],"weights":{"face_position":0.1,"face_size":0.1,"background_similarity":0.3,"reference_similarity":0.4,"temporal_stability":0.1},"minimum_match_score":0.72,"enabled":true}
    ]}""")
    return profile, full, gameplay


def test_random_large_face_without_known_layout_is_waiting(tmp_path):
    profile, _, _ = make_profile(tmp_path)
    random_photo = np.random.default_rng(4).integers(0, 255, (360, 640, 3), dtype=np.uint8)
    result = ProfileLayoutMatcher(profile, 0.55).match(random_photo, [face(220, 80, 260, 260)])
    assert result.phase == "waiting_or_music"
    assert result.layout_id == "waiting_unmatched"


def test_full_camera_and_gameplay_known_layouts(tmp_path):
    profile, full, gameplay = make_profile(tmp_path)
    matcher = ProfileLayoutMatcher(profile, 0.55)
    assert matcher.match(full, [face()]).phase == "talking"
    assert matcher.match(gameplay, [face(30, 130, 120, 160)]).phase == "gameplay"


def test_valid_unmatched_without_face_is_waiting_and_corrupt_is_unknown(tmp_path):
    profile, _, _ = make_profile(tmp_path)
    matcher = ProfileLayoutMatcher(profile, 0.55)
    valid = np.random.default_rng(9).integers(0, 255, (360, 640, 3), dtype=np.uint8)
    assert matcher.match(valid, []).phase == "waiting_or_music"
    assert matcher.match(None, []).phase == "unknown"


def test_missing_reference_and_invalid_profile(tmp_path):
    profile, _, _ = make_profile(tmp_path)
    text = profile.read_text().replace("refs/full.jpg", "refs/missing.jpg")
    profile.write_text(text)
    with pytest.raises(ValueError, match="reference does not exist"):
        load_visual_profile(profile)


def test_equal_known_layout_scores_are_unknown(tmp_path):
    profile, full, _ = make_profile(tmp_path)
    cv2.imwrite(str(tmp_path / "refs/game.jpg"), full)
    profile.write_text(profile.read_text().replace('"ambiguity_margin":0.001', '"ambiguity_margin":0.5'))
    matched = ProfileLayoutMatcher(profile, 0.55).match(full, [face(), face(30, 130, 120, 160)])
    assert matched.phase == "unknown"
    assert "layout_scores_ambiguous" in matched.reasons


def test_close_layout_scores_with_same_phase_keep_known_phase(tmp_path):
    profile, full, _ = make_profile(tmp_path)
    cv2.imwrite(str(tmp_path / "refs/game.jpg"), full)
    profile.write_text(
        profile.read_text()
        .replace('"ambiguity_margin":0.001', '"ambiguity_margin":0.5')
        .replace('"id":"full_camera","phase":"talking"', '"id":"full_camera","phase":"gameplay"')
    )
    matched = ProfileLayoutMatcher(profile, 0.55).match(full, [face(), face(30, 130, 120, 160)])
    assert matched.phase == "gameplay"
    assert "same_phase_layout_tie_resolved" in matched.reasons


def test_illojuan_profile_contains_only_measured_enabled_layouts(test_settings):
    profile = load_visual_profile(test_settings.visual_layout_profile_path)
    layouts = {item.id: item for item in profile.layouts}
    assert layouts.keys() == {"full_camera_room", "gameplay_left", "gameplay_small_left"}
    assert all(item.enabled for item in layouts.values())


def test_cache_changes_when_reference_changes(tmp_path, test_settings):
    profile, full, _ = make_profile(tmp_path)
    settings = test_settings.model_copy(update={"visual_layout_profile_path": profile})
    before = layout_cache_key("twitch", "1", "illojuan", settings)
    cv2.circle(full, (40, 40), 25, (0, 0, 255), -1)
    cv2.imwrite(str(tmp_path / "refs/full.jpg"), full)
    assert layout_cache_key("twitch", "1", "illojuan", settings) != before


def test_debug_frame_contains_profile_annotation(tmp_path, test_settings):
    profile, full, _ = make_profile(tmp_path)
    matcher = ProfileLayoutMatcher(profile, 0.55)
    matched = matcher.match(full, [face()])
    from apps.api.app.services.vod_analysis.schemas import LayoutFrameSample

    sample = LayoutFrameSample(
        index=0,
        frame_timestamp=0,
        layout="fullscreen_face",
        layout_id=matched.layout_id,
        phase=matched.phase,
        confidence=matched.match_score,
        match_score=matched.match_score,
        second_best_score=matched.second_best_score,
        score_margin=matched.score_margin,
        matched_reference=matched.matched_reference,
        face_area_ratio=matched.face_area_ratio,
        signals=matched.signals,
        background_region_scores=matched.background_region_scores,
    )
    output = tmp_path / "debug.jpg"
    annotate_debug_frame(output, full, sample, [face()], test_settings, matcher)
    assert output.is_file() and output.stat().st_size > 0
