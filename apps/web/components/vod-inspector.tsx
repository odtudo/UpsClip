"use client";

import { FormEvent, useEffect, useState } from "react";
import {
  API_URL, ValidationNotes, VodInspectorResult, createVodInspector, getVodInspector,
  saveVodInspectorNotes,
} from "@/lib/api";

const colors = {
  waiting_or_music: "bg-amber-300", talking: "bg-emerald-500",
  gameplay: "bg-violet-500", unknown: "bg-zinc-400",
} as const;
const labels = {
  waiting_or_music: "Waiting / Music", talking: "Talking", gameplay: "Gameplay", unknown: "Unknown",
} as const;
const noteFields: Array<[keyof ValidationNotes, string]> = [
  ["talking_start", "Real talking start"], ["talking_end", "Real talking end"],
  ["gameplay_start", "Real gameplay start"], ["gameplay_end", "Real gameplay end"],
  ["talking_block_2_start", "Talking block 2 start"], ["talking_block_2_end", "Talking block 2 end"],
  ["talking_block_3_start", "Talking block 3 start"], ["talking_block_3_end", "Talking block 3 end"],
];

function time(seconds: number): string {
  const value = Math.max(0, Math.round(seconds));
  const h = Math.floor(value / 3600);
  const m = Math.floor((value % 3600) / 60);
  const s = value % 60;
  return `${h.toString().padStart(2, "0")}:${m.toString().padStart(2, "0")}:${s.toString().padStart(2, "0")}`;
}

function seconds(value: string): number | null {
  if (!value.trim()) return null;
  const parts = value.trim().split(":").map(Number);
  if (parts.some((part) => !Number.isFinite(part) || part < 0) || parts.length < 2 || parts.length > 3) {
    throw new Error(`Invalid timestamp: ${value}`);
  }
  const [h, m, s] = parts.length === 3 ? parts : [0, ...parts];
  if (m >= 60 || s >= 60) throw new Error(`Invalid timestamp: ${value}`);
  return h * 3600 + m * 60 + s;
}

