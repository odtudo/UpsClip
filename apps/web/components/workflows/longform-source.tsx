"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { createVodAnalysis } from "@/lib/api";
import { validateSource } from "@/lib/workflow/validation";

export function LongformSource() {
  const router = useRouter();
  const [url, setUrl] = useState("");
  const [force, setForce] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  async function submit(event: FormEvent) {
    event.preventDefault();
    if (submitting) return;
    const errors = validateSource(url);
    if (errors.url) {
      setError(errors.url);
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const result = await createVodAnalysis({
        url,
        streamer: "illojuan",
        force_reanalyze: force,
      });
      router.push(`/long-form/${result.job_id}?step=analyze`);
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "The analysis could not be started.",
      );
      setSubmitting(false);
    }
  }
  return (
    <div>
      <p className="eyebrow">Long-form Clip</p>
      <h1 className="mt-3 text-3xl font-semibold">
        Discover conversation candidates
      </h1>
      <p className="mt-3 max-w-2xl text-secondary">
        Analyze the configured VOD range using the existing transcript-first
        pipeline. No timestamps or edit options are needed yet.
      </p>
      <form onSubmit={submit} className="surface mt-8 max-w-2xl p-6">
        <label className="block text-sm font-medium">
          VOD URL
          <input
            type="url"
            className="field mt-2"
            value={url}
            onChange={(event) => setUrl(event.target.value)}
            placeholder="https://www.twitch.tv/videos/…"
          />
        </label>
        <label className="mt-5 flex items-start gap-3 text-sm">
          <input
            type="checkbox"
            checked={force}
            onChange={(event) => setForce(event.target.checked)}
            className="mt-0.5 h-4 w-4"
          />
          <span>
            <strong className="block">Ignore cached topic results</strong>
            <span className="mt-1 block text-xs text-secondary">
              Audio and compatible transcription stages may still be reused by
              the backend.
            </span>
          </span>
        </label>
        {error && (
          <p
            role="alert"
            className="mt-5 rounded-md bg-danger/10 p-3 text-sm text-red-200"
          >
            {error}
          </p>
        )}
        <button disabled={submitting} className="button-primary mt-6">
          {submitting ? "Starting analysis…" : "Analyze VOD"}
        </button>
      </form>
    </div>
  );
}
