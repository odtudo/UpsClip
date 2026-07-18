"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import {
  listJobs,
  listVodAnalyses,
  type Job,
  type VodAnalysisJob,
} from "@/lib/api";
import { formatTimestamp } from "@/lib/workflow/validation";

type Filter = "all" | "running" | "completed" | "failed";
const running = new Set([
  "queued",
  "processing",
  "inspecting",
  "downloading",
  "trimming",
  "analyzing",
  "transcribing",
  "rendering",
  "composing",
  "finalizing",
  "uploading",
]);
export function JobsView() {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [analyses, setAnalyses] = useState<VodAnalysisJob[]>([]);
  const [filter, setFilter] = useState<Filter>("all");
  const [error, setError] = useState<string | null>(null);
  const refresh = useCallback(async () => {
    try {
      const [nextJobs, nextAnalyses] = await Promise.all([
        listJobs(),
        listVodAnalyses(),
      ]);
      setJobs(nextJobs);
      setAnalyses(
        nextAnalyses.filter(
          (item) => item.phase_detection_strategy === "transcript_topics",
        ),
      );
      setError(null);
    } catch (caught) {
      setError(
        caught instanceof Error ? caught.message : "Jobs could not be loaded.",
      );
    }
  }, []);
  useEffect(() => {
    queueMicrotask(() => void refresh());
    const timer = setInterval(() => {
      if (
        [
          ...jobs.map((job) => job.status),
          ...analyses.map((job) => job.status),
        ].some((status) => running.has(status))
      )
        void refresh();
    }, 2500);
    return () => clearInterval(timer);
  }, [refresh, jobs, analyses]);
  const matches = (status: string) =>
    filter === "all" ||
    (filter === "running"
      ? running.has(status)
      : filter === "completed"
        ? ["ready", "completed"].includes(status)
        : status === "failed");
  return (
    <div>
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="eyebrow">Persistent workspace</p>
          <h1 className="mt-2 text-3xl font-semibold">Jobs</h1>
          <p className="mt-3 text-secondary">
            Resume analyses, raw previews, renders, and uploads after navigation
            or refresh.
          </p>
        </div>
        <button onClick={() => void refresh()} className="button-secondary">
          Refresh
        </button>
      </div>
      <div className="mt-8 flex gap-2" role="group" aria-label="Filter jobs">
        {(["all", "running", "completed", "failed"] as const).map((value) => (
          <button
            key={value}
            onClick={() => setFilter(value)}
            className={`rounded-md px-3 py-2 text-sm font-medium capitalize ${filter === value ? "bg-active text-primary" : "text-secondary hover:bg-card"}`}
          >
            {value}
          </button>
        ))}
      </div>
      {error && (
        <p
          role="alert"
          className="mt-5 rounded-md bg-danger/10 p-3 text-red-200"
        >
          {error}
        </p>
      )}
      <div className="mt-6 space-y-3">
        {analyses
          .filter((job) => matches(job.status))
          .map((job) => (
            <article
              key={job.id}
              className="surface flex flex-wrap items-center gap-4 p-4"
            >
              <div className="grid h-10 w-10 place-items-center rounded-md bg-emerald-500/10 text-emerald-400">
                A
              </div>
              <div className="min-w-0 flex-1">
                <h2 className="truncate font-medium">
                    {job.result?.vod?.title || "VOD topic analysis"}
                </h2>
                <p className="mt-1 text-xs text-muted">
                  Long-form analysis · {job.stage.replaceAll("_", " ")} ·{" "}
                  {new Date(job.created_at).toLocaleString()}
                </p>
              </div>
              <span className="text-sm capitalize text-secondary">
                {job.status} · {job.progress}%
              </span>
              <Link
                href={`/long-form/${job.id}?step=${job.status === "completed" ? "candidates" : "analyze"}`}
                className="button-secondary"
              >
                Continue
              </Link>
            </article>
          ))}
        {jobs
          .filter((job) => matches(job.status))
          .map((job) => {
            const project = job.project_id || job.id;
            const vertical = job.workflow_type === "vertical_manual";
            const step =
              job.job_kind === "raw_preview"
                ? "raw-preview"
                : ["ready", "completed"].includes(job.status)
                  ? "review"
                  : "render";
            const href = vertical
              ? `/vertical/${project}?step=${step}${job.job_kind === "render" ? `&render=${job.id}` : ""}`
              : job.workflow_type === "longform_automatic"
                ? `/long-form/${project}?step=${step}&${job.job_kind === "raw_preview" ? "preview" : "render"}=${job.id}`
                : `#job-${job.id}`;
            return (
              <article
                id={`job-${job.id}`}
                key={job.id}
                className="surface flex flex-wrap items-center gap-4 p-4"
              >
                <div className="grid h-10 w-10 place-items-center rounded-md bg-blue-500/10 text-blue-400">
                  {job.output_format === "vertical" ? "V" : "H"}
                </div>
                <div className="min-w-0 flex-1">
                  <h2 className="truncate font-medium">
                    {job.source_title ||
                      (job.job_kind === "raw_preview"
                        ? "Raw preview"
                        : "Rendered clip")}
                  </h2>
                  <p className="mt-1 text-xs text-muted">
                    {job.workflow_type.replaceAll("_", " ")} ·{" "}
                    {job.job_kind.replaceAll("_", " ")} ·{" "}
                    {formatTimestamp(job.start_seconds)}–
                    {formatTimestamp(job.end_seconds)}
                  </p>
                </div>
                <span
                  className={`text-sm capitalize ${job.status === "failed" ? "text-red-300" : "text-secondary"}`}
                >
                  {job.status} · {job.progress}%
                </span>
                {job.workflow_type === "legacy" ? (
                  <span className="text-xs text-muted">Legacy job</span>
                ) : (
                  <Link href={href} className="button-secondary">
                    Open
                  </Link>
                )}
              </article>
            );
          })}
        {!analyses.some((job) => matches(job.status)) &&
          !jobs.some((job) => matches(job.status)) && (
            <div className="surface p-10 text-center text-secondary">
              No jobs match this filter.
            </div>
          )}
      </div>
    </div>
  );
}
