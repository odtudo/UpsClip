"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { ClipEditor } from "@/components/editor/clip-editor";
import { PublishPanel } from "@/components/publishing/publish-panel";
import { VideoPreview } from "@/components/video/video-preview";
import { ProgressPanel } from "@/components/workflow/progress-panel";
import { WorkflowStepper } from "@/components/workflow/workflow-stepper";
import {
  createJob,
  getJob,
  getSetupStatus,
  getVodAnalysis,
  listProfiles,
  videoUrl,
  type Job,
  type SetupStatus,
  type StreamerProfile,
  type VodCandidate,
} from "@/lib/api";
import { useJobPolling } from "@/hooks/use-job-polling";
import { loadProject, saveProject } from "@/lib/workflow/storage";
import { formatTimestamp } from "@/lib/workflow/validation";
import {
  horizontalDefaults,
  type ClipProjectState,
  type EditSettings,
  type WorkflowStep,
} from "@/types/workflow";

const steps: Array<{ id: WorkflowStep; label: string }> = [
  { id: "source", label: "Source" },
  { id: "analyze", label: "Analyze" },
  { id: "candidates", label: "Candidates" },
  { id: "raw-preview", label: "Raw Preview" },
  { id: "edit", label: "Edit" },
  { id: "render", label: "Render" },
  { id: "review", label: "Review" },
  { id: "publish", label: "Publish" },
];

function CandidateCard({
  candidate,
  onSelect,
  disabled,
}: {
  candidate: VodCandidate;
  onSelect: (candidate: VodCandidate) => void;
  disabled: boolean;
}) {
  return (
    <article className="surface p-5">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-lg font-semibold">{candidate.title}</h2>
          <p className="mt-1 text-xs text-muted">
            {formatTimestamp(candidate.safe_start_seconds)}–
            {formatTimestamp(candidate.safe_end_seconds)} ·{" "}
            {formatTimestamp(
              candidate.safe_end_seconds - candidate.safe_start_seconds,
            )}
          </p>
        </div>
        <span className="rounded-full bg-accent/10 px-2.5 py-1 text-sm font-semibold text-accentSoft">
          {Math.round(candidate.score)}
        </span>
      </div>
      <p className="mt-4 text-sm leading-6 text-secondary">
        {candidate.summary}
      </p>
      <div className="mt-4 flex flex-wrap gap-2">
        {candidate.keywords.map((keyword) => (
          <span
            key={keyword}
            className="rounded-full border border-line bg-elevated px-2.5 py-1 text-xs text-secondary"
          >
            {keyword}
          </span>
        ))}
      </div>
      <details className="mt-4 border-t border-line pt-4 text-sm text-secondary">
        <summary className="cursor-pointer font-medium text-primary">
          Representative excerpts
        </summary>
        <div className="mt-3 space-y-2">
          {candidate.representative_sentences.map((sentence, index) => (
            <p key={index}>{sentence}</p>
          ))}
        </div>
      </details>
      <details className="mt-3 text-xs text-secondary">
        <summary className="cursor-pointer font-medium text-primary">
          Advanced score breakdown
        </summary>
        <dl className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-3">
          <div>
            <dt>Coherence</dt>
            <dd>
              {Math.round(candidate.score_breakdown.semantic_coherence * 100)}%
            </dd>
          </div>
          <div>
            <dt>Grounding</dt>
            <dd>
              {Math.round(candidate.score_breakdown.title_grounding * 100)}%
            </dd>
          </div>
          <div>
            <dt>Keywords</dt>
            <dd>
              {Math.round(candidate.score_breakdown.keyword_quality * 100)}%
            </dd>
          </div>
          <div>
            <dt>Opening</dt>
            <dd>
              {Math.round(candidate.score_breakdown.opening_quality * 100)}%
            </dd>
          </div>
          <div>
            <dt>Closing</dt>
            <dd>
              {Math.round(candidate.score_breakdown.closing_quality * 100)}%
            </dd>
          </div>
        </dl>
      </details>
      <button
        disabled={disabled}
        onClick={() => onSelect(candidate)}
        className="button-primary mt-5"
      >
        {disabled ? "Preparing preview…" : "Use this clip"}
      </button>
    </article>
  );
}

