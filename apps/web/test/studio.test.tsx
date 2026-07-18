import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import HomePage from "@/app/page";
import { ClipEditor } from "@/components/editor/clip-editor";
import { PublishPanel } from "@/components/publishing/publish-panel";
import { VideoPreview } from "@/components/video/video-preview";
import { ProgressPanel } from "@/components/workflow/progress-panel";
import { WorkflowStepper } from "@/components/workflow/workflow-stepper";
import { VerticalSource } from "@/components/workflows/vertical-source";
import {
  cleanExportDefaults,
  horizontalDefaults,
  verticalDefaults,
  type EditSettings,
} from "@/types/workflow";
import {
  formatTimestamp,
  parseTimestamp,
  validateSource,
} from "@/lib/workflow/validation";
import type { Job, SetupStatus } from "@/lib/api";

const push = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push, replace: vi.fn() }),
  usePathname: () => "/",
  useSearchParams: () => new URLSearchParams(),
}));
vi.mock("@/lib/api", async (original) => {
  const actual = await original<typeof import("@/lib/api")>();
  return {
    ...actual,
    createJob: vi.fn(async (input) => ({
      ...job,
      source_url: input.source_url,
      id: "preview-1",
    })),
    uploadJob: vi.fn(async () => job),
  };
});

const job: Job = {
  id: "job-1",
  source_url: "https://www.twitch.tv/videos/123",
  start_seconds: 0,
  end_seconds: 30,
  remove_silences: false,
  normalize_audio: false,
  generate_subtitles: false,
  output_format: "horizontal",
  smart_vertical_layout: false,
  streamer_profile: "auto",
  resolved_streamer_profile: null,
  layout_warnings: [],
  layout_summary: {},
  demo: true,
  status: "ready",
  progress: 100,
  current_step: "Ready for preview",
  error_message: null,
  source_title: "Demo clip",
  rendered_duration: 30,
  rendered_size: 1024,
  youtube_url: null,
  youtube_title: null,
  youtube_description: null,
  tags: [],
  privacy_status: "private",
  video_url: "/jobs/job-1/video",
  created_at: "2026-07-17T00:00:00Z",
  updated_at: "2026-07-17T00:01:00Z",
  source_job_id: null,
  job_kind: "render",
  workflow_type: "vertical_manual",
  project_id: "job-1",
};
const setup = { youtube_ready: true } as SetupStatus;
afterEach(cleanup);

describe("Clipping Studio home and source", () => {
  beforeEach(() => {
    push.mockClear();
    localStorage.clear();
  });
  it("shows both workflows", () => {
    render(<HomePage />);
    expect(screen.getByText("Vertical Clip")).toBeInTheDocument();
    expect(screen.getByText("Long-form Clip")).toBeInTheDocument();
  });
  it("links to vertical source", () => {
    render(<HomePage />);
    expect(
      screen.getByRole("link", { name: /Vertical Clip/i }),
    ).toHaveAttribute("href", "/vertical/new");
  });
  it("links to long-form source", () => {
    render(<HomePage />);
    expect(
      screen.getByRole("link", { name: /Long-form Clip/i }),
    ).toHaveAttribute("href", "/long-form/new");
  });
  it("validates an invalid URL", () => {
    expect(validateSource("not-a-url", "00:00", "00:30").url).toMatch(
      /valid Twitch/i,
    );
  });
  it("rejects end before start", () => {
    expect(
      validateSource("https://www.twitch.tv/videos/123", "00:40", "00:30").end,
    ).toMatch(/later/i);
  });
  it("accepts seconds timestamps", () => {
    expect(parseTimestamp("630")).toBe(630);
  });
  it("accepts hh:mm:ss timestamps", () => {
    expect(parseTimestamp("01:10:30")).toBe(4230);
  });
  it("formats timestamps", () => {
    expect(formatTimestamp(4230)).toBe("01:10:30");
  });
  it("shows accessible validation from Vertical Source", async () => {
    render(<VerticalSource />);
    await userEvent.click(
      screen.getByRole("button", { name: /Generate Raw Preview/i }),
    );
    expect(screen.getByRole("alert")).toBeInTheDocument();
  });
  it("creates only a raw preview from Vertical Source", async () => {
    render(<VerticalSource />);
    await userEvent.type(
      screen.getByLabelText("VOD URL"),
      "https://www.twitch.tv/videos/123",
    );
    await userEvent.click(
      screen.getByRole("button", { name: /Generate Raw Preview/i }),
    );
    await waitFor(() =>
      expect(push).toHaveBeenCalledWith("/vertical/preview-1?step=raw-preview"),
    );
  });
});

