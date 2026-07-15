from typing import Any


def rejected_candidate_fixture() -> list[dict[str, Any]]:
    return [
        {
            "id": "fragmento-repetitivo-rechazado",
            "start_seconds": 4020,
            "end_seconds": 4300,
            "score": 38,
            "reasons": [
                "below_minimum_candidate_score",
                "extreme_short_duration",
                "repetitive_transcript",
                "previous_context_required",
            ],
        }
    ]


def coarse_timeline_fixture(cache_key: str = "fixture") -> dict[str, Any]:
    kinds = (
        (0.03, 0.97, "", False, 0.01),
        (0.00, 1.00, "", False, 0.00),
        (0.78, 0.22, "Hoy os quería contar una cosa.", True, 0.02),
        (0.42, 0.58, "Vamos a empezar con el juego.", True, 0.31),
    )
    windows = []
    for index, (voice, silence, text, face, motion) in enumerate(kinds):
        start = index * 30
        windows.append(
            {
                "index": index,
                "start": start,
                "end": start + 30,
                "sample_start": start + 10,
                "sample_end": start + 20,
                "audio": {
                    "voice_ratio": voice,
                    "voiced_seconds": voice * 10,
                    "longest_speech_run": voice * 8,
                    "speech_continuity": voice,
                    "number_of_speech_regions": 1 if voice else 0,
                    "longest_silence": silence * 10,
                    "speech_start_delay": 0.5 if voice else None,
                    "speech_end_margin": 0.5 if voice else None,
                    "silence_ratio": silence,
                    "rms_mean": 0.12,
                    "rms_variance": 0.01,
                    "peak_level": 0.6,
                    "dynamic_range": 0.2,
                    "zero_crossing_rate": 0.08,
                    "spectral_flatness": 0.2,
                    "music_likelihood_features": {"energy_continuity": 0.9 if index == 0 else 0.4},
                },
                "transcript_probe": {
                    "attempted": bool(text),
                    "text": text,
                    "word_count": len(text.split()),
                    "words_per_second": len(text.split()) / 10,
                    "language": "es" if text else None,
                    "transcript_quality_score": 0.82 if text else 0,
                    "skip_reason": None if text else "voice_ratio_below_threshold",
                },
                "visual": {
                    "sampled": True,
                    "frame_count": 2,
                    "scene_change_score": motion,
                    "frame_difference": motion,
                    "layout_hint": "facecam_overlay_hint" if face else "no_face",
                    "face_present": face,
                    "face_area_ratio": 0.03 if face else 0,
                    "motion_score": motion,
                },
            }
        )
    return {
        "version": 1,
        "pipeline_version": "fixture-phase2",
        "cache_key": cache_key,
        "window_seconds": 30,
        "audio_sample_seconds": 10,
        "visual_samples_per_window": 2,
        "analyzed_duration_seconds": 120,
        "completed_windows": 4,
        "total_windows": 4,
        "bytes_downloaded": 2_000_000,
        "windows": windows,
        "warnings": [],
    }


