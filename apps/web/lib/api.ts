export const API_URL = (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(/\/$/, "");

export type Job = {
  id: string;
  source_url: string;
  start_seconds: number;
  end_seconds: number;
  remove_silences: boolean;
  normalize_audio: boolean;
  generate_subtitles: boolean;
  output_format: "horizontal" | "vertical";
  smart_vertical_layout: boolean;
  streamer_profile: string;
  resolved_streamer_profile: string | null;
  layout_warnings: Array<{ code: string; start: number; end: number; message: string }>;
  layout_summary: Record<string, number>;
  demo: boolean;
  status: string;
  progress: number;
  current_step: string;
  error_message: string | null;
  source_title: string | null;
  rendered_duration: number | null;
  rendered_size: number | null;
  youtube_url: string | null;
  video_url: string | null;
  created_at: string;
};

export type CreateJobInput = {
  source_url: string;
  start: string;
  end: string;
  remove_silences: boolean;
  normalize_audio: boolean;
  generate_subtitles: boolean;
  output_format: "horizontal" | "vertical";
  smart_vertical_layout: boolean;
  streamer_profile: string;
  demo: boolean;
  youtube_title?: string;
};

export type SetupStatus = {
  ffmpeg_available: boolean;
  ffprobe_available: boolean;
  ytdlp_available: boolean;
  data_writable: boolean;
  youtube_client_secret_present: boolean;
  youtube_token_present: boolean;
  youtube_token_usable: boolean;
  youtube_ready: boolean;
  twitch_cookies_present: boolean;
  database_accessible: boolean;
  face_detector_name: string;
  face_detector_available: boolean;
  face_detector_model_present: boolean;
  face_detector_model_valid: boolean;
  smart_vertical_available: boolean;
  smart_vertical_ready: boolean;
  messages: string[];
};

export type StreamerProfile = { id: string; display_name: string };

export type ScoreBreakdown = {
  topic_coherence: number;
  speech_density: number;
  duration_fit: number;
  opening_quality: number;
  closing_quality: number;
  self_containment: number;
  title_specificity: number;
  emotional_energy: number;
  story_or_opinion_signal: number;
  penalties: string[];
};

export type VodCandidate = {
  id: string;
  exact_start_seconds: number;
  exact_end_seconds: number;
  safe_start_seconds: number;
  safe_end_seconds: number;
  title: string;
  summary: string;
  keywords: string[];
  score: number;
  score_breakdown: ScoreBreakdown;
  transcript_preview: string;
  warnings: string[];
  overlap_ratio: number;
};

export type VodAnalysisJob = {
  id: string;
  source_url: string;
  streamer_profile: string;
  pipeline_version: string;
  status: "queued" | "processing" | "completed" | "failed";
  stage: string;
  progress: number;
  cached: boolean;
  fixture_mode: boolean;
  completed_windows: number;
  total_windows: number;
  current_timestamp: number;
  warnings: string[];
  error_message: string | null;
  result: null | {
    fixture: boolean;
    vod: { platform: "twitch" | "youtube"; title: string; uploader: string; duration_seconds: number };
    analysis?: { talking_start_seconds: number; talking_end_seconds: number; confidence: number };
    candidates?: VodCandidate[];
    phase?: "coarse_signals" | "phase_analysis" | "visual_layout";
    phase_detection_strategy?: string;
    requires_coarse_timeline?: boolean;
    primary_talking_block_id?: string | null;
    phase_summary?: PhaseSummary;
    talking_blocks?: TalkingBlock[];
    selected_talking_blocks?: Array<{ id: string; start_seconds: number; end_seconds: number; priority: number }>;
    phase_timeline?: PhaseTimeline;
    coarse_timeline?: {
      analyzed_duration_seconds: number;
      completed_windows: number;
      total_windows: number;
      bytes_downloaded: number;
    };
  };
};

export type PhaseName = "waiting_or_music" | "talking" | "gameplay" | "unknown";
export type PhaseSummary = {
  waiting_seconds: number; talking_seconds: number; gameplay_seconds: number; unknown_seconds: number;
};
export type PhaseSegment = {
  start: number; end: number; phase: PhaseName; confidence: number; window_count: number;
  reasons: string[]; warnings: string[]; transition_in: string | null; transition_out: string | null;
};
export type TalkingBlock = {
  id: string; start_seconds: number; end_seconds: number; duration_seconds: number;
  confidence: number; priority: number; relevance: "primary" | "secondary" | "low_priority" | "ignored";
  selected_for_deep_transcription: boolean; selection_reason: string[]; end_transition: string;
  warnings: string[];
};
export type PhaseTimeline = {
  pipeline_version: string; segments: PhaseSegment[]; talking_blocks: TalkingBlock[];
  selected_talking_blocks: Array<{ id: string; start_seconds: number; end_seconds: number; priority: number }>;
  primary_talking_block_id: string | null; warnings: string[]; summary: PhaseSummary;
};

export type ValidationNotes = {
  talking_start: number | null; talking_end: number | null;
  gameplay_start: number | null; gameplay_end: number | null;
  talking_block_2_start: number | null; talking_block_2_end: number | null;
  talking_block_3_start: number | null; talking_block_3_end: number | null;
};
export type ValidationComparison = {
  transition: keyof ValidationNotes; detector_seconds: number | null; actual_seconds: number;
  error_seconds: number | null; absolute_error_seconds: number | null;
};
export type ValidationMetrics = {
  mean_absolute_error_seconds: number | null; maximum_absolute_error_seconds: number | null;
  mean_error_by_transition: Record<string, number>; detected_phase_count: number;
  omitted_phase_count: number; false_detection_count: number; mean_confidence: number;
};
export type InspectorSegment = {
  start: number; end: number; phase: PhaseName; confidence: number;
  layout_id: string | null; match_score: number | null;
  second_best_score: number | null; score_margin: number | null;
  reasons: string[]; warnings: string[]; open_url: string;
};
export type VodInspectorResult = {
  job_id: string; source_url: string; streamer_profile: string;
  status: "queued" | "processing" | "completed" | "failed";
  stage: string; progress: number; error_message: string | null; cached: boolean;
  phase_detection_strategy: string; requires_coarse_timeline: boolean;
  metadata: null | { title: string; duration_seconds: number; platform: "twitch" | "youtube" };
  phase_timeline: PhaseTimeline | null; segments: InspectorSegment[];
  validation_notes: ValidationNotes; comparisons: ValidationComparison[];
  metrics: ValidationMetrics | null; export_url: string | null;
};

async function parseResponse<T>(response: Response): Promise<T> {
  if (response.ok) return response.json() as Promise<T>;
  let message = `Request failed (${response.status})`;
  try {
    const body = (await response.json()) as { detail?: string | Array<{ msg: string }> };
    if (typeof body.detail === "string") message = body.detail;
    else if (Array.isArray(body.detail)) message = body.detail.map((item) => item.msg).join("; ");
  } catch {
    // The status text above remains useful for a non-JSON response.
  }
  throw new Error(message);
}

export async function listJobs(): Promise<Job[]> {
  return parseResponse<Job[]>(await fetch(`${API_URL}/jobs`, { cache: "no-store" }));
}

export async function getSetupStatus(): Promise<SetupStatus> {
  return parseResponse<SetupStatus>(await fetch(`${API_URL}/setup/status`, { cache: "no-store" }));
}

export async function listProfiles(): Promise<StreamerProfile[]> {
  return parseResponse<StreamerProfile[]>(await fetch(`${API_URL}/profiles`, { cache: "no-store" }));
}

export async function createJob(input: CreateJobInput): Promise<Job> {
  return parseResponse<Job>(
    await fetch(`${API_URL}/jobs`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(input),
    }),
  );
}

