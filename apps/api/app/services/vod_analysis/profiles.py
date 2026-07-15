from pydantic import BaseModel, Field, model_validator


class PhaseDetectionConfig(BaseModel):
    """Explainable Phase 3 thresholds and weights for one streamer profile."""

    talking_min_voice_ratio: float = Field(ge=0, le=1)
    talking_min_speech_continuity: float = Field(ge=0, le=1)
    talking_min_transcript_quality: float = Field(ge=0, le=1)
    talking_min_word_density: float = Field(ge=0)
    gameplay_min_motion_score: float = Field(ge=0)
    gameplay_min_scene_change_score: float = Field(ge=0)
    waiting_max_voice_ratio: float = Field(ge=0, le=1)
    raw_phase_min_confidence: float = Field(ge=0, le=1)
    raw_phase_min_margin: float = Field(ge=0, le=1)
    smoothing_radius_windows: int = Field(ge=1, le=5)
    waiting_min_segment_seconds: int = Field(ge=30)
    gameplay_min_segment_seconds: int = Field(ge=30)
    microsegment_max_seconds: int = Field(ge=0)
    selected_blocks_max_count: int = Field(ge=1, le=20)
    selected_blocks_max_total_seconds: int = Field(ge=600)
    weights: dict[str, float]
    transition_penalties: dict[str, float]

    @model_validator(mode="after")
    def validate_weight_sets(self) -> "PhaseDetectionConfig":
        required = {
            "talking_voice",
            "talking_continuity",
            "talking_transcript",
            "talking_words",
            "talking_spanish",
            "talking_face",
            "talking_low_motion",
            "talking_repetition_penalty",
            "waiting_low_voice",
            "waiting_silence",
            "waiting_repetition",
            "waiting_music",
            "waiting_no_face",
            "waiting_stable_visual",
            "gameplay_motion",
            "gameplay_scene",
            "gameplay_overlay",
            "gameplay_dynamics",
            "gameplay_fragmented_speech",
        }
        if set(self.weights) != required or any(value < 0 for value in self.weights.values()):
            raise ValueError("Phase classifier weights are incomplete or invalid")
        if any(value < 0 for value in self.transition_penalties.values()):
            raise ValueError("Phase transition penalties must be non-negative")
        return self


class AnalysisProfile(BaseModel):
    id: str
    display_name: str
    language: str
    max_initial_analysis_seconds: int = Field(gt=0)
    expected_music_intro_min_seconds: int = Field(ge=0)
    expected_music_intro_max_seconds: int = Field(gt=0)
    sustained_talking_seconds: int = Field(ge=180)
    minimum_talking_block_seconds: int = Field(ge=300)
    maximum_talking_analysis_seconds: int = Field(ge=600)
    candidate_min_duration_seconds: int = Field(ge=60)
    candidate_target_min_seconds: int = Field(ge=60)
    candidate_target_max_seconds: int = Field(ge=60)
    candidate_max_duration_seconds: int = Field(ge=60)
    candidate_context_margin_seconds: int = Field(ge=0, le=60)
    phase_window_seconds: int = Field(ge=10, le=120)
    phase_order: list[str]
    phase_detection: PhaseDetectionConfig

    @model_validator(mode="after")
    def validate_ranges(self) -> "AnalysisProfile":
        if self.expected_music_intro_max_seconds < self.expected_music_intro_min_seconds:
            raise ValueError("Invalid intro range")
        durations = (
            self.candidate_min_duration_seconds,
            self.candidate_target_min_seconds,
            self.candidate_target_max_seconds,
            self.candidate_max_duration_seconds,
        )
        if tuple(sorted(durations)) != durations:
            raise ValueError("Candidate durations must be ordered")
        if self.phase_order != ["waiting_or_music", "talking", "gameplay"]:
            raise ValueError("IlloJuan phase order is invalid")
        return self


ILLOJUAN = AnalysisProfile(
    id="illojuan",
    display_name="IlloJuan",
    language="es",
    max_initial_analysis_seconds=10800,
    expected_music_intro_min_seconds=60,
    expected_music_intro_max_seconds=3600,
    sustained_talking_seconds=240,
    minimum_talking_block_seconds=600,
    maximum_talking_analysis_seconds=7200,
    candidate_min_duration_seconds=480,
    candidate_target_min_seconds=600,
    candidate_target_max_seconds=900,
    candidate_max_duration_seconds=1200,
    candidate_context_margin_seconds=5,
    phase_window_seconds=30,
    phase_order=["waiting_or_music", "talking", "gameplay"],
    phase_detection=PhaseDetectionConfig(
        talking_min_voice_ratio=0.35,
        talking_min_speech_continuity=0.40,
        talking_min_transcript_quality=0.45,
        talking_min_word_density=0.45,
        gameplay_min_motion_score=0.18,
        gameplay_min_scene_change_score=0.16,
        waiting_max_voice_ratio=0.20,
        raw_phase_min_confidence=0.43,
        raw_phase_min_margin=0.07,
        smoothing_radius_windows=2,
        waiting_min_segment_seconds=90,
        gameplay_min_segment_seconds=120,
        microsegment_max_seconds=60,
        selected_blocks_max_count=6,
        selected_blocks_max_total_seconds=14400,
        weights={
            "talking_voice": 0.24,
            "talking_continuity": 0.18,
            "talking_transcript": 0.18,
            "talking_words": 0.12,
            "talking_spanish": 0.06,
            "talking_face": 0.10,
            "talking_low_motion": 0.12,
            "talking_repetition_penalty": 0.18,
            "waiting_low_voice": 0.28,
            "waiting_silence": 0.20,
            "waiting_repetition": 0.12,
            "waiting_music": 0.18,
            "waiting_no_face": 0.10,
            "waiting_stable_visual": 0.12,
            "gameplay_motion": 0.26,
            "gameplay_scene": 0.20,
            "gameplay_overlay": 0.22,
            "gameplay_dynamics": 0.14,
            "gameplay_fragmented_speech": 0.18,
        },
        transition_penalties={
            "same": 0.0,
            "unknown": 0.05,
            "common": 0.10,
            "waiting_gameplay": 0.20,
            "gameplay_waiting": 0.24,
        },
    ),
)

PROFILES = {ILLOJUAN.id: ILLOJUAN}


def get_analysis_profile(profile_id: str) -> AnalysisProfile:
    try:
        return PROFILES[profile_id]
    except KeyError as exc:
        raise ValueError(f"Unsupported analysis profile: {profile_id}") from exc
