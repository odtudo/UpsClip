"use client";

import Link from "next/link";
import { FormEvent, useState } from "react";
import { type Job, type SetupStatus, uploadJob, videoUrl } from "@/lib/api";
import { Icon } from "@/components/ui/icons";

export function PublishPanel({
  job,
  setup,
  onChanged,
}: {
  job: Job;
  setup: SetupStatus | null;
  onChanged: (job: Job) => void;
}) {
  const [destination, setDestination] = useState<"youtube" | "export">(
    "youtube",
  );
  const [title, setTitle] = useState(
    job.youtube_title || job.source_title || "Twitch clip",
  );
  const [description, setDescription] = useState(job.youtube_description || "");
  const [tags, setTags] = useState(job.tags.join(", "));
  const [privacy, setPrivacy] = useState<"private" | "unlisted" | "public">(
    job.privacy_status,
  );
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  async function submit(event: FormEvent) {
    event.preventDefault();
    if (uploading) return;
    setUploading(true);
    setError(null);
    try {
      onChanged(
        await uploadJob(job.id, {
          title,
          description,
          tags: tags
            .split(",")
            .map((tag) => tag.trim())
            .filter(Boolean),
          privacy_status: privacy,
        }),
      );
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "Upload could not be started.",
      );
    } finally {
      setUploading(false);
    }
  }
  const destinations = [
    { id: "youtube", label: "YouTube", available: true },
    { id: "instagram", label: "Instagram", available: false },
    { id: "tiktok", label: "TikTok", available: false },
    { id: "export", label: "Export only", available: true },
  ] as const;
  return (
    <div className="grid gap-6 lg:grid-cols-[18rem_1fr]">
      <aside>
        <h2 className="text-sm font-semibold">Destination</h2>
        <div className="mt-3 space-y-2">
          {destinations.map((item) => (
            <button
              key={item.id}
              type="button"
              disabled={!item.available}
              onClick={() => item.available && setDestination(item.id)}
              className={`flex w-full items-center justify-between rounded-md border p-3 text-left text-sm ${destination === item.id ? "border-accent bg-accent/10" : "border-line bg-card"} disabled:cursor-not-allowed disabled:opacity-45`}
            >
              <span>{item.label}</span>
              <span className="text-xs text-secondary">
                {item.available
                  ? item.id === "export"
                    ? "Download"
                    : "Available"
                  : "Coming soon"}
              </span>
            </button>
          ))}
        </div>
      </aside>
      <section className="surface p-6">
        {destination === "export" ? (
          <div>
            <Icon name="upload" className="h-8 w-8 text-accentSoft" />
            <h2 className="mt-4 text-xl font-semibold">
              Export finished video
            </h2>
            <p className="mt-2 text-sm text-secondary">
              Download the rendered MP4 without publishing it to an external
              service.
            </p>
            <a
              href={videoUrl(job) || "#"}
              download
              className="button-primary mt-6"
            >
              Download MP4
            </a>
          </div>
        ) : job.youtube_url ? (
          <div>
            <h2 className="text-xl font-semibold text-success">
              Published to YouTube
            </h2>
            <p className="mt-2 text-sm text-secondary">
              The upload completed successfully.
            </p>
            <a
              href={job.youtube_url}
              target="_blank"
              rel="noreferrer"
              className="button-primary mt-6"
            >
              Open video
            </a>
          </div>
        ) : !setup?.youtube_ready ? (
          <div>
            <h2 className="text-xl font-semibold">Connect YouTube</h2>
            <p className="mt-2 max-w-xl text-sm leading-6 text-secondary">
              YouTube is disconnected. Complete the existing local OAuth flow
              before uploading. No credentials are exposed in this interface.
            </p>
            <Link href="/settings" className="button-primary mt-6">
              Open Settings
            </Link>
          </div>
        ) : (
          <form onSubmit={submit}>
            <h2 className="text-xl font-semibold">Publish to YouTube</h2>
            <p className="mt-2 text-sm text-secondary">
              Uploads never start automatically. Private is the safest default.
            </p>
            <div className="mt-6 space-y-4">
              <label className="block text-sm font-medium">
                Title
                <input
                  className="field mt-2"
                  required
                  maxLength={100}
                  value={title}
                  onChange={(event) => setTitle(event.target.value)}
                />
              </label>
              <label className="block text-sm font-medium">
                Description
                <textarea
                  className="field mt-2 min-h-28"
                  maxLength={5000}
                  value={description}
                  onChange={(event) => setDescription(event.target.value)}
                />
              </label>
              <div className="grid gap-4 sm:grid-cols-[1fr_12rem]">
                <label className="block text-sm font-medium">
                  Tags
                  <input
                    className="field mt-2"
                    value={tags}
                    onChange={(event) => setTags(event.target.value)}
                    placeholder="twitch, commentary"
                  />
                </label>
                <label className="block text-sm font-medium">
                  Visibility
                  <select
                    className="field mt-2"
                    value={privacy}
                    onChange={(event) =>
                      setPrivacy(event.target.value as typeof privacy)
                    }
                  >
                    <option value="private">Private</option>
                    <option value="unlisted">Unlisted</option>
                    <option value="public">Public</option>
                  </select>
                </label>
              </div>
              {error && (
                <p
                  role="alert"
                  className="rounded-md border border-danger/30 bg-danger/10 p-3 text-sm text-red-200"
                >
                  {error}
                </p>
              )}
              <button
                disabled={uploading || job.status === "uploading"}
                className="button-primary"
              >
                {uploading || job.status === "uploading"
                  ? "Starting upload…"
                  : "Upload to YouTube"}
              </button>
            </div>
          </form>
        )}
      </section>
    </div>
  );
}
