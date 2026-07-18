import type { Job, VodCandidate } from "@/lib/api";

export type WorkflowType = "vertical_manual" | "longform_automatic";
export type WorkflowStep =
  | "source"
  | "analyze"
  | "candidates"
  | "raw-preview"
  | "edit"
  | "render"
  | "review"
  | "publish";

export type ClipRange = { start: string; end: string };

export type EditSettings = {
  removeSilences: boolean;
  normalizeAudio: boolean;
  generateSubtitles: boolean;
  outputFormat: "horizontal" | "vertical";
  smartVerticalLayout: boolean;
  streamerProfile: string;
};

export type ClipProjectState = {
  workflowType: WorkflowType;
  sourceUrl: string;
  range: ClipRange;
  title: string;
  candidate?: VodCandidate;
  rawPreviewJob?: Job;
  renderJob?: Job;
  editSettings: EditSettings;
  updatedAt: string;
};

export const verticalDefaults: EditSettings = {
  removeSilences: true,
  normalizeAudio: true,
  generateSubtitles: true,
  outputFormat: "vertical",
  smartVerticalLayout: true,
  streamerProfile: "auto",
};

export const horizontalDefaults: EditSettings = {
  removeSilences: false,
  normalizeAudio: true,
  generateSubtitles: false,
  outputFormat: "horizontal",
  smartVerticalLayout: false,
  streamerProfile: "auto",
};

export const cleanExportDefaults: EditSettings = {
  removeSilences: false,
  normalizeAudio: false,
  generateSubtitles: false,
  outputFormat: "horizontal",
  smartVerticalLayout: false,
  streamerProfile: "auto",
};
