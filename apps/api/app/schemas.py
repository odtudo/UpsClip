from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator, model_validator

OutputFormat = Literal["horizontal", "vertical"]
PrivacyStatus = Literal["private", "unlisted", "public"]


class JobCreate(BaseModel):
    source_url: HttpUrl
    start: str
    end: str
    remove_silences: bool = True
    normalize_audio: bool = True
    generate_subtitles: bool = False
    output_format: OutputFormat = "horizontal"
    smart_vertical_layout: bool = True
    streamer_profile: str = "auto"
    demo: bool = False
    youtube_title: str | None = Field(default=None, min_length=1, max_length=100)

    @model_validator(mode="after")
    def require_vertical_subtitles(self) -> "JobCreate":
        if self.output_format == "vertical":
            self.generate_subtitles = True
        else:
            self.smart_vertical_layout = False
            self.streamer_profile = "auto"
        return self

    @field_validator("streamer_profile")
    @classmethod
    def safe_profile_id(cls, value: str) -> str:
        import re

        if value != "auto" and not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", value):
            raise ValueError("Invalid streamer profile id")
        return value

    @field_validator("source_url")
    @classmethod
    def require_twitch(cls, value: HttpUrl) -> HttpUrl:
        host = (value.host or "").lower()
        if host not in {"twitch.tv", "www.twitch.tv", "m.twitch.tv"}:
            raise ValueError("Only Twitch VOD URLs are supported")
        if "/videos/" not in value.path:
            raise ValueError("Enter a Twitch VOD URL such as https://www.twitch.tv/videos/123")
        return value


class YouTubeUploadRequest(BaseModel):
    title: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=5000)
    tags: list[str] = Field(default_factory=list, max_length=50)
    privacy_status: PrivacyStatus = "private"

    @field_validator("tags")
    @classmethod
    def clean_tags(cls, value: list[str]) -> list[str]:
        return [tag.strip()[:100] for tag in value if tag.strip()]


class JobResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    source_url: str
    start_seconds: int
    end_seconds: int
    remove_silences: bool
    normalize_audio: bool
    generate_subtitles: bool
    output_format: OutputFormat
    smart_vertical_layout: bool = False
    streamer_profile: str = "auto"
    resolved_streamer_profile: str | None = None
    layout_warnings: list[dict] = Field(default_factory=list)
    layout_summary: dict = Field(default_factory=dict)
    demo: bool
    status: str
    progress: int
    current_step: str
    error_message: str | None = None
    source_title: str | None = None
    rendered_duration: float | None = None
    rendered_size: int | None = None
    youtube_title: str | None = None
    youtube_description: str | None = None
    tags: list[str] = Field(default_factory=list)
    privacy_status: PrivacyStatus = "private"
    youtube_video_id: str | None = None
    youtube_url: str | None = None
    video_url: str | None = None
    created_at: datetime
    updated_at: datetime


class HealthResponse(BaseModel):
    status: str
    ffmpeg_available: bool
    ffprobe_available: bool
    ytdlp_available: bool
    youtube_configured: bool
    demo_mode: bool


class SetupStatusResponse(BaseModel):
    ffmpeg_available: bool
    ffprobe_available: bool
    ytdlp_available: bool
    data_writable: bool
    youtube_client_secret_present: bool
    youtube_token_present: bool
    youtube_token_usable: bool
    youtube_ready: bool
    twitch_cookies_present: bool
    database_accessible: bool
    face_detector_name: str
    face_detector_available: bool
    face_detector_model_present: bool
    face_detector_model_valid: bool
    smart_vertical_available: bool
    smart_vertical_ready: bool
    messages: list[str] = Field(default_factory=list)


class StreamerProfileResponse(BaseModel):
    id: str
    display_name: str
