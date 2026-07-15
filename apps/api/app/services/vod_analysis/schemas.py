from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator, model_validator

PhaseName = Literal["waiting_or_music", "talking", "gameplay", "unknown"]
LayoutState = Literal["no_face", "fullscreen_face", "small_facecam", "unknown"]
AnalysisStatus = Literal["queued", "processing", "completed", "failed"]


class VodAnalysisCreate(BaseModel):
    url: HttpUrl
    streamer: Literal["illojuan"] = "illojuan"
    force_reanalyze: bool = False

    @field_validator("url")
    @classmethod
    def supported_vod_url(cls, value: HttpUrl) -> HttpUrl:
        host = (value.host or "").lower()
        twitch = host in {"twitch.tv", "www.twitch.tv", "m.twitch.tv"} and "/videos/" in value.path
        youtube = host in {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"}
        if not twitch and not youtube:
            raise ValueError("Enter a Twitch VOD or YouTube video URL")
        return value


class PhaseSignals(BaseModel):
    voice_ratio: float = Field(ge=0, le=1)
    speech_continuity: float = Field(ge=0, le=1)
    word_density: float = Field(ge=0)
    transcript_quality: float = Field(ge=0, le=1)
    music_likelihood: float = Field(ge=0, le=1)
    visual_change_rate: float = Field(ge=0)


class PhaseWindow(BaseModel):
    start: float = Field(ge=0)
    end: float = Field(gt=0)
    phase: PhaseName
    confidence: float = Field(ge=0, le=1)
    signals: PhaseSignals
    reasons: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def ordered(self) -> "PhaseWindow":
        if self.end <= self.start:
            raise ValueError("Phase window end must be after start")
        return self


class ScoreBreakdown(BaseModel):
    topic_coherence: float = Field(ge=0, le=1)
    speech_density: float = Field(ge=0, le=1)
    duration_fit: float = Field(ge=0, le=1)
    opening_quality: float = Field(ge=0, le=1)
    closing_quality: float = Field(ge=0, le=1)
    self_containment: float = Field(ge=0, le=1)
    title_specificity: float = Field(ge=0, le=1)
    emotional_energy: float = Field(ge=0, le=1)
    story_or_opinion_signal: float = Field(ge=0, le=1)
    penalties: list[str] = Field(default_factory=list)


class ClipCandidate(BaseModel):
    id: str
    exact_start_seconds: float = Field(ge=0)
    exact_end_seconds: float = Field(gt=0)
    safe_start_seconds: float = Field(ge=0)
    safe_end_seconds: float = Field(gt=0)
    title: str = Field(min_length=1, max_length=100)
    summary: str = Field(min_length=1, max_length=1000)
    keywords: list[str]
    score: float = Field(ge=0, le=100)
    score_breakdown: ScoreBreakdown
    transcript_preview: str
    warnings: list[str] = Field(default_factory=list)
    overlap_ratio: float = Field(default=0, ge=0, le=1)


class TopicBlock(BaseModel):
    start_seconds: float
    end_seconds: float
    topic: str
    summary: str
    keywords: list[str]
    coherence_score: float = Field(ge=0, le=1)
    boundary_reasons: list[str]
    transcript: str


class TalkingBlock(BaseModel):
    talking_start_seconds: float
    talking_end_seconds: float
    confidence: float = Field(ge=0, le=1)
    start_reasons: list[str]
    end_reasons: list[str]


class VodMetadata(BaseModel):
    platform: Literal["twitch", "youtube"]
    vod_id: str
    title: str
    uploader: str
    duration_seconds: float
    webpage_url: str


class VodAnalysisResult(BaseModel):
    pipeline_version: str
    fixture: bool
    vod: VodMetadata
    phases: list[PhaseWindow]
    analysis: TalkingBlock
    topics: list[TopicBlock]
    candidates: list[ClipCandidate] = Field(max_length=10)
    timings: dict[str, float] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


class VodAnalysisStartResponse(BaseModel):
    job_id: str
    cached: bool


class VodAnalysisJobResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    source_url: str
    streamer_profile: str
    pipeline_version: str
    phase_detection_strategy: str = "legacy_heuristic"
    requires_coarse_timeline: bool = True
    status: AnalysisStatus
    stage: str
    progress: int = Field(ge=0, le=100)
    cached: bool
    fixture_mode: bool
    warnings: list[str]
    result: VodAnalysisResult | PhasedAnalysisResult | CoarseAnalysisResult | None
    error_message: str | None = None
    completed_windows: int = 0
    total_windows: int = 0
    current_timestamp: float = 0
    created_at: datetime
    updated_at: datetime


class AnalysisProfileResponse(BaseModel):
    id: str
    display_name: str
    language: str


class AudioSignals(BaseModel):
    voice_ratio: float = Field(ge=0, le=1)
    voiced_seconds: float = Field(ge=0)
    longest_speech_run: float = Field(ge=0)
    speech_continuity: float = Field(ge=0, le=1)
    number_of_speech_regions: int = Field(ge=0)
    longest_silence: float = Field(ge=0)
    speech_start_delay: float | None = Field(default=None, ge=0)
    speech_end_margin: float | None = Field(default=None, ge=0)
    silence_ratio: float = Field(ge=0, le=1)
    rms_mean: float = Field(ge=0)
    rms_variance: float = Field(ge=0)
    peak_level: float = Field(ge=0)
    dynamic_range: float = Field(ge=0)
    zero_crossing_rate: float = Field(ge=0, le=1)
    spectral_flatness: float = Field(ge=0, le=1)
    music_likelihood_features: dict[str, float] = Field(default_factory=dict)


class TranscriptProbe(BaseModel):
    attempted: bool
    text: str = ""
    word_count: int = Field(default=0, ge=0)
    words_per_second: float = Field(default=0, ge=0)
    avg_logprob: float | None = None
    no_speech_probability: float | None = Field(default=None, ge=0, le=1)
    language: str | None = None
    repeated_text_ratio: float = Field(default=0, ge=0, le=1)
    transcript_quality_score: float = Field(default=0, ge=0, le=1)
    skip_reason: str | None = None


class VisualSignals(BaseModel):
    sampled: bool
    frame_count: int = Field(default=0, ge=0)
    scene_change_score: float = Field(default=0, ge=0)
    frame_difference: float = Field(default=0, ge=0)
    layout_hint: str = "unknown"
    face_present: bool = False
    face_area_ratio: float = Field(default=0, ge=0, le=1)
    facecam_position: str | None = None
    motion_score: float = Field(default=0, ge=0)
    warning: str | None = None


class CoarseWindow(BaseModel):
    index: int = Field(ge=0)
    start: float = Field(ge=0)
    end: float = Field(gt=0)
    sample_start: float = Field(ge=0)
    sample_end: float = Field(gt=0)
    audio: AudioSignals | None = None
    transcript_probe: TranscriptProbe | None = None
    visual: VisualSignals | None = None
    warnings: list[str] = Field(default_factory=list)
    bytes_downloaded: int = Field(default=0, ge=0)


class CoarseTimeline(BaseModel):
    version: int = 1
    pipeline_version: str
    cache_key: str
    window_seconds: int
    audio_sample_seconds: float
    visual_samples_per_window: int
    analyzed_duration_seconds: float
    completed_windows: int
    total_windows: int
    bytes_downloaded: int = 0
    windows: list[CoarseWindow]
    warnings: list[str] = Field(default_factory=list)


class CoarseVodMetadata(BaseModel):
    platform: Literal["twitch", "youtube"]
    extractor: str
    vod_id: str
    title: str
    uploader: str | None = None
    channel: str | None = None
    duration_seconds: float
    chapters: list[dict] = Field(default_factory=list)
    original_url: str
    availability: str | None = None
    audio_formats: list[dict] = Field(default_factory=list)
    video_formats: list[dict] = Field(default_factory=list)


class CoarseAnalysisResult(BaseModel):
    pipeline_version: str
    fixture: Literal[False] = False
    phase: Literal["coarse_signals"] = "coarse_signals"
    vod: CoarseVodMetadata
    coarse_timeline: CoarseTimeline
    warnings: list[str] = Field(default_factory=list)


class PhaseScores(BaseModel):
    waiting_or_music: float = Field(ge=0, le=1)
    talking: float = Field(ge=0, le=1)
    gameplay: float = Field(ge=0, le=1)
    unknown: float = Field(ge=0, le=1)


class ClassifiedPhaseWindow(BaseModel):
    index: int = Field(ge=0)
    start: float = Field(ge=0)
    end: float = Field(gt=0)
    raw_phase: PhaseName
    raw_confidence: float = Field(ge=0, le=1)
    phase: PhaseName
    confidence: float = Field(ge=0, le=1)
    phase_scores: PhaseScores
    reasons: list[str] = Field(default_factory=list)
    smoothing_reasons: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class PhaseSegment(BaseModel):
    start: float = Field(ge=0)
    end: float = Field(gt=0)
    phase: PhaseName
    confidence: float = Field(ge=0, le=1)
    window_count: int = Field(ge=1)
    reasons: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    transition_in: str | None = None
    transition_out: str | None = None


class DetectedTalkingBlock(BaseModel):
    id: str
    start_seconds: float = Field(ge=0)
    end_seconds: float = Field(gt=0)
    duration_seconds: float = Field(gt=0)
    confidence: float = Field(ge=0, le=1)
    priority: int = Field(ge=1)
    relevance: Literal["primary", "secondary", "low_priority", "ignored"]
    selected_for_deep_transcription: bool = False
    selection_reason: list[str] = Field(default_factory=list)
    end_transition: Literal[
        "gameplay_transition",
        "unknown_transition",
        "end_of_analysis",
        "low_confidence_transition",
        "other_transition",
    ]
    warnings: list[str] = Field(default_factory=list)


class SelectedTalkingBlock(BaseModel):
    id: str
    start_seconds: float
    end_seconds: float
    priority: int


class PhaseSummary(BaseModel):
    waiting_seconds: float = 0
    talking_seconds: float = 0
    gameplay_seconds: float = 0
    unknown_seconds: float = 0


class PhaseTimeline(BaseModel):
    version: int = 1
    pipeline_version: str
    phase_detection_strategy: Literal["profile_layout_match", "visual_layout", "legacy_heuristic"] = (
        "legacy_heuristic"
    )
    requires_coarse_timeline: bool = True
    source_coarse_pipeline_version: str | None = None
    source_coarse_cache_key: str | None = None
    phase_cache_key: str
    window_seconds: int
    raw_windows: list[ClassifiedPhaseWindow]
    smoothed_windows: list[ClassifiedPhaseWindow]
    segments: list[PhaseSegment]
    talking_blocks: list[DetectedTalkingBlock]
    selected_talking_blocks: list[SelectedTalkingBlock]
    primary_talking_block_id: str | None = None
    warnings: list[str] = Field(default_factory=list)
    summary: PhaseSummary


class LayoutFrameSample(BaseModel):
    index: int = Field(ge=0)
    frame_timestamp: float = Field(ge=0)
    layout: LayoutState
    layout_id: str = "legacy_unknown"
    phase: PhaseName
    confidence: float = Field(ge=0, le=1)
    match_score: float = Field(default=0, ge=0, le=1)
    second_best_score: float = Field(default=0, ge=0, le=1)
    score_margin: float = Field(default=0, ge=0, le=1)
    matched_reference: str | None = None
    face_area_ratio: float = Field(ge=0, le=1)
    face_position: str | None = None
    face_box: dict[str, int] | None = None
    signals: dict[str, float] = Field(default_factory=dict)
    background_region_scores: dict[str, float] = Field(default_factory=dict)
    reasons: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class LayoutSegment(BaseModel):
    start: float = Field(ge=0)
    end: float = Field(gt=0)
    layout: LayoutState
    layout_id: str = "legacy_unknown"
    phase: PhaseName
    confidence: float = Field(ge=0, le=1)
    match_score: float = Field(default=0, ge=0, le=1)
    second_best_score: float = Field(default=0, ge=0, le=1)
    score_margin: float = Field(default=0, ge=0, le=1)
    sample_count: int = Field(ge=1)
    reasons: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class LayoutTimeline(BaseModel):
    version: int = 1
    pipeline_version: str
    cache_key: str
    phase_detection_strategy: Literal["profile_layout_match", "visual_layout"] = "profile_layout_match"
    requires_coarse_timeline: Literal[False] = False
    source_coarse_cache_key: str | None = None
    sample_seconds: float
    transition_confirmation: int
    analyzed_duration_seconds: float
    completed_samples: int
    total_samples: int
    raw_samples: list[LayoutFrameSample]
    smoothed_samples: list[LayoutFrameSample]
    segments: list[LayoutSegment]
    warnings: list[str] = Field(default_factory=list)


class PhasedAnalysisResult(BaseModel):
    pipeline_version: str
    fixture: bool = False
    phase: Literal["visual_layout"] = "visual_layout"
    phase_detection_strategy: Literal["profile_layout_match", "visual_layout"] = "profile_layout_match"
    requires_coarse_timeline: Literal[False] = False
    vod: CoarseVodMetadata
    coarse_timeline: CoarseTimeline | None = None
    phase_timeline: PhaseTimeline
    talking_blocks: list[DetectedTalkingBlock]
    selected_talking_blocks: list[SelectedTalkingBlock]
    primary_talking_block_id: str | None = None
    phase_summary: PhaseSummary
    layout_timeline: LayoutTimeline
    warnings: list[str] = Field(default_factory=list)


class ValidationNotes(BaseModel):
    talking_start: float | None = Field(default=None, ge=0)
    talking_end: float | None = Field(default=None, ge=0)
    gameplay_start: float | None = Field(default=None, ge=0)
    gameplay_end: float | None = Field(default=None, ge=0)
    talking_block_2_start: float | None = Field(default=None, ge=0)
    talking_block_2_end: float | None = Field(default=None, ge=0)
    talking_block_3_start: float | None = Field(default=None, ge=0)
    talking_block_3_end: float | None = Field(default=None, ge=0)


class ValidationComparison(BaseModel):
    transition: str
    detector_seconds: float | None = None
    actual_seconds: float
    error_seconds: float | None = None
    absolute_error_seconds: float | None = None


class ValidationMetrics(BaseModel):
    mean_absolute_error_seconds: float | None = None
    maximum_absolute_error_seconds: float | None = None
    mean_error_by_transition: dict[str, float] = Field(default_factory=dict)
    detected_phase_count: int
    omitted_phase_count: int
    false_detection_count: int
    mean_confidence: float


class InspectorSegment(BaseModel):
    start: float
    end: float
    phase: PhaseName
    confidence: float
    layout_id: str | None = None
    match_score: float | None = None
    second_best_score: float | None = None
    score_margin: float | None = None
    reasons: list[str]
    warnings: list[str]
    open_url: str


class VodInspectorResponse(BaseModel):
    job_id: str
    source_url: str
    streamer_profile: str
    status: AnalysisStatus
    stage: str
    progress: int
    error_message: str | None = None
    cached: bool
    phase_detection_strategy: str = "legacy_heuristic"
    requires_coarse_timeline: bool = True
    metadata: CoarseVodMetadata | VodMetadata | None = None
    phase_timeline: PhaseTimeline | None = None
    segments: list[InspectorSegment] = Field(default_factory=list)
    validation_notes: ValidationNotes = Field(default_factory=ValidationNotes)
    comparisons: list[ValidationComparison] = Field(default_factory=list)
    metrics: ValidationMetrics | None = None
    export_url: str | None = None


VodAnalysisJobResponse.model_rebuild()