export function LongformWorkflow({ analysisId }: { analysisId: string }) {
  const router = useRouter();
  const search = useSearchParams();
  const requestedStep = (search.get("step") || "analyze") as WorkflowStep;
  const previewId = search.get("preview");
  const renderId = search.get("render");
  const analysisFetcher = useCallback(
    (id: string, signal?: AbortSignal) => getVodAnalysis(id, signal),
    [],
  );
  const jobFetcher = useCallback(
    (id: string, signal?: AbortSignal) => getJob(id, signal),
    [],
  );
  const analysisPoll = useJobPolling(analysisId, analysisFetcher);
  const previewPoll = useJobPolling(previewId, jobFetcher);
  const renderPoll = useJobPolling(renderId, jobFetcher);
  const [project, setProject] = useState<ClipProjectState | null>(null);
  const [profiles, setProfiles] = useState<StreamerProfile[]>([]);
  const [setup, setSetup] = useState<SetupStatus | null>(null);
  const [submitting, setSubmitting] = useState(false);
  useEffect(() => {
    queueMicrotask(() => setProject(loadProject(analysisId)));
    void listProfiles().then(setProfiles);
    void getSetupStatus().then(setSetup);
  }, [analysisId]);
  useEffect(() => {
    if (
      analysisPoll.value?.status === "completed" &&
      requestedStep === "analyze"
    )
      router.replace(`/long-form/${analysisId}?step=candidates`);
  }, [analysisPoll.value?.status, analysisId, requestedStep, router]);
  useEffect(() => {
    if (renderPoll.value?.status === "ready" && requestedStep === "render")
      router.replace(
        `/long-form/${analysisId}?step=review&preview=${previewId}&render=${renderPoll.value.id}`,
      );
  }, [
    renderPoll.value?.status,
    renderPoll.value?.id,
    requestedStep,
    router,
    analysisId,
    previewId,
  ]);
  const analysis = analysisPoll.value;
  const preview = previewPoll.value || project?.rawPreviewJob || null;
  const render = renderPoll.value || project?.renderJob || null;
  const settings = project?.editSettings || horizontalDefaults;
  const navigate = (step: WorkflowStep, query = "") =>
    router.push(`/long-form/${analysisId}?step=${step}${query}`);
  async function select(candidate: VodCandidate) {
    if (!analysis || submitting) return;
    setSubmitting(true);
    try {
      const previewJob = await createJob({
        source_url: analysis.source_url,
        start: formatTimestamp(candidate.safe_start_seconds),
        end: formatTimestamp(candidate.safe_end_seconds),
        remove_silences: false,
        normalize_audio: false,
        generate_subtitles: false,
        output_format: "horizontal",
        smart_vertical_layout: false,
        streamer_profile: "auto",
        demo: false,
        youtube_title: candidate.title,
        job_kind: "raw_preview",
        workflow_type: "longform_automatic",
        project_id: analysisId,
      });
      const next: ClipProjectState = {
        workflowType: "longform_automatic",
        sourceUrl: analysis.source_url,
        range: {
          start: formatTimestamp(candidate.safe_start_seconds),
          end: formatTimestamp(candidate.safe_end_seconds),
        },
        title: candidate.title,
        candidate,
        rawPreviewJob: previewJob,
        editSettings: horizontalDefaults,
        updatedAt: new Date().toISOString(),
      };
      setProject(next);
      saveProject(analysisId, next);
      navigate("raw-preview", `&preview=${previewJob.id}`);
    } finally {
      setSubmitting(false);
    }
  }
  function updateSettings(value: EditSettings) {
    if (!project) return;
    const next = {
      ...project,
      editSettings: value,
      updatedAt: new Date().toISOString(),
    };
    setProject(next);
    saveProject(analysisId, next);
  }
  async function startRender() {
    if (!preview || submitting) return;
    setSubmitting(true);
    try {
      const created = await createJob({
        source_url: preview.source_url,
        start: project?.range.start ?? formatTimestamp(preview.start_seconds),
        end: project?.range.end ?? formatTimestamp(preview.end_seconds),
        remove_silences: settings.removeSilences,
        normalize_audio: settings.normalizeAudio,
        generate_subtitles: settings.generateSubtitles,
        output_format: "horizontal",
        smart_vertical_layout: false,
        streamer_profile: "auto",
        demo: preview.demo,
        youtube_title:
          project?.title ??
          preview.youtube_title ??
          preview.source_title ??
          "Long-form clip",
        source_job_id: preview.id,
        job_kind: "render",
        workflow_type: "longform_automatic",
        project_id: analysisId,
      });
      if (project) {
        const next = {
          ...project,
          renderJob: created,
          updatedAt: new Date().toISOString(),
        };
        setProject(next);
        saveProject(analysisId, next);
      }
      navigate("render", `&preview=${preview.id}&render=${created.id}`);
    } finally {
      setSubmitting(false);
    }
  }
  return (
    <div>
      <WorkflowStepper steps={steps} current={requestedStep} />
      {requestedStep === "analyze" && (
        <div>
          <p className="eyebrow">Analyze</p>
          <h1 className="mt-2 text-3xl font-semibold">
            Finding conversation candidates
          </h1>
          <div className="mt-8">
            <ProgressPanel
              job={analysis}
              error={analysisPoll.error}
              onRetry={() => void analysisPoll.refresh()}
            />
          </div>
        </div>
      )}
      {requestedStep === "candidates" && (
        <div>
          <p className="eyebrow">Candidates</p>
          <h1 className="mt-2 text-3xl font-semibold">
            Choose an interval to review
          </h1>
          <p className="mt-3 text-secondary">
            Selecting a candidate creates a clean RAW preview. It does not apply
            final edits.
          </p>
          <div className="mt-8 grid gap-4 lg:grid-cols-2">
            {analysis?.result?.candidates?.map((candidate) => (
              <CandidateCard
                key={candidate.id}
                candidate={candidate}
                onSelect={(value) => void select(value)}
                disabled={submitting}
              />
            ))}
          </div>
          {analysis?.result?.candidates?.length === 0 && (
            <div className="surface mt-8 p-8 text-center text-secondary">
              No intervals passed the editorial quality gate.
            </div>
          )}
          <details className="surface mt-6 p-4 text-sm text-secondary">
            <summary className="cursor-pointer font-medium text-primary">
              Rejected candidates
            </summary>
            <p className="mt-3">
              Intervals excluded because they did not meet grounding or quality
              requirements. Detailed artifacts remain available to engineering
              tools.
            </p>
          </details>
        </div>
      )}
      {requestedStep === "raw-preview" && (
        <div>
          <p className="eyebrow">Raw Preview</p>
          <h1 className="mt-2 text-3xl font-semibold">
            Verify the selected topic
          </h1>
          {preview && ["ready", "completed"].includes(preview.status) ? (
            <div className="mt-8 grid gap-6 lg:grid-cols-[minmax(0,1fr)_20rem]">
              <VideoPreview
                src={videoUrl(preview)}
                orientation="horizontal"
                title="Raw candidate preview"
              />
              <aside className="surface p-5">
                <h2 className="font-semibold">{project?.title}</h2>
                <p className="mt-2 text-sm text-secondary">
                  {project?.candidate?.summary}
                </p>
                <p className="mt-4 text-xs text-muted">
                  {project?.range.start}–{project?.range.end}
                </p>
                <button
                  onClick={() => navigate("candidates")}
                  className="button-secondary mt-6 w-full"
                >
                  Back to Candidates
                </button>
                <button
                  onClick={() => navigate("edit", `&preview=${preview.id}`)}
                  className="button-primary mt-3 w-full"
                >
                  Continue to Edit
                </button>
              </aside>
            </div>
          ) : (
            <div className="mt-8">
              <ProgressPanel
                job={preview}
                error={previewPoll.error}
                onRetry={() => void previewPoll.refresh()}
              />
            </div>
          )}
        </div>
      )}
      {requestedStep === "edit" && (
        <div>
          <p className="eyebrow">Edit</p>
          <h1 className="mt-2 text-3xl font-semibold">
            Configure horizontal output
          </h1>
          <div className="mt-8">
            <ClipEditor
              value={settings}
              onChange={updateSettings}
              profiles={profiles}
              workflow="horizontal"
            />
          </div>
          <div className="mt-8 flex justify-between">
            <button
              onClick={() =>
                navigate("raw-preview", preview ? `&preview=${preview.id}` : "")
              }
              className="button-secondary"
            >
              Back to Raw Preview
            </button>
            <button
              disabled={submitting}
              onClick={() => void startRender()}
              className="button-primary"
            >
              {submitting ? "Creating render…" : "Render Clip"}
            </button>
          </div>
        </div>
      )}
      {requestedStep === "render" && (
        <div>
          <p className="eyebrow">Render</p>
          <h1 className="mt-2 text-3xl font-semibold">
            Building the final video
          </h1>
          <div className="mt-8">
            <ProgressPanel
              job={render}
              error={renderPoll.error}
              onRetry={() => void renderPoll.refresh()}
            />
          </div>
        </div>
      )}
      {requestedStep === "review" && render && (
        <div>
          <p className="eyebrow">Final Review</p>
          <h1 className="mt-2 text-3xl font-semibold">
            Check the horizontal render
          </h1>
          <div className="mt-8 grid gap-6 lg:grid-cols-[minmax(0,1fr)_20rem]">
            <VideoPreview
              src={videoUrl(render)}
              orientation="horizontal"
              title="Final long-form video"
            />
            <aside className="surface p-5">
              <h2 className="font-semibold">{project?.title}</h2>
              <p className="mt-3 text-sm text-secondary">
                Duration {formatTimestamp(render.rendered_duration || 0)} ·{" "}
                {render.rendered_size
                  ? `${(render.rendered_size / 1_048_576).toFixed(1)} MB`
                  : "size unknown"}
              </p>
              <a
                href={videoUrl(render) || "#"}
                download
                className="button-secondary mt-6 w-full"
              >
                Download
              </a>
              <button
                onClick={() =>
                  navigate(
                    "edit",
                    `&preview=${preview?.id || ""}&render=${render.id}`,
                  )
                }
                className="button-secondary mt-3 w-full"
              >
                Edit and render again
              </button>
              <button
                onClick={() =>
                  navigate(
                    "publish",
                    `&preview=${preview?.id || ""}&render=${render.id}`,
                  )
                }
                className="button-primary mt-3 w-full"
              >
                Continue to Publish
              </button>
            </aside>
          </div>
        </div>
      )}
      {requestedStep === "publish" && render && (
        <div>
          <p className="eyebrow">Publish</p>
          <h1 className="mt-2 text-3xl font-semibold">Choose a destination</h1>
          <div className="mt-8">
            <PublishPanel
              job={render}
              setup={setup}
              onChanged={(job: Job) => {
                if (!project) return;
                const next = {
                  ...project,
                  renderJob: job,
                  updatedAt: new Date().toISOString(),
                };
                setProject(next);
                saveProject(analysisId, next);
              }}
            />
          </div>
        </div>
      )}
    </div>
  );
}