def phase_detection_fixture(
    sequence: list[tuple[str, int]] | None = None,
    cache_key: str = "phase-fixture",
) -> dict[str, Any]:
    """Long deterministic coarse timeline used to exercise Phase 3 without media access."""
    sequence = sequence or [
        ("waiting_or_music", 6),
        ("talking", 24),
        ("gameplay", 8),
        ("talking", 22),
        ("unknown", 2),
        ("gameplay", 6),
    ]
    templates = {
        "waiting_or_music": (0.05, 0.04, 0.10, 0.08, 0.01, "no_face", "la la la la"),
        "talking": (
            0.76,
            0.72,
            0.82,
            0.03,
            0.03,
            "fullscreen_camera_hint",
            "Chat, os voy a contar una historia importante.",
        ),
        "gameplay": (
            0.46,
            0.30,
            0.68,
            0.22,
            0.27,
            "facecam_overlay_hint",
            "Vamos a jugar esta partida y abrir el mapa.",
        ),
        "unknown": (0.28, 0.18, 0.25, 0.12, 0.11, "unknown", "Bueno, esto sigue."),
        "failed": (0.0, 0.0, 0.0, 0.0, 0.0, "unknown", ""),
    }
    windows: list[dict[str, Any]] = []
    index = 0
    for phase, count in sequence:
        voice, continuity, quality, scene, motion, layout, text = templates[phase]
        for _ in range(count):
            start = index * 30
            failed = phase == "failed"
            windows.append(
                {
                    "index": index,
                    "start": start,
                    "end": start + 30,
                    "sample_start": start + 10,
                    "sample_end": start + 20,
                    "audio": None
                    if failed
                    else {
                        "voice_ratio": voice,
                        "voiced_seconds": voice * 10,
                        "longest_speech_run": continuity * 8,
                        "speech_continuity": continuity,
                        "number_of_speech_regions": 1 if continuity > 0.4 else 4,
                        "longest_silence": (1 - voice) * 10,
                        "speech_start_delay": 0.4 if voice else None,
                        "speech_end_margin": 0.4 if voice else None,
                        "silence_ratio": 1 - voice,
                        "rms_mean": 0.12,
                        "rms_variance": 0.02,
                        "peak_level": 0.65,
                        "dynamic_range": 0.25 if phase == "gameplay" else 0.10,
                        "zero_crossing_rate": 0.08,
                        "spectral_flatness": 0.20,
                        "music_likelihood_features": {
                            "energy_continuity": 0.92 if phase == "waiting_or_music" else 0.35
                        },
                    },
                    "transcript_probe": None
                    if failed
                    else {
                        "attempted": bool(text),
                        "text": text,
                        "word_count": len(text.split()),
                        "words_per_second": len(text.split()) / 10,
                        "avg_logprob": -0.2,
                        "no_speech_probability": 0.05 if text else 0.9,
                        "language": "es" if text else None,
                        "repeated_text_ratio": 0.65 if phase == "waiting_or_music" else 0.02,
                        "transcript_quality_score": quality,
                        "skip_reason": None if text else "voice_ratio_below_threshold",
                    },
                    "visual": None
                    if failed
                    else {
                        "sampled": layout != "unknown",
                        "frame_count": 2,
                        "scene_change_score": scene,
                        "frame_difference": scene,
                        "layout_hint": layout,
                        "face_present": layout not in {"no_face", "unknown"},
                        "face_area_ratio": 0.08 if layout == "fullscreen_camera_hint" else 0.025,
                        "facecam_position": "top_left" if layout == "facecam_overlay_hint" else None,
                        "motion_score": motion,
                    },
                    "warnings": ["fixture_window_failed"] if failed else [],
                }
            )
            index += 1
    return {
        "version": 1,
        "pipeline_version": "vod-analysis-v2-coarse.1",
        "cache_key": cache_key,
        "window_seconds": 30,
        "audio_sample_seconds": 10,
        "visual_samples_per_window": 2,
        "analyzed_duration_seconds": index * 30,
        "completed_windows": index,
        "total_windows": index,
        "bytes_downloaded": index * 600000,
        "windows": windows,
        "warnings": [],
    }


