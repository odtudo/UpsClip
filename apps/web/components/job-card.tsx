"use client";

import { FormEvent, useState } from "react";
import { API_URL, Job, uploadJob } from "@/lib/api";

const activeStatuses = new Set(["queued", "inspecting", "downloading", "trimming", "analyzing", "detecting_scenes", "analyzing_layouts", "composing", "transcribing", "rendering", "finalizing", "uploading"]);

function formatDuration(seconds: number | null) {
  if (seconds === null) return "—";
  const minutes = Math.floor(seconds / 60);
  return `${minutes}:${Math.floor(seconds % 60).toString().padStart(2, "0")}`;
}

type Props = {
  job: Job;
  youtubeReady: boolean;
  onChanged: () => Promise<void>;
  onDelete: (id: string) => Promise<void>;
};

export function JobCard({ job, youtubeReady, onChanged, onDelete }: Props) {
  const [expanded, setExpanded] = useState(job.status === "ready" || job.status === "completed");
  const [title, setTitle] = useState(job.source_title || "Twitch clip");
  const [description, setDescription] = useState("");
  const [tags, setTags] = useState("twitch, gaming");
  const [privacy, setPrivacy] = useState("private");
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const isActive = activeStatuses.has(job.status);
  const ready = ["ready", "completed"].includes(job.status) && Boolean(job.video_url);

  async function upload(event: FormEvent) {
    event.preventDefault();
    setUploadError(null);
    setUploading(true);
    try {
      await uploadJob(job.id, {
        title,
        description,
        tags: tags.split(",").map((tag) => tag.trim()).filter(Boolean),
        privacy_status: privacy,
      });
      await onChanged();
    } catch (error) {
      setUploadError(error instanceof Error ? error.message : "Upload could not be started");
    } finally {
      setUploading(false);
    }
  }

  return (
    <article className="overflow-hidden rounded-2xl border border-zinc-200 bg-white shadow-sm">
      <div className="p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <span
                className={`rounded-full px-2.5 py-1 text-xs font-semibold capitalize ${
                  job.status === "failed"
                    ? "bg-red-100 text-red-700"
                    : ready
                      ? "bg-emerald-100 text-emerald-700"
                      : "bg-violet-100 text-violet-700"
                }`}
              >
                {job.status}
              </span>
              {job.demo && <span className="text-xs font-medium text-zinc-400">Demo</span>}
            </div>
            <h3 className="mt-2 truncate font-semibold">{job.source_title || "Twitch VOD clip"}</h3>
            <p className="mt-1 text-xs text-zinc-500">
              {job.start_seconds}s–{job.end_seconds}s · {job.output_format} · {new Date(job.created_at).toLocaleString()}
            </p>
          </div>
          <button
            type="button"
            disabled={isActive}
            onClick={() => onDelete(job.id)}
            className="text-xs font-semibold text-zinc-500 hover:text-red-600 disabled:cursor-not-allowed disabled:opacity-40"
          >
            Delete local job
          </button>
        </div>

        <div className="mt-4 h-2 overflow-hidden rounded-full bg-zinc-100">
          <div className="h-full rounded-full bg-twitch transition-all" style={{ width: `${job.progress}%` }} />
        </div>
        <div className="mt-2 flex justify-between gap-3 text-xs text-zinc-500">
          <span>{job.current_step}</span>
          <span>{job.progress}%</span>
        </div>

        {job.error_message && <p className="mt-4 rounded-lg bg-red-50 p-3 text-sm text-red-700">{job.error_message}</p>}
        {job.output_format === "vertical" && job.smart_vertical_layout && Object.keys(job.layout_summary || {}).length > 0 && (
          <div className="mt-4 rounded-lg bg-violet-50 p-3 text-sm text-violet-900">
            <strong>Smart layout:</strong> {job.layout_summary.segments || 0} scenes · {job.layout_summary.fullscreen_face || 0} fullscreen · {job.layout_summary.small_facecam || 0} facecam · {job.layout_summary.fallbacks || 0} fallback
            {job.resolved_streamer_profile && <span> · Profile: {job.resolved_streamer_profile}</span>}
          </div>
        )}
        {job.layout_warnings?.length > 0 && <div className="mt-3 rounded-lg bg-amber-50 p-3 text-sm text-amber-900"><strong>Smart layout warnings</strong><ul className="mt-1 list-disc pl-5">{job.layout_warnings.map((warning, index) => <li key={`${warning.code}-${index}`}>{warning.message} ({formatDuration(warning.start)}–{formatDuration(warning.end)})</li>)}</ul></div>}
        {job.youtube_url && (
          <a className="mt-4 block text-sm font-semibold text-twitch underline" href={job.youtube_url} target="_blank" rel="noreferrer">
            View uploaded video on YouTube
          </a>
        )}

        {ready && (
          <button
            type="button"
            onClick={() => setExpanded((value) => !value)}
            className="mt-4 rounded-lg border border-zinc-300 px-3 py-2 text-sm font-semibold hover:bg-zinc-50"
          >
            {expanded ? "Hide preview" : "Preview and upload"}
          </button>
        )}
      </div>

      {ready && expanded && (
        <div className="border-t border-zinc-200 bg-zinc-50 p-5">
          <video
            className={job.output_format === "vertical" ? "mx-auto aspect-[9/16] max-h-[70vh] w-auto rounded-xl bg-black" : "aspect-video w-full rounded-xl bg-black"}
            controls
            preload="metadata"
            src={`${API_URL}${job.video_url}`}
          />
          <p className="mt-2 text-xs text-zinc-500">
            Duration {formatDuration(job.rendered_duration)} · {job.rendered_size ? `${(job.rendered_size / 1_048_576).toFixed(1)} MB` : "size unknown"}
          </p>

          {!job.youtube_url && (
            <form onSubmit={upload} className="mt-5 grid gap-3">
              <h4 className="font-semibold">Upload to YouTube after preview</h4>
              <input
                className="rounded-lg border border-zinc-300 px-3 py-2 text-sm"
                required
                maxLength={100}
                value={title}
                onChange={(event) => setTitle(event.target.value)}
                placeholder="Title"
              />
              <textarea
                className="min-h-24 rounded-lg border border-zinc-300 px-3 py-2 text-sm"
                value={description}
                onChange={(event) => setDescription(event.target.value)}
                placeholder="Description"
              />
              <div className="grid gap-3 sm:grid-cols-[1fr_10rem]">
                <input
                  className="rounded-lg border border-zinc-300 px-3 py-2 text-sm"
                  value={tags}
                  onChange={(event) => setTags(event.target.value)}
                  placeholder="comma, separated, tags"
                />
                <select
                  className="rounded-lg border border-zinc-300 px-3 py-2 text-sm"
                  value={privacy}
                  onChange={(event) => setPrivacy(event.target.value)}
                >
                  <option value="private">Private</option>
                  <option value="unlisted">Unlisted</option>
                  <option value="public">Public</option>
                </select>
              </div>
              {uploadError && <p className="rounded-lg bg-red-50 p-3 text-sm text-red-700">{uploadError}</p>}
              <button
                disabled={!youtubeReady || uploading || job.status === "uploading"}
                className="rounded-lg bg-zinc-900 px-4 py-2.5 text-sm font-semibold text-white disabled:opacity-50"
              >
                {uploading || job.status === "uploading" ? "Starting upload…" : youtubeReady ? "Upload to YouTube" : "Authorize YouTube first"}
              </button>
              {!youtubeReady && <p className="text-xs text-amber-700">Place the Desktop app JSON at data/credentials/client_secret.json, then run ./scripts/youtube_auth.sh.</p>}
              <p className="text-xs text-zinc-500">Uploads are private by default and never start automatically.</p>
            </form>
          )}
        </div>
      )}
    </article>
  );
}
