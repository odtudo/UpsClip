from __future__ import annotations

import hashlib
import json
import math
import statistics
from collections import Counter

from .profiles import AnalysisProfile, PhaseDetectionConfig
from .schemas import (
    ClassifiedPhaseWindow,
    CoarseTimeline,
    CoarseVodMetadata,
    CoarseWindow,
    DetectedTalkingBlock,
    PhaseScores,
    PhaseSegment,
    PhaseSummary,
    PhaseTimeline,
    SelectedTalkingBlock,
)

PHASES = ("waiting_or_music", "talking", "gameplay", "unknown")
GAMEPLAY_WORDS = {
    "jugar",
    "juego",
    "partida",
    "nivel",
    "misión",
    "mision",
    "boss",
    "enemigo",
    "mapa",
    "inventario",
    "empezamos",
    "vamos a jugar",
    "abrimos el juego",
}
TALKING_WORDS = {"chat", "contar", "historia", "anécdota", "anecdota", "opinión", "opinion"}


def phase_cache_key(coarse: CoarseTimeline, profile: AnalysisProfile, pipeline_version: str) -> str:
    payload = {
        "coarse_cache_key": coarse.cache_key,
        "coarse_pipeline_version": coarse.pipeline_version,
        "phase_pipeline_version": pipeline_version,
        "phase_profile": profile.phase_detection.model_dump(),
        "minimum_talking_block_seconds": profile.minimum_talking_block_seconds,
        "sustained_talking_seconds": profile.sustained_talking_seconds,
        "classifier": "explainable-weighted-v1",
        "smoothing": "viterbi-neighbour-microsegment-v1",
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def _ratio(value: float, threshold: float) -> float:
    return _clamp(value / max(threshold, 1e-6))


def _chapter_hint(metadata: CoarseVodMetadata, start: float, end: float) -> tuple[str | None, str | None]:
    midpoint = (start + end) / 2
    for chapter in metadata.chapters:
        chapter_start = float(chapter.get("start_time", chapter.get("start", 0)) or 0)
        chapter_end = float(chapter.get("end_time", chapter.get("end", math.inf)) or math.inf)
        if chapter_start <= midpoint < chapter_end:
            title = str(chapter.get("title", "")).lower()
            if any(word in title for word in ("chat", "charla", "talk", "just chatting")):
                return "talking", "chapter_title_chatting_hint"
            if any(word in title for word in ("game", "juego", "jugando", "partida", "gaming")):
                return "gameplay", "chapter_title_gameplay_hint"
    return None, None


def classify_window(
    window: CoarseWindow,
    metadata: CoarseVodMetadata,
    profile: AnalysisProfile,
) -> ClassifiedPhaseWindow:
    config = profile.phase_detection
    weights = config.weights
    audio = window.audio
    probe = window.transcript_probe
    visual = window.visual
    reasons: list[str] = []
    warnings = list(window.warnings)

    if audio is None:
        warnings.append("audio_signals_unavailable")
    if visual is None or not visual.sampled:
        warnings.append("visual_signals_unavailable")

    voice = audio.voice_ratio if audio else 0.0
    continuity = audio.speech_continuity if audio else 0.0
    silence = audio.silence_ratio if audio else 1.0
    dynamics = audio.dynamic_range if audio else 0.0
    music = audio.music_likelihood_features.get("energy_continuity", 0.0) if audio else 0.0
    quality = probe.transcript_quality_score if probe and probe.attempted else 0.0
    words = probe.words_per_second if probe and probe.attempted else 0.0
    repetition = probe.repeated_text_ratio if probe and probe.attempted else 0.0
    spanish = bool(probe and probe.language == profile.language)
    text = probe.text.lower() if probe else ""
    motion = visual.motion_score if visual and visual.sampled else 0.0
    scene = visual.scene_change_score if visual and visual.sampled else 0.0
    layout = visual.layout_hint if visual and visual.sampled else "unknown"
    face = bool(visual and visual.sampled and visual.face_present)

    talking = (
        weights["talking_voice"] * _ratio(voice, config.talking_min_voice_ratio)
        + weights["talking_continuity"] * _ratio(continuity, config.talking_min_speech_continuity)
        + weights["talking_transcript"] * _ratio(quality, config.talking_min_transcript_quality)
        + weights["talking_words"] * _ratio(words, config.talking_min_word_density)
        + weights["talking_spanish"] * float(spanish)
        + weights["talking_face"]
        * float(face and layout in {"fullscreen_camera_hint", "facecam_overlay_hint"})
        + weights["talking_low_motion"] * (1 - _ratio(motion, config.gameplay_min_motion_score * 1.5))
        - weights["talking_repetition_penalty"] * repetition
    )
    waiting = (
        weights["waiting_low_voice"] * (1 - _ratio(voice, config.waiting_max_voice_ratio))
        + weights["waiting_silence"] * silence
        + weights["waiting_repetition"] * repetition
        + weights["waiting_music"] * music * (1 - voice * 0.5)
        + weights["waiting_no_face"] * float(not face)
        + weights["waiting_stable_visual"]
        * (1 - _ratio(max(motion, scene), config.gameplay_min_motion_score))
    )
    fragmented = _clamp((voice - continuity) * 2 + (0.35 if 0.1 < voice < 0.55 else 0))
    gameplay = (
        weights["gameplay_motion"] * _ratio(motion, config.gameplay_min_motion_score)
        + weights["gameplay_scene"] * _ratio(scene, config.gameplay_min_scene_change_score)
        + weights["gameplay_overlay"] * float(layout == "facecam_overlay_hint")
        + weights["gameplay_dynamics"] * _ratio(dynamics, 0.18)
        + weights["gameplay_fragmented_speech"] * fragmented
    )

    if voice >= config.talking_min_voice_ratio:
        reasons.append("high_voice_ratio")
    if continuity >= config.talking_min_speech_continuity:
        reasons.append("continuous_speech")
    if quality >= config.talking_min_transcript_quality:
        reasons.append("high_transcript_quality")
    if spanish and quality > 0:
        reasons.append("spanish_speech_probe")
    if repetition >= 0.35:
        reasons.append("repetitive_transcript")
    if silence >= 0.75:
        reasons.append("long_silence_ratio")
    if face and layout == "fullscreen_camera_hint":
        reasons.append("stable_large_face")
    if layout == "facecam_overlay_hint":
        reasons.append("overlay_facecam_layout")
    if motion >= config.gameplay_min_motion_score:
        reasons.append("high_motion")
    if scene >= config.gameplay_min_scene_change_score:
        reasons.append("high_scene_change")
    if any(word in text for word in GAMEPLAY_WORDS):
        gameplay += 0.10
        reasons.append("gameplay_language_hint")
    if any(word in text for word in TALKING_WORDS):
        talking += 0.06
        reasons.append("conversation_language_hint")
    chapter_phase, chapter_reason = _chapter_hint(metadata, window.start, window.end)
    if chapter_phase == "talking":
        talking += 0.08
    elif chapter_phase == "gameplay":
        gameplay += 0.08
    if chapter_reason:
        reasons.append(chapter_reason)

    talking, waiting, gameplay = map(_clamp, (talking, waiting, gameplay))
    missing_ratio = (float(audio is None) + float(visual is None or not visual.sampled)) / 2
    ordered = sorted((waiting, talking, gameplay), reverse=True)
    ambiguity = 1 - _clamp((ordered[0] - ordered[1]) / max(config.raw_phase_min_margin, 0.01))
    unknown = _clamp(0.08 + 0.72 * missing_ratio + 0.35 * ambiguity)
    named_scores = {"waiting_or_music": waiting, "talking": talking, "gameplay": gameplay}
    winner = max(named_scores, key=named_scores.get)
    winner_score = named_scores[winner]
    margin = ordered[0] - ordered[1]
    if audio is None and (visual is None or not visual.sampled):
        raw_phase = "unknown"
        reasons.append("insufficient_audio_and_visual_signals")
    elif winner_score < config.raw_phase_min_confidence or margin < config.raw_phase_min_margin:
        raw_phase = "unknown"
        reasons.append("contradictory_or_low_confidence_signals")
    else:
        raw_phase = winner
    confidence = unknown if raw_phase == "unknown" else winner_score
    return ClassifiedPhaseWindow(
        index=window.index,
        start=window.start,
        end=window.end,
        raw_phase=raw_phase,
        raw_confidence=_clamp(confidence),
        phase=raw_phase,
        confidence=_clamp(confidence),
        phase_scores=PhaseScores(
            waiting_or_music=waiting, talking=talking, gameplay=gameplay, unknown=unknown
        ),
        reasons=list(dict.fromkeys(reasons)),
        warnings=list(dict.fromkeys(warnings)),
    )


def _transition_penalty(previous: str, current: str, config: PhaseDetectionConfig) -> float:
    if previous == current:
        return config.transition_penalties["same"]
    if "unknown" in {previous, current}:
        return config.transition_penalties["unknown"]
    if {previous, current} == {"waiting_or_music", "gameplay"}:
        key = "waiting_gameplay" if previous == "waiting_or_music" else "gameplay_waiting"
        return config.transition_penalties[key]
    return config.transition_penalties["common"]


def smooth_windows(
    raw_windows: list[ClassifiedPhaseWindow], config: PhaseDetectionConfig
) -> list[ClassifiedPhaseWindow]:
    if not raw_windows:
        return []
    # Viterbi over explainable emissions and transition penalties prevents one-window flicker.
    states = list(PHASES)
    costs: list[dict[str, tuple[float, str | None]]] = []
    for index, window in enumerate(raw_windows):
        emissions = window.phase_scores.model_dump()
        current: dict[str, tuple[float, str | None]] = {}
        for state in states:
            emission_cost = 1 - emissions[state]
            if index == 0:
                current[state] = (emission_cost, None)
            else:
                options = [
                    (costs[-1][previous][0] + _transition_penalty(previous, state, config), previous)
                    for previous in states
                ]
                best_cost, previous = min(options, key=lambda item: item[0])
                current[state] = (best_cost + emission_cost, previous)
        costs.append(current)
    state = min(costs[-1], key=lambda item: costs[-1][item][0])
    path = [state]
    for index in range(len(raw_windows) - 1, 0, -1):
        state = costs[index][state][1] or state
        path.append(state)
    path.reverse()

    smoothed: list[ClassifiedPhaseWindow] = []
    for window, phase in zip(raw_windows, path, strict=True):
        reasons = list(window.smoothing_reasons)
        if phase != window.raw_phase:
            reasons.append("temporal_viterbi_smoothing")
            if window.raw_phase == "unknown":
                reasons.append("smoothed_short_unknown_gap")
        score = getattr(window.phase_scores, phase)
        smoothed.append(
            window.model_copy(
                update={
                    "phase": phase,
                    "confidence": _clamp((window.raw_confidence + score) / 2),
                    "smoothing_reasons": reasons,
                }
            )
        )

    # Explicitly bridge small unknown gaps surrounded by the same stable phase.
    radius = config.smoothing_radius_windows
    for index, window in enumerate(smoothed):
        if window.phase != "unknown":
            continue
        left = [item.phase for item in smoothed[max(0, index - radius) : index] if item.phase != "unknown"]
        right = [item.phase for item in smoothed[index + 1 : index + 1 + radius] if item.phase != "unknown"]
        if left and right and left[-1] == right[0]:
            smoothed[index] = window.model_copy(
                update={
                    "phase": left[-1],
                    "confidence": getattr(window.phase_scores, left[-1]),
                    "smoothing_reasons": [*window.smoothing_reasons, "smoothed_short_unknown_gap"],
                }
            )
    return smoothed


def _robust_confidence(values: list[float]) -> float:
    if not values:
        return 0
    ordered = sorted(values)
    trim = max(0, len(ordered) // 10)
    core = ordered[trim : len(ordered) - trim] if trim and len(ordered) > trim * 2 else ordered
    return _clamp((statistics.median(core) * 0.6) + (statistics.fmean(core) * 0.4))


def merge_segments(windows: list[ClassifiedPhaseWindow]) -> list[PhaseSegment]:
    segments: list[PhaseSegment] = []
    for window in windows:
        if not segments or segments[-1].phase != window.phase or abs(segments[-1].end - window.start) > 0.01:
            segments.append(
                PhaseSegment(
                    start=window.start,
                    end=window.end,
                    phase=window.phase,
                    confidence=window.confidence,
                    window_count=1,
                    reasons=[*window.reasons, *window.smoothing_reasons],
                    warnings=window.warnings,
                )
            )
            continue
        previous = segments[-1]
        matching = [item for item in windows if previous.start <= item.start and item.end <= window.end]
        previous.end = window.end
        previous.window_count += 1
        previous.confidence = _robust_confidence([item.confidence for item in matching])
        previous.reasons = list(
            dict.fromkeys([*previous.reasons, *window.reasons, *window.smoothing_reasons])
        )
        previous.warnings = list(dict.fromkeys([*previous.warnings, *window.warnings]))
    for index, segment in enumerate(segments):
        segment.transition_in = None if index == 0 else f"{segments[index - 1].phase}_to_{segment.phase}"
        segment.transition_out = (
            None if index == len(segments) - 1 else f"{segment.phase}_to_{segments[index + 1].phase}"
        )
    return segments


def absorb_microsegments(
    windows: list[ClassifiedPhaseWindow], config: PhaseDetectionConfig
) -> list[ClassifiedPhaseWindow]:
    result = list(windows)
    segments = merge_segments(result)
    for index in range(1, len(segments) - 1):
        segment, left, right = segments[index], segments[index - 1], segments[index + 1]
        duration = segment.end - segment.start
        strong_transition = segment.confidence >= 0.72 or any(
            reason in segment.reasons for reason in ("high_motion", "high_scene_change")
        )
        minimum = config.microsegment_max_seconds
        if segment.phase == "waiting_or_music" and segment.confidence < 0.55:
            minimum = max(minimum, config.waiting_min_segment_seconds)
        elif segment.phase == "gameplay" and segment.confidence < 0.55:
            minimum = max(minimum, config.gameplay_min_segment_seconds)
        if duration <= minimum and left.phase == right.phase and not strong_transition:
            for window_index, window in enumerate(result):
                if segment.start <= window.start and window.end <= segment.end:
                    result[window_index] = window.model_copy(
                        update={
                            "phase": left.phase,
                            "confidence": getattr(window.phase_scores, left.phase),
                            "smoothing_reasons": [
                                *window.smoothing_reasons,
                                "merged_low_confidence_transition",
                            ],
                        }
                    )
    return result


def build_talking_blocks(
    segments: list[PhaseSegment], profile: AnalysisProfile
) -> tuple[list[DetectedTalkingBlock], list[SelectedTalkingBlock], str | None, list[str]]:
    talking_segments = [(index, item) for index, item in enumerate(segments) if item.phase == "talking"]
    blocks: list[DetectedTalkingBlock] = []
    for number, (segment_index, segment) in enumerate(talking_segments, 1):
        duration = segment.end - segment.start
        next_segment = segments[segment_index + 1] if segment_index + 1 < len(segments) else None
        if next_segment is None:
            transition = "end_of_analysis"
        elif next_segment.phase == "gameplay" and next_segment.confidence >= 0.5:
            transition = "gameplay_transition"
        elif next_segment.phase == "unknown":
            transition = "unknown_transition"
        elif next_segment.confidence < 0.5:
            transition = "low_confidence_transition"
        else:
            transition = "other_transition"
        if duration >= profile.minimum_talking_block_seconds:
            relevance = "secondary"
            reasons = ["long_sustained_conversation"]
        elif duration >= profile.sustained_talking_seconds:
            relevance = "low_priority"
            reasons = ["short_sustained_conversation"]
        else:
            relevance = "ignored"
            reasons = ["below_relevant_talking_duration"]
        if segment.confidence >= 0.65:
            reasons.append("consistent_talking_window_scores")
        blocks.append(
            DetectedTalkingBlock(
                id=f"talking-{number:03d}",
                start_seconds=segment.start,
                end_seconds=segment.end,
                duration_seconds=duration,
                confidence=segment.confidence,
                priority=number,
                relevance=relevance,
                selection_reason=reasons,
                end_transition=transition,
                warnings=segment.warnings,
            )
        )

    eligible = [item for item in blocks if item.duration_seconds >= profile.minimum_talking_block_seconds]
    primary = eligible[0].id if eligible else None
    if primary:
        for item in blocks:
            if item.id == primary:
                item.relevance = "primary"
                item.selection_reason.insert(0, "primary_initial_long_talking_block")
    ranked = sorted(eligible, key=lambda item: (item.id != primary, -item.confidence, -item.duration_seconds))
    selected: list[DetectedTalkingBlock] = []
    total = 0.0
    config = profile.phase_detection
    for item in ranked:
        if len(selected) >= config.selected_blocks_max_count:
            break
        if selected and total + item.duration_seconds > config.selected_blocks_max_total_seconds:
            continue
        item.selected_for_deep_transcription = True
        selected.append(item)
        total += item.duration_seconds
    for priority, item in enumerate(ranked, 1):
        item.priority = priority
    selection = [
        SelectedTalkingBlock(
            id=item.id, start_seconds=item.start_seconds, end_seconds=item.end_seconds, priority=item.priority
        )
        for item in selected
    ]
    warnings = [] if primary else ["primary_talking_block_not_found"]
    return blocks, selection, primary, warnings


def build_phase_timeline(
    coarse: CoarseTimeline,
    metadata: CoarseVodMetadata,
    profile: AnalysisProfile,
    pipeline_version: str,
    progress=None,
) -> PhaseTimeline:
    raw: list[ClassifiedPhaseWindow] = []
    total = len(coarse.windows)
    for position, window in enumerate(coarse.windows, 1):
        raw.append(classify_window(window, metadata, profile))
        if progress:
            progress("scoring_phase_windows", position, total)
    if progress:
        progress("smoothing_timeline", total, total)
    smoothed = absorb_microsegments(smooth_windows(raw, profile.phase_detection), profile.phase_detection)
    if progress:
        progress("detecting_phase_transitions", total, total)
    segments = merge_segments(smoothed)
    if progress:
        progress("building_talking_blocks", total, total)
    blocks, selected, primary, warnings = build_talking_blocks(segments, profile)
    if progress:
        progress("selecting_conversation_blocks", total, total)
    durations = Counter()
    for segment in segments:
        durations[segment.phase] += segment.end - segment.start
    return PhaseTimeline(
        pipeline_version=pipeline_version,
        source_coarse_pipeline_version=coarse.pipeline_version,
        source_coarse_cache_key=coarse.cache_key,
        phase_cache_key=phase_cache_key(coarse, profile, pipeline_version),
        window_seconds=coarse.window_seconds,
        raw_windows=raw,
        smoothed_windows=smoothed,
        segments=segments,
        talking_blocks=blocks,
        selected_talking_blocks=selected,
        primary_talking_block_id=primary,
        warnings=warnings,
        summary=PhaseSummary(
            waiting_seconds=durations["waiting_or_music"],
            talking_seconds=durations["talking"],
            gameplay_seconds=durations["gameplay"],
            unknown_seconds=durations["unknown"],
        ),
    )
