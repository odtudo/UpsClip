import json
import logging
from concurrent.futures import ThreadPoolExecutor

from .config import Settings
from .database import JobStore, VodAnalysisStore, safe_data_path
from .services.edit_plan import generate_edit_plan
from .services.media import (
    create_demo_clip,
    detect_silences,
    download_section,
    inspect_vod,
    media_duration,
    precise_trim,
    probe_media,
    render_edit_plan,
)
from .services.subtitles import burn_subtitles, transcribe_media, write_ass
from .services.youtube import upload_video

logger = logging.getLogger(__name__)


class JobProcessor:
    def __init__(self, store: JobStore, settings: Settings, analysis_store: VodAnalysisStore | None = None):
        self.store = store
        self.settings = settings
        self.analysis_store = analysis_store
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="video-job")

    def submit(self, job_id: str) -> None:
        self.executor.submit(self._process_safely, job_id)

    def submit_upload(self, job_id: str) -> None:
        self.executor.submit(self._upload_safely, job_id)

    def submit_vod_analysis(self, job_id: str) -> None:
        if self.analysis_store is None:
            raise RuntimeError("VOD analysis store is not configured")
        from .services.vod_analysis import VodAnalysisAnalyzer

        analyzer = VodAnalysisAnalyzer(self.analysis_store, self.settings)
        self.executor.submit(analyzer.process, job_id)

    def shutdown(self) -> None:
        self.executor.shutdown(wait=False, cancel_futures=False)

    def _step(self, job_id: str, status: str, progress: int, message: str, **values: object) -> None:
        logger.info("Job %s: %s (%s%%)", job_id, message, progress)
        self.store.update(
            job_id,
            status=status,
            progress=max(0, min(progress, 100)),
            current_step=message,
            error_message=None,
            **values,
        )

    def _process_safely(self, job_id: str) -> None:
        try:
            self.process(job_id)
        except Exception as exc:  # worker boundary must persist all failures
            logger.exception("Job %s failed", job_id)
            self.store.update(
                job_id,
                status="failed",
                current_step="Processing failed",
                error_message=str(exc)[:1000],
            )

    def process(self, job_id: str) -> None:
        job = self.store.get(job_id)
        if job is None:
            return
        job_download_dir = self.settings.data_dir / "downloads" / job_id
        job_work_dir = self.settings.data_dir / "work" / job_id
        source_clip = job_work_dir / "source_clip.mp4"
        rendered_path = self.settings.data_dir / "rendered" / f"{job_id}.mp4"
        edited_path = job_work_dir / "edited_without_subtitles.mp4"
        edited_timeline_path = job_work_dir / "edited_timeline.mp4"
        composed_path = job_work_dir / "vertical_composed.mp4"
        subtitle_path = self.settings.data_dir / "subtitles" / f"{job_id}.ass"
        edit_plan_path = job_work_dir / "edit_plan.json"
        composition_plan_path = job_work_dir / "composition_plan.json"
        job_work_dir.mkdir(parents=True, exist_ok=True)

        requested_duration = float(job["end_seconds"] - job["start_seconds"])
        uploader: str | None = None
        if job["demo"] or self.settings.demo_mode:
            self._step(job_id, "downloading", 15, "Generating demo media", source_title="Local FFmpeg demo")
            create_demo_clip(source_clip, requested_duration, self.settings)
            source_duration = media_duration(source_clip, self.settings)
            self.store.update(job_id, source_clip_path=str(source_clip))
        else:
            self._step(job_id, "inspecting", 5, "Reading Twitch VOD metadata")
            metadata = inspect_vod(job["source_url"], self.settings)
            uploader = metadata.get("uploader") or metadata.get("channel")
            vod_duration = metadata.get("duration")
            if vod_duration is not None and job["end_seconds"] > float(vod_duration) + 0.5:
                raise ValueError(
                    f"End timestamp is beyond the VOD duration ({float(vod_duration):.1f} seconds)"
                )
            self.store.update(job_id, source_title=metadata.get("title") or "Twitch VOD")

            self._step(job_id, "downloading", 20, "Downloading requested VOD section")
            downloaded, margin_start = download_section(
                job["source_url"],
                job["start_seconds"],
                job["end_seconds"],
                job_download_dir,
                self.settings,
            )
            self.store.update(job_id, download_path=str(downloaded))

            self._step(job_id, "trimming", 42, "Precisely trimming requested interval")
            precise_trim(
                downloaded,
                source_clip,
                job["start_seconds"] - margin_start,
                requested_duration,
                self.settings,
            )
            self.store.update(job_id, source_clip_path=str(source_clip))
            source_duration = media_duration(source_clip, self.settings)

        self._step(job_id, "analyzing", 58, "Analyzing audio silences")
        silences = detect_silences(source_clip, self.settings) if job["remove_silences"] else []

        self._step(job_id, "analyzing", 68, "Generating deterministic edit plan")
        plan = generate_edit_plan(
            source_duration,
            silences,
            remove_silences=job["remove_silences"],
            minimum_silence=self.settings.silence_min_seconds,
            remove_after=self.settings.silence_remove_after_seconds,
            padding=self.settings.silence_padding_seconds,
        )
        edit_plan_path.write_text(json.dumps(plan, indent=2), encoding="utf-8")
        self.store.update(job_id, edit_plan_path=str(edit_plan_path))

        smart = bool(job["output_format"] == "vertical" and job.get("smart_vertical_layout"))
        render_destination = (
            edited_timeline_path if smart else (edited_path if job["generate_subtitles"] else rendered_path)
        )
        self._step(
            job_id,
            "rendering",
            34 if smart else 76,
            "Preparing edited clip" if smart else "Rendering H.264/AAC video",
        )
        render_edit_plan(
            source_clip,
            render_destination,
            plan,
            normalize_audio=job["normalize_audio"],
            output_format="horizontal" if smart else job["output_format"],
            settings=self.settings,
        )
        caption_source = edited_path
        if smart:
            # OpenCV is imported only for smart vertical jobs. This keeps horizontal jobs and
            # API startup lightweight and avoids initializing native detector threads early.
            from .services.smart_vertical.planner import build_composition_plan
            from .services.smart_vertical.renderer import (
                render_composition_plan,
                render_simple_vertical,
            )

            try:
                plan = build_composition_plan(
                    edited_timeline_path,
                    composition_plan_path,
                    requested_profile=job.get("streamer_profile") or "auto",
                    uploader=uploader,
                    settings=self.settings,
                    progress=lambda status, progress, message: self._step(job_id, status, progress, message),
                )
                self._step(job_id, "composing", 60, "Building vertical composition")
                render_metrics = render_composition_plan(
                    edited_timeline_path,
                    composed_path,
                    plan,
                    job_work_dir,
                    self.settings,
                    progress=lambda status, progress, message: self._step(job_id, status, progress, message),
                )
                plan["render_metrics"] = render_metrics
                composition_plan_path.write_text(json.dumps(plan, indent=2), encoding="utf-8")
                self.store.update(
                    job_id,
                    composition_plan_path=str(composition_plan_path),
                    resolved_streamer_profile=plan.get("profile_resolved"),
                    layout_warnings=plan["warnings"],
                    layout_summary=plan["summary"],
                )
                caption_source = composed_path
            except Exception:
                logger.exception("Smart Vertical Layout failed for job %s; using center crop", job_id)
                self._step(job_id, "composing", 65, "Smart layout unavailable; applying safe vertical crop")
                render_simple_vertical(edited_timeline_path, composed_path, self.settings)
                warning = {
                    "code": "smart_layout_fallback",
                    "start": 0.0,
                    "end": plan.get("output_duration", source_duration)
                    if isinstance(plan, dict)
                    else source_duration,
                    "message": "Smart layout analysis failed; a simple vertical crop was used.",
                }
                self.store.update(
                    job_id, layout_warnings=[warning], layout_summary={"segments": 1, "fallbacks": 1}
                )
                caption_source = composed_path
        if job["generate_subtitles"]:
            self._step(job_id, "transcribing", 78 if smart else 84, "Transcribing audio after final timeline")
            captions = transcribe_media(caption_source, self.settings)
            write_ass(
                captions,
                subtitle_path,
                vertical=job["output_format"] == "vertical",
                width=self.settings.vertical_output_width if job["output_format"] == "vertical" else None,
                height=self.settings.vertical_output_height if job["output_format"] == "vertical" else None,
            )
            self.store.update(job_id, subtitle_path=str(subtitle_path))
            self._step(job_id, "rendering", 92, "Burning subtitles")
            burn_subtitles(caption_source, subtitle_path, rendered_path, self.settings)
        self._step(job_id, "finalizing", 97, "Finalizing video")
        rendered_info = probe_media(rendered_path, self.settings)
        duration = float(rendered_info["format"]["duration"])
        size = int(rendered_info["format"].get("size") or rendered_path.stat().st_size)
        self._step(
            job_id,
            "ready",
            100,
            "Ready for preview",
            rendered_path=str(rendered_path),
            rendered_duration=duration,
            rendered_size=size,
        )

    def _upload_safely(self, job_id: str) -> None:
        try:
            job = self.store.get(job_id)
            if job is None or not job.get("rendered_path"):
                raise RuntimeError("Rendered video not found")
            video_path = safe_data_path(job["rendered_path"], self.settings.data_dir)
            if not video_path.is_file():
                raise RuntimeError("Rendered video file is missing")

            def progress(value: int) -> None:
                self._step(job_id, "uploading", value, f"Uploading to YouTube ({value}%)")

            video_id = upload_video(
                video_path,
                title=job["youtube_title"],
                description=job["youtube_description"] or "",
                tags=job["tags"],
                privacy_status=job["privacy_status"],
                settings=self.settings,
                progress_callback=progress,
            )
            self._step(
                job_id,
                "completed",
                100,
                "Uploaded to YouTube",
                youtube_video_id=video_id,
                youtube_url=f"https://youtu.be/{video_id}",
            )
        except Exception as exc:
            logger.exception("YouTube upload failed for job %s", job_id)
            self.store.update(
                job_id,
                status="ready",
                progress=100,
                current_step="Ready for preview (upload failed)",
                error_message=str(exc)[:1000],
            )
