"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { createJob } from "@/lib/api";
import { validateSource } from "@/lib/workflow/validation";
import { saveProject } from "@/lib/workflow/storage";
import { verticalDefaults } from "@/types/workflow";

export function VerticalSource() {
  const router = useRouter();
  const [url, setUrl] = useState("");
  const [start, setStart] = useState("00:00");
  const [end, setEnd] = useState("00:30");
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [submitting, setSubmitting] = useState(false);
  async function submit(event: FormEvent) {
    event.preventDefault();
    if (submitting) return;
    const nextErrors = validateSource(url, start, end);
    setErrors(nextErrors);
    if (Object.keys(nextErrors).length) return;
    setSubmitting(true);
    try {
      const job = await createJob({
        source_url: url,
        start,
        end,
        remove_silences: false,
        normalize_audio: false,
        generate_subtitles: false,
        output_format: "horizontal",
        smart_vertical_layout: false,
        streamer_profile: "auto",
        demo: false,
        job_kind: "raw_preview",
        workflow_type: "vertical_manual",
      });
      saveProject(job.id, {
        workflowType: "vertical_manual",
        sourceUrl: url,
        range: { start, end },
        title: "Vertical clip",
        rawPreviewJob: job,
        editSettings: verticalDefaults,
        updatedAt: new Date().toISOString(),
      });
      router.push(`/vertical/${job.id}?step=raw-preview`);
    } catch (caught) {
      setErrors({
        form:
          caught instanceof Error
            ? caught.message
            : "The raw preview could not be created.",
      });
      setSubmitting(false);
    }
  }
  return (
    <div>
      <p className="eyebrow">Vertical Clip</p>
      <h1 className="mt-3 text-3xl font-semibold">
        Choose the source interval
      </h1>
      <p className="mt-3 max-w-2xl text-secondary">
        First create an untouched horizontal preview of only the requested VOD
        section. Editing begins after you approve the interval.
      </p>
      <form onSubmit={submit} className="surface mt-8 max-w-2xl p-6" noValidate>
        <label htmlFor="source-url" className="block text-sm font-medium">
          VOD URL
          <input
            id="source-url"
            type="url"
            className="field mt-2"
            value={url}
            onChange={(event) => setUrl(event.target.value)}
            placeholder="https://www.twitch.tv/videos/…"
            aria-invalid={Boolean(errors.url)}
            aria-describedby={errors.url ? "url-error" : undefined}
          />
        </label>
        {errors.url && (
          <p id="url-error" role="alert" className="mt-2 text-sm text-red-300">
            {errors.url}
          </p>
        )}
        <div className="mt-5 grid gap-4 sm:grid-cols-2">
          <label className="block text-sm font-medium">
            Start timestamp
            <input
              className="field mt-2"
              value={start}
              onChange={(event) => setStart(event.target.value)}
              aria-invalid={Boolean(errors.start)}
            />
            {errors.start && (
              <span className="mt-2 block text-sm text-red-300">
                {errors.start}
              </span>
            )}
          </label>
          <label className="block text-sm font-medium">
            End timestamp
            <input
              className="field mt-2"
              value={end}
              onChange={(event) => setEnd(event.target.value)}
              aria-invalid={Boolean(errors.end)}
            />
            {errors.end && (
              <span className="mt-2 block text-sm text-red-300">
                {errors.end}
              </span>
            )}
          </label>
        </div>
        <p className="mt-3 text-xs text-muted">
          Accepted: MM:SS, HH:MM:SS, or seconds. Maximum duration follows the
          backend limit.
        </p>
        {errors.form && (
          <p
            role="alert"
            className="mt-5 rounded-md bg-danger/10 p-3 text-sm text-red-200"
          >
            {errors.form}
          </p>
        )}
        <button disabled={submitting} className="button-primary mt-6">
          {submitting ? "Preparing preview…" : "Generate Raw Preview"}
        </button>
      </form>
    </div>
  );
}