describe("shared editor", () => {
  function Editor({
    initial = verticalDefaults,
    workflow = "vertical",
  }: {
    initial?: EditSettings;
    workflow?: "vertical" | "horizontal";
  }) {
    const onChange = vi.fn();
    render(
      <ClipEditor
        value={initial}
        onChange={onChange}
        profiles={[]}
        workflow={workflow}
      />,
    );
    return onChange;
  }
  it("shows the three vertical presets", () => {
    Editor({});
    expect(screen.getByText("Vertical Short")).toBeInTheDocument();
    expect(screen.getByText("Horizontal Long-form")).toBeInTheDocument();
    expect(screen.getByText("Clean Export")).toBeInTheDocument();
  });
  it("applies vertical preset defaults", async () => {
    const onChange = Editor({ initial: cleanExportDefaults });
    await userEvent.click(
      screen.getByRole("button", { name: /Vertical Short/i }),
    );
    expect(onChange).toHaveBeenCalledWith(verticalDefaults);
  });
  it("applies clean export defaults", async () => {
    const onChange = Editor({});
    await userEvent.click(
      screen.getByRole("button", { name: /Clean Export/i }),
    );
    expect(onChange).toHaveBeenCalledWith(cleanExportDefaults);
  });
  it("uses horizontal defaults without smart layout", () => {
    expect(horizontalDefaults.outputFormat).toBe("horizontal");
    expect(horizontalDefaults.smartVerticalLayout).toBe(false);
  });
  it("disables Smart Vertical for horizontal workflow", () => {
    Editor({ initial: horizontalDefaults, workflow: "horizontal" });
    expect(
      screen.getByRole("checkbox", { name: /Smart Vertical Layout/i }),
    ).toBeDisabled();
  });
  it("updates silence shortening", async () => {
    const onChange = Editor({
      initial: horizontalDefaults,
      workflow: "horizontal",
    });
    await userEvent.click(
      screen.getByRole("checkbox", { name: /Shorten long silences/i }),
    );
    expect(onChange).toHaveBeenCalledWith({
      ...horizontalDefaults,
      removeSilences: true,
    });
  });
});

describe("review, progress and publish", () => {
  it("renders a responsive video preview", () => {
    render(
      <VideoPreview
        src="/video.mp4"
        orientation="horizontal"
        title="Raw Preview"
      />,
    );
    expect(screen.getByLabelText("Raw Preview")).toHaveAttribute("controls");
  });
  it("shows unavailable preview state", () => {
    render(
      <VideoPreview src={null} orientation="horizontal" title="Preview" />,
    );
    expect(screen.getByText(/not available yet/i)).toBeInTheDocument();
  });
  it("shows real render progress", () => {
    render(
      <ProgressPanel
        job={{
          ...job,
          status: "rendering",
          progress: 72,
          current_step: "Rendering H.264/AAC video",
        }}
      />,
    );
    expect(screen.getByText("72%")).toBeInTheDocument();
  });
  it("shows understandable polling errors", () => {
    render(
      <ProgressPanel
        job={null}
        error={
          new (class extends Error {
            status = 0;
            technicalDetail = "Fetch failed";
          })() as never
        }
      />,
    );
    expect(screen.getByText(/Fetch failed/i)).toBeInTheDocument();
  });
  it("marks completed workflow steps", () => {
    render(
      <WorkflowStepper
        steps={[
          { id: "source", label: "Source" },
          { id: "edit", label: "Edit" },
        ]}
        current="edit"
      />,
    );
    expect(screen.getByLabelText("Workflow progress")).toBeInTheDocument();
  });
  it("shows YouTube and export destinations", () => {
    render(<PublishPanel job={job} setup={setup} onChanged={vi.fn()} />);
    expect(screen.getByText("YouTube")).toBeInTheDocument();
    expect(screen.getByText("Export only")).toBeInTheDocument();
  });
  it("shows Instagram as coming soon", () => {
    render(<PublishPanel job={job} setup={setup} onChanged={vi.fn()} />);
    expect(
      screen.getByRole("button", { name: /Instagram.*Coming soon/i }),
    ).toBeDisabled();
  });
  it("shows TikTok as coming soon", () => {
    render(<PublishPanel job={job} setup={setup} onChanged={vi.fn()} />);
    expect(
      screen.getByRole("button", { name: /TikTok.*Coming soon/i }),
    ).toBeDisabled();
  });
  it("routes disconnected YouTube users to Settings", () => {
    render(
      <PublishPanel
        job={job}
        setup={{ ...setup, youtube_ready: false }}
        onChanged={vi.fn()}
      />,
    );
    expect(screen.getByRole("link", { name: "Open Settings" })).toHaveAttribute(
      "href",
      "/settings",
    );
  });
});
