import logging
import shutil
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from .config import Settings, get_settings
from .database import JobStore, VodAnalysisStore, safe_data_path
from .schemas import (
    HealthResponse,
    JobCreate,
    JobResponse,
    SetupStatusResponse,
    StreamerProfileResponse,
    YouTubeUploadRequest,
)
from .services.setup_status import get_setup_status
from .services.smart_vertical.profiles import ProfileValidationError, list_profiles, load_profile
from .services.vod_analysis.cache import parse_source_identity
from .services.vod_analysis.layout_detection import layout_cache_key
from .services.vod_analysis.profiles import PROFILES, get_analysis_profile
from .services.vod_analysis.schemas import (
    AnalysisProfileResponse,
    ValidationNotes,
    VodAnalysisCreate,
    VodAnalysisJobResponse,
    VodAnalysisStartResponse,
    VodInspectorResponse,
)
from .services.vod_analysis.topic_cache import topic_cache_keys
from .services.vod_inspector import export_report, prepare_inspector, save_notes
from .timecodes import validate_interval
from .worker import JobProcessor


def configure_logging(settings: Settings) -> None:
    log_path = settings.data_dir / "logs" / "api.log"
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[logging.StreamHandler(), logging.FileHandler(log_path)],
        force=False,
    )


def create_app(settings: Settings | None = None) -> FastAPI:
    configured = settings or get_settings()
    configured.ensure_directories()
    store = JobStore(configured)
    store.initialize()
    analysis_store = VodAnalysisStore(configured)
    analysis_store.initialize()

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        configure_logging(configured)
        store.fail_interrupted_jobs()
        analysis_store.fail_interrupted_jobs()
        for stale_temp in (configured.data_dir / "analysis").glob("*/tmp"):
            if stale_temp.is_dir():
                shutil.rmtree(stale_temp, ignore_errors=True)
        application.state.settings = configured
        application.state.store = store
        application.state.analysis_store = analysis_store
        application.state.processor = JobProcessor(store, configured, analysis_store)
        logging.getLogger(__name__).info("API started with data directory %s", configured.data_dir)
        yield
        application.state.processor.shutdown()

    application = FastAPI(title="Twitch VOD Local Clip Editor", version="1.0.0", lifespan=lifespan)
    application.state.settings = configured
    application.state.store = store
    application.add_middleware(
        CORSMiddleware,
        allow_origins=configured.cors_origin_list,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    def response_for(job: dict) -> JobResponse:
        payload = dict(job)
        payload["video_url"] = f"/jobs/{job['id']}/video" if job.get("rendered_path") else None
        return JobResponse.model_validate(payload)

    @application.get("/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        return HealthResponse(
            status="ok",
            ffmpeg_available=shutil.which(configured.ffmpeg_path) is not None,
            ffprobe_available=shutil.which(configured.ffprobe_path) is not None,
            ytdlp_available=shutil.which(configured.ytdlp_path) is not None,
            youtube_configured=configured.youtube_client_secrets_path.is_file(),
            demo_mode=configured.demo_mode,
        )

    @application.get("/setup/status", response_model=SetupStatusResponse)
    def setup_status() -> SetupStatusResponse:
        return SetupStatusResponse.model_validate(get_setup_status(configured))

    @application.get("/profiles", response_model=list[StreamerProfileResponse])
    def profiles() -> list[StreamerProfileResponse]:
        return [
            StreamerProfileResponse.model_validate(item)
            for item in list_profiles(configured.data_dir / "profiles")
        ]

    @application.get("/vod-analysis/profiles", response_model=list[AnalysisProfileResponse])
    def analysis_profiles() -> list[AnalysisProfileResponse]:
        return [
            AnalysisProfileResponse(
                id=profile.id, display_name=profile.display_name, language=profile.language
            )
            for profile in PROFILES.values()
        ]

    @application.post(
        "/vod-analysis", response_model=VodAnalysisStartResponse, status_code=status.HTTP_202_ACCEPTED
    )
    def create_vod_analysis(payload: VodAnalysisCreate, request: Request) -> VodAnalysisStartResponse:
        try:
            identity = parse_source_identity(str(payload.url))
            profile = get_analysis_profile(payload.streamer)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        cache_key = topic_cache_keys(
            identity, profile.id, configured, source_url=str(payload.url)
        )["candidates"]
        if not payload.force_reanalyze:
            cached_job = analysis_store.find_cached(cache_key)
            cached_result = cached_job.get("result") if cached_job is not None else None
            topic_cache_ready = (
                cached_job is not None
                and isinstance(cached_result, dict)
                and cached_result.get("analysis_strategy") == "transcript_topics"
                and cached_result.get("pipeline_version") == configured.vod_topic_analysis_pipeline_version
            )
            fixture_cache_ready = (
                configured.vod_analysis_fixture_mode
                and cached_job is not None
                and isinstance(cached_result, dict)
                and cached_result.get("fixture") is True
                and cached_result.get("pipeline_version") == configured.vod_topic_analysis_pipeline_version
            )
            if topic_cache_ready or fixture_cache_ready:
                analysis_store.update(cached_job["id"], cached=1)
                return VodAnalysisStartResponse(job_id=cached_job["id"], cached=True)
        job_id = str(uuid.uuid4())
        analysis_store.create(
            {
                "id": job_id,
                "source_url": str(payload.url),
                "source_platform": identity.platform,
                "source_vod_id": identity.vod_id,
                "streamer_profile": profile.id,
                "pipeline_version": configured.vod_topic_analysis_pipeline_version,
                "cache_key": cache_key,
                "fixture_mode": configured.vod_analysis_fixture_mode,
                "phase_detection_strategy": "transcript_topics",
                "requires_coarse_timeline": False,
            }
        )
        request.app.state.processor.submit_vod_analysis(job_id)
        return VodAnalysisStartResponse(job_id=job_id, cached=False)

    @application.get("/vod-analysis/{job_id}", response_model=VodAnalysisJobResponse)
    def get_vod_analysis(job_id: str) -> VodAnalysisJobResponse:
        job = analysis_store.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="VOD analysis job not found")
        return VodAnalysisJobResponse.model_validate(job)

    @application.get("/vod-analyses", response_model=list[VodAnalysisJobResponse])
    def list_vod_analyses() -> list[VodAnalysisJobResponse]:
        return [VodAnalysisJobResponse.model_validate(job) for job in analysis_store.list()]

    @application.post(
        "/vod-inspector",
        response_model=VodAnalysisStartResponse,
        status_code=status.HTTP_202_ACCEPTED,
    )
    def create_vod_inspector(payload: VodAnalysisCreate, request: Request) -> VodAnalysisStartResponse:
        try:
            identity = parse_source_identity(str(payload.url))
            profile = get_analysis_profile(payload.streamer)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        cache_key = layout_cache_key(identity.platform, identity.vod_id, profile.id, configured)
        if not payload.force_reanalyze:
            cached_job = analysis_store.find_cached(cache_key)
            if cached_job is not None:
                analysis_store.update(cached_job["id"], cached=1)
                return VodAnalysisStartResponse(job_id=cached_job["id"], cached=True)
        job_id = str(uuid.uuid4())
        analysis_store.create(
            {
                "id": job_id,
                "source_url": str(payload.url),
                "source_platform": identity.platform,
                "source_vod_id": identity.vod_id,
                "streamer_profile": profile.id,
                "pipeline_version": configured.vod_analysis_phase_pipeline_version,
                "cache_key": cache_key,
                "fixture_mode": configured.vod_analysis_fixture_mode,
                "phase_detection_strategy": "profile_layout_match",
                "requires_coarse_timeline": False,
            }
        )
        request.app.state.processor.submit_vod_analysis(job_id)
        return VodAnalysisStartResponse(job_id=job_id, cached=False)

    @application.get("/vod-inspector/{job_id}", response_model=VodInspectorResponse)
    def get_vod_inspector(job_id: str) -> VodInspectorResponse:
        job = analysis_store.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="VOD Inspector job not found")
        return prepare_inspector(job, configured)

    @application.put("/vod-inspector/{job_id}/validation-notes", response_model=VodInspectorResponse)
    def update_vod_inspector_notes(job_id: str, notes: ValidationNotes) -> VodInspectorResponse:
        job = analysis_store.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="VOD Inspector job not found")
        if job["status"] != "completed":
            raise HTTPException(status_code=409, detail="VOD Inspector analysis is not completed")
        directory = configured.data_dir / "analysis" / job_id
        save_notes(directory, notes)
        return prepare_inspector(job, configured)

    @application.get("/vod-inspector/{job_id}/export")
    def export_vod_inspector(job_id: str) -> FileResponse:
        job = analysis_store.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="VOD Inspector job not found")
        if job["status"] != "completed":
            raise HTTPException(status_code=409, detail="VOD Inspector analysis is not completed")
        try:
            path = export_report(job, configured)
        except (RuntimeError, ValueError, OSError) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return FileResponse(
            path,
            media_type="application/zip",
            filename=f"vod-inspector-{job['source_vod_id']}.zip",
        )

    @application.post("/jobs", response_model=JobResponse, status_code=status.HTTP_202_ACCEPTED)
    def create_job(payload: JobCreate, request: Request) -> JobResponse:
        try:
            start_seconds, end_seconds = validate_interval(
                payload.start, payload.end, configured.max_clip_duration_seconds
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        if payload.streamer_profile != "auto":
            try:
                load_profile(configured.data_dir / "profiles", payload.streamer_profile)
            except ProfileValidationError as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc
        if payload.source_job_id:
            source_job = store.get(payload.source_job_id)
            if source_job is None:
                raise HTTPException(status_code=422, detail="Raw preview job not found")
            if source_job["status"] not in {"ready", "completed"} or not source_job.get(
                "source_clip_path"
            ):
                raise HTTPException(status_code=409, detail="Raw preview is not ready yet")
            if (
                source_job["source_url"] != str(payload.source_url)
                or source_job["start_seconds"] != start_seconds
                or source_job["end_seconds"] != end_seconds
            ):
                raise HTTPException(
                    status_code=422, detail="Raw preview source and interval do not match"
                )
        job_id = str(uuid.uuid4())
        job = store.create(
            {
                "id": job_id,
                "source_url": str(payload.source_url),
                "start_seconds": start_seconds,
                "end_seconds": end_seconds,
                "remove_silences": payload.remove_silences,
                "normalize_audio": payload.normalize_audio,
                "generate_subtitles": payload.generate_subtitles,
                "output_format": payload.output_format,
                "smart_vertical_layout": (
                    payload.smart_vertical_layout
                    if "smart_vertical_layout" in payload.model_fields_set
                    else configured.smart_vertical_layout_default and payload.output_format == "vertical"
                ),
                "streamer_profile": payload.streamer_profile,
                "demo": payload.demo,
                "youtube_title": payload.youtube_title,
                "source_job_id": payload.source_job_id,
                "job_kind": payload.job_kind,
                "workflow_type": payload.workflow_type,
                "project_id": payload.project_id or job_id,
            }
        )
        request.app.state.processor.submit(job["id"])
        return response_for(job)

    @application.get("/jobs", response_model=list[JobResponse])
    def list_jobs() -> list[JobResponse]:
        return [response_for(job) for job in store.list()]

    @application.get("/jobs/{job_id}", response_model=JobResponse)
    def get_job(job_id: str) -> JobResponse:
        job = store.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Job not found")
        return response_for(job)

    @application.get("/jobs/{job_id}/video")
    def get_video(job_id: str) -> FileResponse:
        job = store.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Job not found")
        if not job.get("rendered_path"):
            raise HTTPException(status_code=409, detail="Video is not ready")
        try:
            path = safe_data_path(job["rendered_path"], configured.data_dir)
        except ValueError as exc:
            raise HTTPException(status_code=403, detail="Invalid stored video path") from exc
        if not path.is_file():
            raise HTTPException(status_code=404, detail="Rendered video file is missing")
        return FileResponse(path, media_type="video/mp4", filename=f"twitch-clip-{job_id}.mp4")

    @application.post("/jobs/{job_id}/youtube", response_model=JobResponse, status_code=202)
    def upload_to_youtube(job_id: str, payload: YouTubeUploadRequest, request: Request) -> JobResponse:
        job = store.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Job not found")
        if job["status"] not in {"ready", "completed"} or not job.get("rendered_path"):
            raise HTTPException(status_code=409, detail="Preview must be ready before upload")
        if not get_setup_status(configured)["youtube_ready"]:
            raise HTTPException(
                status_code=503,
                detail=(
                    "YouTube OAuth is not configured or authorized. "
                    "See README.md and run scripts/youtube_auth.py."
                ),
            )
        updated = store.update(
            job_id,
            youtube_title=payload.title,
            youtube_description=payload.description,
            tags=payload.tags,
            privacy_status=payload.privacy_status,
            status="uploading",
            progress=0,
            current_step="Queued for YouTube upload",
            error_message=None,
        )
        assert updated is not None
        request.app.state.processor.submit_upload(job_id)
        return response_for(updated)

    @application.delete("/jobs/{job_id}", status_code=204)
    def delete_job(job_id: str) -> Response:
        job = store.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Job not found")
        active_statuses = {
            "queued",
            "inspecting",
            "downloading",
            "trimming",
            "analyzing",
            "transcribing",
            "rendering",
            "uploading",
        }
        if job["status"] in active_statuses:
            raise HTTPException(status_code=409, detail="Active jobs cannot be deleted")
        file_fields = (
            "download_path",
            "source_clip_path",
            "rendered_path",
            "subtitle_path",
            "edit_plan_path",
            "composition_plan_path",
        )
        for field in file_fields:
            if not job.get(field):
                continue
            try:
                path = safe_data_path(job[field], configured.data_dir)
                if path.is_file():
                    path.unlink(missing_ok=True)
            except ValueError:
                logging.getLogger(__name__).warning("Skipped unsafe stored path for job %s", job_id)
        for base in (configured.data_dir / "downloads", configured.data_dir / "work"):
            directory = base / job_id
            if directory.is_dir():
                shutil.rmtree(directory)
        store.delete(job_id)
        return Response(status_code=204)

    return application


app = create_app()
