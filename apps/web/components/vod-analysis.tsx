"use client";

import { FormEvent, useEffect, useState } from "react";
import { CreateJobInput, VodAnalysisJob, VodCandidate, createVodAnalysis, getVodAnalysis } from "@/lib/api";

const stageLabels: Record<string, string> = {
  queued: "Queued",
  reading_metadata: "Reading VOD metadata",
  preparing_visual_stream: "Preparing visual stream",
  sampling_layout_frames: "Sampling OBS layout frames",
  detecting_faces: "Detecting faces",
  smoothing_layouts: "Confirming visual transitions",
  building_layout_timeline: "Building visual timeline",
  completed: "Visual analysis completed",
  preparing_analysis_audio: "Preparing analysis audio",
  preparing_stream_access: "Preparing stream access",
  sampling_audio: "Sampling audio",
  measuring_speech: "Measuring speech",
  running_transcript_probes: "Running transcript probes",
  sampling_video: "Sampling video",
  building_coarse_timeline: "Building coarse timeline",
  loading_coarse_timeline: "Loading coarse timeline",
  sampling_obs_layout: "Sampling OBS layout",
  smoothing_obs_layout: "Confirming visual transitions",
  coarse_analysis_completed: "Coarse analysis completed",
  scoring_phase_windows: "Scoring phase windows",
  smoothing_timeline: "Smoothing timeline",
  detecting_phase_transitions: "Detecting phase transitions",
  building_talking_blocks: "Building talking blocks",
  selecting_conversation_blocks: "Selecting conversation blocks",
  phase_analysis_completed: "Phase analysis completed",
  detecting_stream_phases: "Detecting stream phases",
  locating_talking_block: "Locating the talking block",
  transcribing_conversation: "Transcribing conversation",
  detecting_topic_boundaries: "Detecting topic boundaries",
  building_clip_candidates: "Building clip candidates",
  ranking_candidates: "Ranking candidates",
  analysis_completed: "Analysis completed",
  failed: "Analysis failed",
};

function timestamp(seconds: number): string {
  const value = Math.max(0, Math.round(seconds));
  const hours = Math.floor(value / 3600);
  const minutes = Math.floor((value % 3600) / 60);
  const secs = value % 60;
  return hours > 0
    ? `${hours.toString().padStart(2, "0")}:${minutes.toString().padStart(2, "0")}:${secs.toString().padStart(2, "0")}`
    : `${minutes.toString().padStart(2, "0")}:${secs.toString().padStart(2, "0")}`;
}

const phaseLabels = { waiting_or_music: "Waiting / Music", talking: "Talking", gameplay: "Gameplay", unknown: "Unknown" } as const;
const phaseColors = { waiting_or_music: "bg-amber-300", talking: "bg-emerald-500", gameplay: "bg-violet-500", unknown: "bg-zinc-400" } as const;

function CandidateCard({ candidate, sourceUrl, onGenerate }: {
  candidate: VodCandidate;
  sourceUrl: string;
  onGenerate: (input: CreateJobInput) => Promise<void>;
}) {
  const [title, setTitle] = useState(candidate.title);
  const [start, setStart] = useState(timestamp(candidate.safe_start_seconds));
  const [end, setEnd] = useState(timestamp(candidate.safe_end_seconds));
  const [generating, setGenerating] = useState(false);
  const twitch = sourceUrl.includes("twitch.tv/videos/");

  async function generate() {
    setGenerating(true);
    try {
      await onGenerate({
        source_url: sourceUrl,
        start,
        end,
        remove_silences: true,
        normalize_audio: true,
        generate_subtitles: false,
        output_format: "horizontal",
        smart_vertical_layout: false,
        streamer_profile: "auto",
        demo: false,
        youtube_title: title,
      });
    } finally {
      setGenerating(false);
    }
  }

  return (
    <article className="rounded-2xl border border-zinc-200 bg-white p-5 shadow-sm">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <input aria-label="Candidate title" value={title} onChange={(event) => setTitle(event.target.value)} className="min-w-0 flex-1 border-b border-transparent text-lg font-semibold focus:border-twitch focus:outline-none" />
        <span className="rounded-full bg-violet-100 px-3 py-1 text-sm font-bold text-violet-800">{Math.round(candidate.score)}/100</span>
      </div>
      <p className="mt-3 text-sm leading-6 text-zinc-600">{candidate.summary}</p>
      <div className="mt-3 flex flex-wrap gap-2">{candidate.keywords.map((word) => <span key={word} className="rounded-full bg-zinc-100 px-2.5 py-1 text-xs">{word}</span>)}</div>
      <div className="mt-4 grid grid-cols-2 gap-3">
        <label className="text-xs font-semibold text-zinc-600">Start<input value={start} onChange={(event) => setStart(event.target.value)} className="mt-1 w-full rounded-lg border border-zinc-300 px-3 py-2 text-sm" /></label>
        <label className="text-xs font-semibold text-zinc-600">End<input value={end} onChange={(event) => setEnd(event.target.value)} className="mt-1 w-full rounded-lg border border-zinc-300 px-3 py-2 text-sm" /></label>
      </div>
      <details className="mt-4 rounded-lg bg-zinc-50 p-3 text-sm text-zinc-600"><summary className="cursor-pointer font-semibold text-zinc-800">Transcript preview</summary><p className="mt-2 leading-6">{candidate.transcript_preview}</p></details>
      {candidate.warnings.length > 0 && <p className="mt-3 text-xs text-amber-700">Warnings: {candidate.warnings.join(", ")}</p>}
      <button type="button" disabled={!twitch || generating} onClick={() => void generate()} className="mt-4 w-full rounded-xl bg-twitch px-4 py-2.5 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-50">
        {generating ? "Creating render job…" : "Generate clip"}
      </button>
      {!twitch && <p className="mt-2 text-xs text-zinc-500">YouTube candidate generation is planned for Phase 5.</p>}
    </article>
  );
}