def illojuan_fixture(source_url: str, platform: str, vod_id: str, pipeline_version: str) -> dict[str, Any]:
    signals = {
        "voice_ratio": 0.08,
        "speech_continuity": 0.05,
        "word_density": 0.1,
        "transcript_quality": 0.12,
        "music_likelihood": 0.91,
        "visual_change_rate": 0.01,
    }
    phases = [
        {
            "start": 0,
            "end": 1410,
            "phase": "waiting_or_music",
            "confidence": 0.89,
            "signals": signals,
            "reasons": ["fixture_music_dominant", "low_speech_continuity"],
        },
        {
            "start": 1410,
            "end": 5070,
            "phase": "talking",
            "confidence": 0.86,
            "signals": {
                "voice_ratio": 0.76,
                "speech_continuity": 0.83,
                "word_density": 2.38,
                "transcript_quality": 0.88,
                "music_likelihood": 0.07,
                "visual_change_rate": 0.03,
            },
            "reasons": ["continuous_speech_detected", "stable_transcription_quality"],
        },
        {
            "start": 5070,
            "end": 7200,
            "phase": "gameplay",
            "confidence": 0.77,
            "signals": {
                "voice_ratio": 0.43,
                "speech_continuity": 0.36,
                "word_density": 1.18,
                "transcript_quality": 0.70,
                "music_likelihood": 0.14,
                "visual_change_rate": 0.31,
            },
            "reasons": ["persistent_visual_layout_change", "speech_pattern_changed"],
        },
    ]
    breakdown_good = {
        "topic_coherence": 0.91,
        "speech_density": 0.88,
        "duration_fit": 0.94,
        "opening_quality": 0.83,
        "closing_quality": 0.86,
        "self_containment": 0.89,
        "title_specificity": 0.93,
        "emotional_energy": 0.71,
        "story_or_opinion_signal": 0.87,
        "penalties": [],
    }
    topics = [
        {
            "start_seconds": 1530,
            "end_seconds": 2250,
            "topic": "expectativas sobre GTA VI",
            "summary": "Comenta el precio esperado y qué tendría que ofrecer el juego.",
            "keywords": ["GTA VI", "precio", "expectativas"],
            "coherence_score": 0.91,
            "boundary_reasons": ["natural_topic_opening", "long_pause_after_conclusion"],
            "transcript": "El chat pregunta por GTA VI y explica qué espera del juego y de su precio.",
        },
        {
            "start_seconds": 2280,
            "end_seconds": 3060,
            "topic": "anécdota en el aeropuerto",
            "summary": "Cuenta una anécdota completa sobre un viaje y su paso por el aeropuerto.",
            "keywords": ["aeropuerto", "viaje", "anécdota"],
            "coherence_score": 0.89,
            "boundary_reasons": ["story_opening", "narrative_resolution"],
            "transcript": (
                "Ayer en el aeropuerto me pasó una cosa... La historia termina al explicar cómo lo resolvió."
            ),
        },
        {
            "start_seconds": 3150,
            "end_seconds": 3900,
            "topic": "crear contenido en directo",
            "summary": "Reflexiona sobre preparar contenido y mantener conversaciones con el chat.",
            "keywords": ["streaming", "chat", "contenido"],
            "coherence_score": 0.84,
            "boundary_reasons": ["explicit_transition", "closing_statement"],
            "transcript": "Explica su opinión sobre preparar un directo y responder al chat.",
        },
    ]
    candidates = [
        {
            "id": "gta-vi-expectativas",
            "exact_start_seconds": 1530,
            "exact_end_seconds": 2250,
            "safe_start_seconds": 1525,
            "safe_end_seconds": 2255,
            "title": "IlloJuan habla sobre el precio y las expectativas de GTA VI",
            "summary": (
                "IlloJuan responde al chat sobre cuánto podría costar GTA VI y qué espera del juego. "
                "La conversación tiene una introducción clara y una conclusión natural."
            ),
            "keywords": ["IlloJuan", "GTA VI", "precio"],
            "score": 88,
            "score_breakdown": breakdown_good,
            "transcript_preview": (
                "A ver, con GTA VI yo creo que la pregunta no es sólo cuánto va a costar..."
            ),
            "warnings": [],
            "overlap_ratio": 0,
        },
        {
            "id": "anecdota-aeropuerto",
            "exact_start_seconds": 2280,
            "exact_end_seconds": 3060,
            "safe_start_seconds": 2275,
            "safe_end_seconds": 3065,
            "title": "La anécdota de IlloJuan en el aeropuerto",
            "summary": (
                "Una historia autocontenida sobre un incidente durante un viaje. "
                "Funciona como clip por su estructura narrativa y su remate."
            ),
            "keywords": ["IlloJuan", "aeropuerto", "viaje"],
            "score": 84,
            "score_breakdown": {**breakdown_good, "emotional_energy": 0.79},
            "transcript_preview": "Ayer en el aeropuerto me pasó una cosa que no me había ocurrido nunca...",
            "warnings": [],
            "overlap_ratio": 0,
        },
        {
            "id": "contenido-y-chat",
            "exact_start_seconds": 3150,
            "exact_end_seconds": 3900,
            "safe_start_seconds": 3145,
            "safe_end_seconds": 3905,
            "title": "Cómo plantea IlloJuan sus conversaciones con el chat",
            "summary": (
                "Reflexiona sobre la preparación de los directos y por qué una charla necesita "
                "espacio para desarrollarse."
            ),
            "keywords": ["IlloJuan", "streaming", "chat"],
            "score": 78,
            "score_breakdown": {**breakdown_good, "emotional_energy": 0.58},
            "transcript_preview": "Yo no preparo una conversación como si fuera un guion cerrado...",
            "warnings": ["fixture_transcript_is_synthetic"],
            "overlap_ratio": 0,
        },
    ]
    return {
        "pipeline_version": pipeline_version,
        "fixture": True,
        "vod": {
            "platform": platform,
            "vod_id": vod_id,
            "title": "Fixture: charla inicial de IlloJuan",
            "uploader": "IlloJuan",
            "duration_seconds": 14400,
            "webpage_url": source_url,
        },
        "phases": phases,
        "analysis": {
            "talking_start_seconds": 1410,
            "talking_end_seconds": 5070,
            "confidence": 0.82,
            "start_reasons": [
                "continuous_speech_detected",
                "high_word_density",
                "stable_transcription_quality",
            ],
            "end_reasons": ["persistent_visual_layout_change", "speech_pattern_changed"],
        },
        "topics": topics,
        "candidates": candidates,
        "timings": {"fixture_load_seconds": 0.01},
        "warnings": ["Phase 1 fixture mode: no media was downloaded or transcribed."],
    }
