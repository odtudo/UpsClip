"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
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
  listProfiles,
  videoUrl,
  type Job,
  type SetupStatus,
  type StreamerProfile,
} from "@/lib/api";
import { loadProject, saveProject } from "@/lib/workflow/storage";
import { formatTimestamp } from "@/lib/workflow/validation";
import { useJobPolling } from "@/hooks/use-job-polling";
import {
  verticalDefaults,
  type ClipProjectState,
  type EditSettings,
  type WorkflowStep,
} from "@/types/workflow";

const steps: Array<{ id: WorkflowStep; label: string }> = [
  { id: "source", label: "Source" },
  { id: "raw-preview", label: "Raw Preview" },
  { id: "edit", label: "Edit" },
  { id: "render", label: "Render" },
  { id: "review", label: "Review" },
  { id: "publish", label: "Publish" },
];

export function VerticalWorkflow({ previewId }: { previewId: string }) {
  const router = useRouter();
  const search = useSearchParams();
  const requestedStep = (search.get("step") || "raw-preview") as WorkflowStep;
  const renderId = search.get("render");
  const previewFetcher = useCallback(
    (id: string, signal?: AbortSignal) => getJob(id, signal),
    [],
  );
  const renderFetcher = useCallback(
    (id: string, signal?: AbortSignal) => getJob(id, signal),
    [],
  );
  const previewPoll = useJobPolling(previewId, previewFetcher);
  const renderPoll = useJobPolling(renderId, renderFetcher);
  const [project, setProject] = useState<ClipProjectState | null>(null);
  const [profiles, setProfiles] = useState<StreamerProfile[]>([]);
  const [setup, setSetup] = useState<SetupStatus | null>(null);
  const [submitting, setSubmitting] = useState(false);
  useEffect(() => {
    queueMicrotask(() => setProject(loadProject(previewId)));
    void listProfiles().then(setProfiles);
    void getSetupStatus().then(setSetup);
  }, [previewId]);
  useEffect(() => {
    if (renderPoll.value?.status === "ready" && requestedStep === "render")
      router.replace(
        `/vertical/${previewId}?step=review&render=${renderPoll.value.id}`,
      );
  }, [
    renderPoll.value?.status,
    renderPoll.value?.id,
    requestedStep,
    router,
    previewId,
  ]);
  const preview = previewPoll.value || project?.rawPreviewJob || null;
  const render = renderPoll.value || project?.renderJob || null;
  const current = requestedStep;
  const settings = project?.editSettings || verticalDefaults;
  const navigate = (step: WorkflowStep, extra = "") =>
    router.push(`/vertical/${previewId}?step=${step}${extra}`);
  function updateSettings(value: EditSettings) {
    if (!project) return;
    const next = {
      ...project,
      editSettings: value,
      updatedAt: new Date().toISOString(),
    };
    setProject(next);
    saveProject(previewId, next);
  }
  async function startRender() {
    if (!preview || submitting) return;
    setSubmitting(true);
    try {
      const created = await createJob({
        source_url: preview.source_url,
        start: formatTimestamp(preview.start_seconds),
        end: formatTimestamp(preview.end_seconds),
        remove_silences: settings.removeSilences,
        normalize_audio: settings.normalizeAudio,
        generate_subtitles: settings.generateSubtitles,
        output_format: settings.outputFormat,
        smart_vertical_layout: settings.smartVerticalLayout,
        streamer_profile: settings.streamerProfile,
        demo: preview.demo,
        source_job_id: preview.id,
        job_kind: "render",
        workflow_type: "vertical_manual",
        project_id: previewId,
        youtube_title: project?.title,
      });
      if (project) {
        const next = {
          ...project,
          renderJob: created,
          updatedAt: new Date().toISOString(),
        };
        setProject(next);
        saveProject(previewId, next);
      }
      navigate("render", `&render=${created.id}`);
    } finally {
      setSubmitting(false);
    }
  }
  const metadata = useMemo(
    () =>
      preview
        ? [
            {
              label: "Interval",
              value: `${formatTimestamp(preview.start_seconds)}–${formatTimestamp(preview.end_seconds)}`,
            },
            {
              label: "Duration",
              value: formatTimestamp(
                preview.end_seconds - preview.start_seconds,
              ),
            },
            { label: "Status", value: preview.status },
            {
              label: "File",
              value: preview.rendered_size
                ? `${(preview.rendered_size / 1_048_576).toFixed(1)} MB`
                : "Processing",
            },
          ]
        : [],
    [preview],
  );
  return (
    <div>
      <WorkflowStepper steps={steps} current={current} />
      {current === "raw-preview" && (
        <div>
          <div className="flex items-end justify-between gap-4">
            <div>
              <p className="eyebrow">Raw Preview</p>
              <h1 className="mt-2 text-3xl font-semibold">
                Review the selected interval
              </h1>
            </div>
            <Link href="/vertical/new" className="button-secondary">
              Change timestamps
            </Link>
          </div>
          {preview && ["ready", "completed"].includes(preview.status) ? (
            <div className="mt-8 grid gap-6 lg:grid-cols-[minmax(0,1fr)_20rem]">
              <VideoPreview
                src={videoUrl(preview)}
                orientation="horizontal"
                title="Raw VOD interval"
              />
              <aside className="surface p-5">
                <h2 className="font-semibold">Source details</h2>
                <dl className="mt-4 space-y-4">
                  {metadata.map((item) => (
                    <div key={item.label}>
                      <dt className="text-xs text-muted">{item.label}</dt>
                      <dd className="mt-1 text-sm font-medium capitalize">
                        {item.value}
                      </dd>
                    </div>
                  ))}
                </dl>
                <button
                  onClick={() => navigate("edit")}
                  className="button-primary mt-6 w-full"
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
      {current === "edit" && (
        <div>
          <p className="eyebrow">Edit</p>
          <h1 className="mt-2 text-3xl font-semibold">
            Configure the final clip
          </h1>
          <p className="mt-3 text-secondary">
            The same editor powers manual and automatic workflows.
          </p>
          <div className="mt-8">
            <ClipEditor
              value={settings}
              onChange={updateSettings}
              profiles={profiles}
              workflow="vertical"
            />
          </div>
          <div className="mt-8 flex justify-between">
            <button
              onClick={() => navigate("raw-preview")}
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
      {current === "render" && (
        <div>
          <p className="eyebrow">Render</p>
          <h1 className="mt-2 text-3xl font-semibold">
            Building the final clip
          </h1>
          <div className="mt-8">
            <ProgressPanel
              job={render}
              error={renderPoll.error}
              onRetry={() => void renderPoll.refresh()}
            />
          </div>
          {render?.status === "ready" && (
            <button
              onClick={() => navigate("review", `&render=${render.id}`)}
              className="button-primary mt-6"
            >
              Review final video
            </button>
          )}
        </div>
      )}
      {current === "review" && render && (
        <div>
          <p className="eyebrow">Final Review</p>
          <h1 className="mt-2 text-3xl font-semibold">
            Check the finished render
          </h1>
          <div className="mt-8 grid gap-6 lg:grid-cols-[minmax(0,1fr)_20rem]">
            <VideoPreview
              src={videoUrl(render)}
              orientation="vertical"
              title="Final vertical clip"
            />
            <aside className="surface p-5">
              <h2 className="font-semibold">Render details</h2>
              <dl className="mt-4 space-y-3 text-sm">
                <div>
                  <dt className="text-muted">Duration</dt>
                  <dd>{formatTimestamp(render.rendered_duration || 0)}</dd>
                </div>
                <div>
                  <dt className="text-muted">Orientation</dt>
                  <dd>Vertical · 9:16</dd>
                </div>
                <div>
                  <dt className="text-muted">Size</dt>
                  <dd>
                    {render.rendered_size
                      ? `${(render.rendered_size / 1_048_576).toFixed(1)} MB`
                      : "Unknown"}
                  </dd>
                </div>
              </dl>
              <a
                href={videoUrl(render) || "#"}
                download
                className="button-secondary mt-6 w-full"
              >
                Download
              </a>
              <button
                onClick={() => navigate("edit", `&render=${render.id}`)}
                className="button-secondary mt-3 w-full"
              >
                Edit and render again
              </button>
              <button
                onClick={() => navigate("publish", `&render=${render.id}`)}
                className="button-primary mt-3 w-full"
              >
                Continue to Publish
              </button>
            </aside>
          </div>
        </div>
      )}
      {current === "publish" && render && (
        <div>
          <p className="eyebrow">Publish</p>
          <h1 className="mt-2 text-3xl font-semibold">Choose a destination</h1>
          <div className="mt-8">
            <PublishPanel
              job={render}
              setup={setup}
              onChanged={(job: Job) => {
                const next = project
                  ? {
                      ...project,
                      renderJob: job,
                      updatedAt: new Date().toISOString(),
                    }
                  : null;
                if (next) {
                  setProject(next);
                  saveProject(previewId, next);
                }
              }}
            />
          </div>
        </div>
      )}
    </div>
  );
}
