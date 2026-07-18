from functools import lru_cache
from pathlib import Path

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(REPOSITORY_ROOT / ".env",),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    api_host: str = "127.0.0.1"
    api_port: int = 8000
    data_dir: Path = REPOSITORY_ROOT / "data"
    database_url: str | None = None
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    max_clip_duration_seconds: int = 1800
    download_margin_seconds: float = 5.0
    ffmpeg_path: str = "ffmpeg"
    ffprobe_path: str = "ffprobe"
    ytdlp_path: str = "yt-dlp"
    video_crf: int = 22
    video_preset: str = "fast"

    silence_min_seconds: float = 1.2
    silence_remove_after_seconds: float = 2.5
    silence_padding_seconds: float = 0.2
    whisper_model: str = "small"
    whisper_device: str = "auto"
    whisper_compute_type: str = "auto"
    whisper_language: str = "auto"

    vod_analysis_fixture_mode: bool = False
    vod_analysis_pipeline_version: str = "vod-analysis-v2-coarse.1"
    vod_analysis_phase_pipeline_version: str = "vod-analysis-profile-layout.2"
    vod_analysis_minimum_candidate_score: int = 55
    vod_analysis_debug: bool = False
    validation_debug: bool = False
    layout_sample_seconds: float = 2.0
    layout_transition_confirmation: int = 3
    visual_layout_profile_path: Path = REPOSITORY_ROOT / "data/profiles/illojuan_visual.json"
    vod_analysis_window_seconds: int = 30
    vod_analysis_audio_sample_seconds: float = 10.0
    vod_analysis_visual_samples_per_window: int = 2
    vod_analysis_fetch_block_seconds: int = 900
    vod_analysis_max_seconds: int = 10800
    vod_analysis_probe_model: str = "tiny"
    vod_analysis_probe_voice_ratio: float = 0.20
    vod_analysis_probe_min_speech_seconds: float = 2.0
    vod_analysis_sample_timeout_seconds: int = 90
    vod_topic_analysis_pipeline_version: str = "vod-topic-analysis-v1.1-grounded"
    vod_topic_analysis_max_seconds: int = 7200
    whisper_analysis_model: str = "medium"
    transcription_chunk_seconds: int = 1800
    transcription_overlap_seconds: int = 15
    vod_topic_audio_timeout_seconds: int = 900
    semantic_embedding_model: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    semantic_window_min_seconds: int = 30
    semantic_window_target_seconds: int = 60
    semantic_window_max_seconds: int = 90
    topic_min_seconds: int = 300
    topic_target_seconds: int = 720
    topic_max_seconds: int = 1500
    candidate_min_seconds: int = 300
    candidate_target_min_seconds: int = 480
    candidate_target_max_seconds: int = 900
    candidate_max_seconds: int = 1200
    candidate_context_margin_seconds: float = 5.0
    vod_topic_max_candidates: int = 10

    smart_vertical_layout_default: bool = True
    scene_detection_enabled: bool = True
    scene_change_threshold: float = 0.08
    scene_min_duration_seconds: float = 1.5
    scene_sample_fps: float = 2.0
    face_detection_sample_fps: float = 2.0
    face_analysis_max_width: int = 1280
    face_detector_model_path: Path = (
        REPOSITORY_ROOT / "data/models/face_detection/face_detection_yunet_2023mar.onnx"
    )
    face_detector_score_threshold: float = 0.55
    face_detector_profile_threshold: float = 0.40
    face_detector_nms_threshold: float = 0.30
    face_detector_top_k: int = 5000
    face_detector_haar_fallback: bool = True
    face_layout_min_confidence: float = 0.60
    fullscreen_face_area_threshold: float = 0.025
    facecam_max_face_area_threshold: float = 0.06
    face_stability_position_tolerance: float = 0.04
    face_stability_size_tolerance: float = 0.20
    layout_min_segment_seconds: float = 1.5
    layout_merge_iou_threshold: float = 0.70
    layout_merge_center_distance_ratio: float = 0.05
    facebox_expand_left: float = 0.80
    facebox_expand_right: float = 0.80
    facebox_expand_top: float = 0.55
    facebox_expand_bottom: float = 1.60
    vertical_facecam_height_ratio: float = 0.38
    vertical_output_width: int = 1080
    vertical_output_height: int = 1920
    vertical_divider_height: int = 4
    smart_layout_debug: bool = False

    youtube_client_secrets_path: Path = REPOSITORY_ROOT / "data/credentials/client_secret.json"
    youtube_token_path: Path = REPOSITORY_ROOT / "data/credentials/token.json"
    twitch_cookies_path: Path | None = None
    demo_mode: bool = False
    log_level: str = "INFO"

    @field_validator(
        "data_dir",
        "youtube_client_secrets_path",
        "youtube_token_path",
        "face_detector_model_path",
        "visual_layout_profile_path",
        mode="after",
    )
    @classmethod
    def make_absolute(cls, value: Path) -> Path:
        return value if value.is_absolute() else (REPOSITORY_ROOT / value).resolve()

    @field_validator("twitch_cookies_path", mode="after")
    @classmethod
    def make_optional_path_absolute(cls, value: Path | None) -> Path | None:
        if value is None:
            return None
        return value if value.is_absolute() else (REPOSITORY_ROOT / value).resolve()

    @property
    def database_path(self) -> Path:
        if self.database_url and self.database_url.startswith("sqlite:///"):
            raw = Path(self.database_url.removeprefix("sqlite:///"))
            return raw if raw.is_absolute() else (REPOSITORY_ROOT / raw).resolve()
        return self.data_dir / "app.db"

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @model_validator(mode="after")
    def validate_vod_analysis_sampling(self) -> "Settings":
        if not 10 <= self.vod_analysis_window_seconds <= 300:
            raise ValueError("VOD_ANALYSIS_WINDOW_SECONDS must be between 10 and 300")
        if not 0 < self.vod_analysis_audio_sample_seconds <= self.vod_analysis_window_seconds:
            raise ValueError("VOD_ANALYSIS_AUDIO_SAMPLE_SECONDS must fit inside a window")
        if not 0 <= self.vod_analysis_visual_samples_per_window <= 3:
            raise ValueError("VOD_ANALYSIS_VISUAL_SAMPLES_PER_WINDOW must be between 0 and 3")
        if self.vod_analysis_fetch_block_seconds < self.vod_analysis_window_seconds:
            raise ValueError("VOD_ANALYSIS_FETCH_BLOCK_SECONDS must contain a window")
        if not 0 <= self.vod_analysis_probe_voice_ratio <= 1:
            raise ValueError("VOD_ANALYSIS_PROBE_VOICE_RATIO must be between 0 and 1")
        if self.vod_analysis_max_seconds <= 0:
            raise ValueError("VOD_ANALYSIS_MAX_SECONDS must be positive")
        if not 0.5 <= self.layout_sample_seconds <= 30:
            raise ValueError("LAYOUT_SAMPLE_SECONDS must be between 0.5 and 30")
        if not 1 <= self.layout_transition_confirmation <= 20:
            raise ValueError("LAYOUT_TRANSITION_CONFIRMATION must be between 1 and 20")
        if self.vod_topic_analysis_max_seconds <= 0:
            raise ValueError("VOD_TOPIC_ANALYSIS_MAX_SECONDS must be positive")
        if self.transcription_chunk_seconds < 60:
            raise ValueError("TRANSCRIPTION_CHUNK_SECONDS must be at least 60")
        if not 0 <= self.transcription_overlap_seconds < self.transcription_chunk_seconds / 2:
            raise ValueError("TRANSCRIPTION_OVERLAP_SECONDS must be non-negative and below half a chunk")
        if not (
            10
            <= self.semantic_window_min_seconds
            <= self.semantic_window_target_seconds
            <= self.semantic_window_max_seconds
        ):
            raise ValueError("Semantic window durations must be ordered")
        if not (self.topic_min_seconds <= self.topic_target_seconds <= self.topic_max_seconds):
            raise ValueError("Topic durations must be ordered")
        if not (
            self.candidate_min_seconds
            <= self.candidate_target_min_seconds
            <= self.candidate_target_max_seconds
            <= self.candidate_max_seconds
        ):
            raise ValueError("Candidate durations must be ordered")
        return self

    def ensure_directories(self) -> None:
        for child in (
            "downloads",
            "work",
            "rendered",
            "subtitles",
            "thumbnails",
            "credentials",
            "logs",
            "models",
            "models/face_detection",
            "profiles",
            "smoke_tests",
            "analysis",
            "analysis/topic_cache",
        ):
            (self.data_dir / child).mkdir(parents=True, exist_ok=True)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    return Settings()