export function VodInspector() {
  const [url, setUrl] = useState("https://www.twitch.tv/videos/123456789");
  const [force, setForce] = useState(false);
  const [result, setResult] = useState<VodInspectorResult | null>(null);
  const [noteValues, setNoteValues] = useState<Record<keyof ValidationNotes, string>>(
    Object.fromEntries(noteFields.map(([key]) => [key, ""])) as Record<keyof ValidationNotes, string>,
  );
  const [error, setError] = useState<string | null>(null);
  const active = result?.status === "queued" || result?.status === "processing";

  function applyResult(value: VodInspectorResult) {
    setResult(value);
    if (value.status === "completed") {
      setNoteValues(Object.fromEntries(noteFields.map(([key]) => [
        key, value.validation_notes[key] == null ? "" : time(value.validation_notes[key] as number),
      ])) as Record<keyof ValidationNotes, string>);
    }
  }

  useEffect(() => {
    if (!active || !result) return;
    const timer = window.setInterval(async () => {
      try { applyResult(await getVodInspector(result.job_id)); }
      catch (caught) { setError(caught instanceof Error ? caught.message : "Inspector polling failed"); }
    }, 900);
    return () => window.clearInterval(timer);
  }, [active, result]);

  async function start(event: FormEvent) {
    event.preventDefault(); setError(null);
    try {
      const created = await createVodInspector({ url, streamer: "illojuan", force_reanalyze: force });
      applyResult(await getVodInspector(created.job_id));
    } catch (caught) { setError(caught instanceof Error ? caught.message : "Inspector could not start"); }
  }

  async function save(event: FormEvent) {
    event.preventDefault();
    if (!result) return;
    try {
      const notes = Object.fromEntries(
        noteFields.map(([key]) => [key, seconds(noteValues[key])]),
      ) as ValidationNotes;
      applyResult(await saveVodInspectorNotes(result.job_id, notes));
      setError(null);
    } catch (caught) { setError(caught instanceof Error ? caught.message : "Notes could not be saved"); }
  }

  return <div className="space-y-6">
    <form onSubmit={start} className="rounded-2xl bg-zinc-900 p-6 text-white shadow-soft">
      <p className="text-xs font-semibold uppercase tracking-[0.18em] text-violet-300">Engineering tool</p>
      <h2 className="mt-1 text-2xl font-semibold">VOD Inspector</h2>
      <p className="mt-2 text-sm text-zinc-300">Inspect the current detector and look for failures. No deep transcription or candidate generation runs here.</p>
      <div className="mt-5 grid gap-4 md:grid-cols-[1fr_14rem]">
        <label className="text-sm">VOD URL<input required type="url" value={url} onChange={(event) => setUrl(event.target.value)} className="mt-1.5 w-full rounded-xl border border-zinc-600 bg-zinc-800 px-3.5 py-2.5" /></label>
        <label className="text-sm">Streamer<select disabled className="mt-1.5 w-full rounded-xl border border-zinc-600 bg-zinc-800 px-3.5 py-2.5"><option>IlloJuan</option></select></label>
      </div>
      <label className="mt-4 flex gap-2 text-sm"><input type="checkbox" checked={force} onChange={(event) => setForce(event.target.checked)} />Create a new inspection job</label>
      <button disabled={Boolean(active)} className="mt-4 rounded-xl bg-violet-500 px-5 py-2.5 font-semibold disabled:opacity-50">{active ? "Inspecting…" : "Inspect VOD"}</button>
    </form>
    {error && <p className="rounded-xl bg-red-50 p-4 text-sm text-red-700">{error}</p>}
    {result && <section className="rounded-2xl border border-zinc-200 bg-white p-5">
      <div className="flex justify-between"><strong>{result.stage.replaceAll("_", " ")}</strong><span>{result.progress}%</span></div>
      <div className="mt-2 h-2 overflow-hidden rounded bg-zinc-100"><div className="h-full bg-violet-500" style={{ width: `${result.progress}%` }} /></div>
      {result.cached && <p className="mt-2 text-sm text-emerald-700">Cached visual layout artifacts reused</p>}
      <p className="mt-2 text-xs text-zinc-500">Strategy: {result.phase_detection_strategy} · Coarse timeline required: {result.requires_coarse_timeline ? "yes" : "no"}</p>
      {result.error_message && <p className="mt-2 text-sm text-red-700">{result.error_message}</p>}
    </section>}
    {result?.phase_timeline && <>
      <section className="rounded-2xl border border-zinc-200 bg-white p-5 shadow-sm">
        <div className="flex flex-wrap items-end justify-between gap-3"><div><p className="text-xs font-semibold uppercase tracking-widest text-zinc-500">Detected timeline</p><h2 className="text-xl font-semibold">{result.metadata?.title}</h2></div>{result.export_url && <a className="rounded-xl bg-zinc-900 px-4 py-2 text-sm font-semibold text-white" href={`${API_URL}${result.export_url}`}>Export Validation Report</a>}</div>
        <div className="mt-5 flex h-12 overflow-hidden rounded-xl border border-white" aria-label="Inspector phase timeline">
          {result.segments.map((segment, index) => <a target="_blank" rel="noreferrer" href={segment.open_url} key={`${segment.start}-${index}`} className={`${colors[segment.phase]} block hover:brightness-110`} style={{ flexGrow: segment.end - segment.start, minWidth: 4 }} title={`${labels[segment.phase]} ${time(segment.start)}–${time(segment.end)} confidence ${Math.round(segment.confidence * 100)}%`} />)}
        </div>
        <div className="mt-5 space-y-3">{result.segments.map((segment, index) => <article key={`${segment.phase}-${index}`} className="rounded-xl border border-zinc-200 p-4">
          <div className="flex flex-wrap items-center justify-between gap-3"><strong>{labels[segment.phase]}</strong><span>{time(segment.start)}–{time(segment.end)} · {time(segment.end - segment.start)} · {Math.round(segment.confidence * 100)}%</span></div>
          <p className="mt-2 text-xs font-medium text-zinc-700">Layout: {segment.layout_id ?? "legacy"} · match {segment.match_score == null ? "n/a" : segment.match_score.toFixed(3)} · second {segment.second_best_score == null ? "n/a" : segment.second_best_score.toFixed(3)} · margin {segment.score_margin == null ? "n/a" : segment.score_margin.toFixed(3)}</p>
          <p className="mt-2 text-xs text-zinc-600">Reasons: {segment.reasons.join(", ") || "none"}</p>
          {segment.warnings.length > 0 && <p className="mt-1 text-xs text-amber-700">Warnings: {segment.warnings.join(", ")}</p>}
          <a href={segment.open_url} target="_blank" rel="noreferrer" className="mt-3 inline-block rounded-lg bg-violet-50 px-3 py-2 text-sm font-semibold text-violet-800">Open on {result.metadata?.platform === "youtube" ? "YouTube" : "Twitch"}</a>
        </article>)}</div>
      </section>
      <form onSubmit={save} className="rounded-2xl border border-zinc-200 bg-white p-5 shadow-sm">
        <h2 className="text-xl font-semibold">Validation Notes</h2><p className="mt-1 text-sm text-zinc-600">Optional ground-truth boundaries. Stored only as a local JSON artifact for this inspection.</p>
        <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">{noteFields.map(([key, label]) => <label key={key} className="text-xs font-semibold text-zinc-600">{label}<input placeholder="HH:MM:SS" value={noteValues[key]} onChange={(event) => setNoteValues((current) => ({ ...current, [key]: event.target.value }))} className="mt-1 w-full rounded-lg border border-zinc-300 px-3 py-2 text-sm" /></label>)}</div>
        <button className="mt-4 rounded-xl bg-violet-600 px-4 py-2 text-sm font-semibold text-white">Compare with detector</button>
      </form>
      {result.metrics && <section className="rounded-2xl border border-zinc-200 bg-white p-5 shadow-sm"><h2 className="text-xl font-semibold">Validation metrics</h2>
        <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">{[
          ["Mean absolute error", result.metrics.mean_absolute_error_seconds == null ? "n/a" : `${result.metrics.mean_absolute_error_seconds.toFixed(1)} s`],
          ["Maximum error", result.metrics.maximum_absolute_error_seconds == null ? "n/a" : `${result.metrics.maximum_absolute_error_seconds.toFixed(1)} s`],
          ["Detected phases", result.metrics.detected_phase_count], ["Omitted phases", result.metrics.omitted_phase_count],
          ["False detections", result.metrics.false_detection_count], ["Mean confidence", `${Math.round(result.metrics.mean_confidence * 100)}%`],
        ].map(([label, value]) => <div key={label} className="rounded-xl bg-zinc-50 p-3"><p className="text-xs text-zinc-500">{label}</p><strong className="text-lg">{value}</strong></div>)}</div>
        {result.comparisons.length > 0 && <div className="mt-5 space-y-2">{result.comparisons.map((item) => <div key={item.transition} className="grid gap-2 rounded-lg border border-zinc-100 p-3 text-sm sm:grid-cols-4"><strong>{item.transition.replaceAll("_", " ")}</strong><span>Detector: {item.detector_seconds == null ? "missing" : time(item.detector_seconds)}</span><span>Real: {time(item.actual_seconds)}</span><span>Error: {item.error_seconds == null ? "n/a" : `${item.error_seconds >= 0 ? "+" : ""}${item.error_seconds.toFixed(1)} s`}</span></div>)}</div>}
      </section>}
    </>}
  </div>;
}