export async function createVodAnalysis(input: {
  url: string;
  streamer: "illojuan";
  force_reanalyze: boolean;
}): Promise<{ job_id: string; cached: boolean }> {
  return parseResponse(
    await fetch(`${API_URL}/vod-analysis`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(input),
    }),
  );
}

export async function getVodAnalysis(id: string): Promise<VodAnalysisJob> {
  return parseResponse<VodAnalysisJob>(await fetch(`${API_URL}/vod-analysis/${id}`, { cache: "no-store" }));
}

export async function createVodInspector(input: {
  url: string; streamer: "illojuan"; force_reanalyze: boolean;
}): Promise<{ job_id: string; cached: boolean }> {
  return parseResponse(await fetch(`${API_URL}/vod-inspector`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(input),
  }));
}

export async function getVodInspector(id: string): Promise<VodInspectorResult> {
  return parseResponse<VodInspectorResult>(
    await fetch(`${API_URL}/vod-inspector/${id}`, { cache: "no-store" }),
  );
}

export async function saveVodInspectorNotes(
  id: string, notes: ValidationNotes,
): Promise<VodInspectorResult> {
  return parseResponse<VodInspectorResult>(await fetch(`${API_URL}/vod-inspector/${id}/validation-notes`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(notes),
  }));
}

export async function deleteJob(id: string): Promise<void> {
  const response = await fetch(`${API_URL}/jobs/${id}`, { method: "DELETE" });
  if (!response.ok) await parseResponse(response);
}

export async function uploadJob(
  id: string,
  metadata: { title: string; description: string; tags: string[]; privacy_status: string },
): Promise<Job> {
  return parseResponse<Job>(
    await fetch(`${API_URL}/jobs/${id}/youtube`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(metadata),
    }),
  );
}