export function VodAnalysis({ onGenerate }: { onGenerate: (input: CreateJobInput) => Promise<void> }) {
  const [url, setUrl] = useState("https://www.twitch.tv/videos/123456789");
  const [force, setForce] = useState(false);
  const [job, setJob] = useState<VodAnalysisJob | null>(null);
  const [cached, setCached] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const active = job?.status === "queued" || job?.status === "processing";

  useEffect(() => {
    if (!active || !job) return;
    const timer = window.setInterval(async () => {
      try { setJob(await getVodAnalysis(job.id)); }
      catch (caught) { setError(caught instanceof Error ? caught.message : "Could not read analysis progress"); }
    }, 800);
    return () => window.clearInterval(timer);
  }, [active, job]);

  async function analyze(event: FormEvent) {
    event.preventDefault();
    setError(null);
    try {
      const started = await createVodAnalysis({ url, streamer: "illojuan", force_reanalyze: force });
      setCached(started.cached);
      setJob(await getVodAnalysis(started.job_id));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "The VOD analysis could not be started");
    }
  }

  return (
    <div className="grid items-start gap-7 lg:grid-cols-[23rem_1fr]">
      <form onSubmit={analyze} className="rounded-2xl bg-panel p-5 shadow-soft sm:p-7">
        <p className="text-xs font-semibold uppercase tracking-[0.18em] text-twitch">Automatic VOD Analysis</p>
        <h2 className="mt-1 text-xl font-semibold">Find conversation clips</h2>
        <label className="mt-6 block text-sm font-medium">Twitch or YouTube VOD URL<input type="url" required value={url} onChange={(event) => setUrl(event.target.value)} className="mt-1.5 w-full rounded-xl border border-zinc-300 px-3.5 py-2.5 text-sm" /></label>
        <label className="mt-4 block text-sm font-medium">Streamer<select value="illojuan" disabled className="mt-1.5 w-full rounded-xl border border-zinc-300 bg-zinc-50 px-3.5 py-2.5 text-sm"><option value="illojuan">IlloJuan</option></select></label>
        <label className="mt-4 flex gap-3 text-sm"><input type="checkbox" checked={force} onChange={(event) => setForce(event.target.checked)} />Ignore cached analysis</label>
        <button disabled={Boolean(active)} className="mt-5 w-full rounded-xl bg-twitch px-4 py-3 text-sm font-semibold text-white disabled:opacity-60">{active ? "Analyzing…" : "Analyze VOD"}</button>
        <p className="mt-3 text-xs leading-5 text-zinc-500">Real mode samples short audio and reduced frames. Fixture mode remains available for development.</p>
      </form>

      <section>
        {error && <p className="mb-4 rounded-xl bg-red-50 p-4 text-sm text-red-700">{error}</p>}
        {job && <div className="mb-4 rounded-2xl border border-zinc-200 bg-white p-5">
          <div className="flex justify-between gap-4"><strong>{stageLabels[job.stage] || job.stage}</strong><span>{job.progress}%</span></div>
          <div className="mt-3 h-2 overflow-hidden rounded-full bg-zinc-100"><div className="h-full bg-twitch transition-all" style={{ width: `${job.progress}%` }} /></div>
          {job.total_windows > 0 && <p className="mt-2 text-xs text-zinc-600">{job.completed_windows}/{job.total_windows} windows · current timestamp {timestamp(job.current_timestamp)}</p>}
          {(cached || job.cached) && <p className="mt-3 text-sm font-medium text-emerald-700">Cached analysis reused</p>}
          {job.error_message && <p className="mt-3 text-sm text-red-700">{job.error_message}</p>}
        </div>}
        {job?.status === "completed" && job.result?.coarse_timeline && !job.result.phase_timeline && <div className="rounded-2xl border border-emerald-200 bg-emerald-50 p-5 text-sm text-emerald-900">
          <h2 className="text-lg font-semibold">Coarse signal timeline ready</h2>
          <p className="mt-2">{job.result.coarse_timeline.completed_windows} windows over {timestamp(job.result.coarse_timeline.analyzed_duration_seconds)}. Phase 2 does not classify phases or build candidates.</p>
          <p className="mt-1">Estimated transferred media: {(job.result.coarse_timeline.bytes_downloaded / 1_000_000).toFixed(1)} MB.</p>
        </div>}
        {job?.status === "completed" && job.result?.phase_timeline && <div className="space-y-5">
          <section className="rounded-2xl border border-zinc-200 bg-white p-5 shadow-sm">
            <h2 className="text-lg font-semibold">Stream phase timeline</h2>
            <div className="mt-4 flex h-8 overflow-hidden rounded-lg" aria-label="VOD phase timeline">
              {job.result.phase_timeline.segments.map((segment, index) => <div key={`${segment.start}-${index}`} title={`${phaseLabels[segment.phase]} ${timestamp(segment.start)}–${timestamp(segment.end)}`} className={phaseColors[segment.phase]} style={{ flexGrow: segment.end - segment.start, minWidth: 3 }} />)}
            </div>
            <div className="mt-4 space-y-2">
              {job.result.phase_timeline.segments.map((segment, index) => <div key={`${segment.phase}-${segment.start}-${index}`} className="flex flex-wrap items-center justify-between gap-2 rounded-lg bg-zinc-50 px-3 py-2 text-sm">
                <span className="font-semibold">{phaseLabels[segment.phase]}</span>
                <span>{timestamp(segment.start)}–{timestamp(segment.end)} · {timestamp(segment.end - segment.start)} · {Math.round(segment.confidence * 100)}%</span>
                {segment.warnings.length > 0 && <span className="w-full text-xs text-amber-700">{segment.warnings.join(", ")}</span>}
              </div>)}
            </div>
            {job.result.phase_timeline.warnings.length > 0 && <p className="mt-3 text-sm text-amber-700">Warnings: {job.result.phase_timeline.warnings.join(", ")}</p>}
          </section>
          <section className="rounded-2xl border border-zinc-200 bg-white p-5 shadow-sm">
            <h2 className="text-lg font-semibold">Conversation blocks detected</h2>
            {job.result.phase_timeline.talking_blocks.length === 0 ? <p className="mt-3 text-sm text-zinc-600">No sustained conversation blocks were detected.</p> : <div className="mt-4 space-y-3">{job.result.phase_timeline.talking_blocks.map((block) => <article key={block.id} className="rounded-xl border border-zinc-200 p-4 text-sm">
              <div className="flex flex-wrap justify-between gap-2"><strong>{block.id}{block.id === job.result?.phase_timeline?.primary_talking_block_id ? " · Primary" : ""}</strong><span>Priority {block.priority}</span></div>
              <p className="mt-2">{timestamp(block.start_seconds)}–{timestamp(block.end_seconds)} · {timestamp(block.duration_seconds)} · {Math.round(block.confidence * 100)}%</p>
              <p className="mt-1 text-zinc-600">End: {block.end_transition.replaceAll("_", " ")} · selected for deep transcription: {block.selected_for_deep_transcription ? "yes" : "no"}</p>
              <p className="mt-1 text-xs text-zinc-500">{block.selection_reason.join(", ")}</p>
            </article>)}</div>}
          </section>
        </div>}
        {job?.status === "completed" && job.result?.candidates && <>
          <div className="mb-4"><p className="text-xs font-semibold uppercase tracking-[0.18em] text-zinc-500">Ranked results</p><h2 className="mt-1 text-2xl font-semibold">{job.result.candidates.length} clip candidates</h2></div>
          {job.result.candidates.length === 0 ? <div className="rounded-2xl border border-dashed p-8 text-center text-zinc-600">No segments passed the minimum quality score.</div> : <div className="space-y-4">{job.result.candidates.map((candidate) => <CandidateCard key={candidate.id} candidate={candidate} sourceUrl={job.source_url} onGenerate={onGenerate} />)}</div>}
        </>}
        {!job && <div className="rounded-2xl border border-dashed border-zinc-300 bg-white/70 p-10 text-center text-sm text-zinc-500">Analyze a VOD to see phase progress and ranked candidates.</div>}
      </section>
    </div>
  );
}
