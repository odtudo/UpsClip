import type { ApiError, Job, VodAnalysisJob } from "@/lib/api";

const labels: Record<string, string> = {
  queued: "Queued",
  inspecting: "Reading source metadata",
  downloading: "Preparing source",
  trimming: "Trimming selected interval",
  analyzing: "Detecting silences",
  detecting_scenes: "Detecting scenes",
  analyzing_layouts: "Planning vertical layout",
  composing: "Composing vertical video",
  transcribing: "Transcribing",
  rendering: "Rendering",
  finalizing: "Finalizing",
  extracting_audio: "Preparing audio",
  transcribing_audio: "Transcribing in resumable chunks",
  cleaning_transcript: "Cleaning transcript",
  creating_semantic_windows: "Creating semantic windows",
  detecting_topics: "Detecting topics",
  building_candidates: "Building candidates",
  ranking_candidates: "Ranking candidates",
  completed: "Completed",
  ready: "Ready for review",
  failed: "Failed",
};

export function ProgressPanel({
  job,
  error,
  onRetry,
}: {
  job: Job | VodAnalysisJob | null;
  error?: ApiError | null;
  onRetry?: () => void;
}) {
  const stage = job
    ? "stage" in job
      ? job.stage
      : job.current_step
    : "queued";
  const failed = job?.status === "failed";
  return (
    <section className="surface p-6" aria-live="polite">
      <div className="flex items-start justify-between gap-5">
        <div>
          <p className="eyebrow">Processing</p>
          <h2 className="mt-2 text-xl font-semibold">
            {labels[stage] ?? stage.replaceAll("_", " ")}
          </h2>
          <p className="mt-2 text-sm text-secondary">
            {failed
              ? ("error_message" in job! ? job!.error_message : null) ||
                "The job failed."
              : "You can leave this page. The backend will keep the job in your history."}
          </p>
        </div>
        <strong className="text-2xl tabular-nums">{job?.progress ?? 0}%</strong>
      </div>
      <div className="mt-6 h-2 overflow-hidden rounded-full bg-elevated">
        <div
          className={`h-full rounded-full transition-[width] ${failed ? "bg-danger" : "bg-accent"}`}
          style={{ width: `${job?.progress ?? 4}%` }}
        />
      </div>
      {error && (
        <div className="mt-5 rounded-md border border-danger/30 bg-danger/10 p-4 text-sm text-red-200">
          <p>{error.message}</p>
          {error.technicalDetail && (
            <details className="mt-2 text-xs text-secondary">
              <summary>Technical details</summary>
              <pre className="mt-2 whitespace-pre-wrap">
                {error.technicalDetail}
              </pre>
            </details>
          )}
          {onRetry && (
            <button onClick={onRetry} className="button-secondary mt-3">
              Retry status check
            </button>
          )}
        </div>
      )}
    </section>
  );
}
