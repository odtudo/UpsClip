"use client";

import { FormEvent, useState } from "react";
import { CreateJobInput, StreamerProfile } from "@/lib/api";

const initialForm: CreateJobInput = {
  source_url: "https://www.twitch.tv/videos/123456789",
  start: "00:00",
  end: "00:12",
  remove_silences: true,
  normalize_audio: true,
  generate_subtitles: false,
  output_format: "horizontal",
  smart_vertical_layout: true,
  streamer_profile: "auto",
  demo: true,
};

type Props = {
  submitting: boolean;
  onSubmit: (input: CreateJobInput) => Promise<void>;
  profiles: StreamerProfile[];
};

export function JobForm({ submitting, onSubmit, profiles }: Props) {
  const [form, setForm] = useState(initialForm);
  const [validation, setValidation] = useState<string | null>(null);

  function set<K extends keyof CreateJobInput>(key: K, value: CreateJobInput[K]) {
    setForm((current) => ({ ...current, [key]: value }));
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    setValidation(null);
    if (!form.source_url.includes("twitch.tv/videos/")) {
      setValidation("Enter a Twitch VOD URL containing twitch.tv/videos/.");
      return;
    }
    if (!/^\d{1,3}:\d{2}(?::\d{2})?$/.test(form.start) || !/^\d{1,3}:\d{2}(?::\d{2})?$/.test(form.end)) {
      setValidation("Timestamps must use MM:SS or HH:MM:SS.");
      return;
    }
    await onSubmit(form);
  }

  const inputClass =
    "mt-1.5 w-full rounded-xl border border-zinc-300 bg-white px-3.5 py-2.5 text-sm shadow-sm transition focus:border-twitch";

  return (
    <form onSubmit={submit} className="rounded-2xl bg-panel p-5 shadow-soft sm:p-7">
      <div className="mb-6">
        <p className="text-xs font-semibold uppercase tracking-[0.18em] text-twitch">New clip</p>
        <h2 className="mt-1 text-xl font-semibold">Choose a VOD interval</h2>
      </div>

      <label className="block text-sm font-medium">
        Twitch VOD URL
        <input
          className={inputClass}
          type="url"
          required
          value={form.source_url}
          onChange={(event) => set("source_url", event.target.value)}
          placeholder="https://www.twitch.tv/videos/123456789"
        />
      </label>

      <div className="mt-4 grid grid-cols-2 gap-3">
        <label className="text-sm font-medium">
          Start
          <input className={inputClass} required value={form.start} onChange={(event) => set("start", event.target.value)} />
        </label>
        <label className="text-sm font-medium">
          End
          <input className={inputClass} required value={form.end} onChange={(event) => set("end", event.target.value)} />
        </label>
      </div>
      <p className="mt-2 text-xs text-zinc-500">Use MM:SS or HH:MM:SS. The default maximum is 30 minutes.</p>
      <p className="mt-2 text-xs text-zinc-500">Public Twitch VODs require no API key. If Twitch reports a login restriction, configure optional cookies under data/credentials.</p>

      <label className="mt-4 block text-sm font-medium">
        Output
        <select
          className={inputClass}
          value={form.output_format}
          onChange={(event) => {
            const output = event.target.value as CreateJobInput["output_format"];
            setForm((current) => ({
              ...current,
              output_format: output,
              generate_subtitles: output === "vertical" ? true : false,
              smart_vertical_layout: output === "vertical",
              streamer_profile: "auto",
            }));
          }}
        >
          <option value="horizontal">Horizontal 16:9 / source</option>
          <option value="vertical">Vertical 9:16 with automatic captions</option>
        </select>
      </label>

      <fieldset className="mt-5 space-y-3 rounded-xl border border-zinc-200 bg-zinc-50 p-4">
        <legend className="px-1 text-sm font-semibold">Editing</legend>
        {[
          ["remove_silences", "Shorten long silences"],
          ["normalize_audio", "Normalize audio loudness"],
        ].map(([key, label]) => (
          <label key={key} className="flex items-center gap-3 text-sm">
            <input
              type="checkbox"
              checked={Boolean(form[key as keyof CreateJobInput])}
              onChange={(event) => set(key as keyof CreateJobInput, event.target.checked as never)}
              className="h-4 w-4"
            />
            {label}
          </label>
        ))}
        {form.output_format === "horizontal" ? (
          <label className="flex items-center gap-3 text-sm">
            <input
              type="checkbox"
              checked={form.generate_subtitles}
              onChange={(event) => set("generate_subtitles", event.target.checked)}
              className="h-4 w-4"
            />
            Burn automatic subtitles
          </label>
        ) : (
          <div className="space-y-3">
            <p className="rounded-lg bg-violet-50 p-3 text-xs leading-5 text-violet-800">
              Vertical clips automatically include large, mobile-friendly burned-in subtitles.
            </p>
            <label className="flex items-start gap-3 text-sm">
              <input type="checkbox" checked={form.smart_vertical_layout} onChange={(event) => set("smart_vertical_layout", event.target.checked)} className="mt-0.5 h-4 w-4" />
              <span><strong className="block">Smart facecam layout</strong><span className="text-xs text-zinc-600">Automatically keeps the streamer and main content visible.</span></span>
            </label>
            {form.smart_vertical_layout && <label className="block text-sm font-medium">
              Streamer profile
              <select className={inputClass} value={form.streamer_profile} onChange={(event) => set("streamer_profile", event.target.value)}>
                <option value="auto">Auto</option>
                {profiles.map((profile) => <option key={profile.id} value={profile.id}>{profile.display_name}</option>)}
              </select>
            </label>}
          </div>
        )}
      </fieldset>

      <label className="mt-4 flex items-start gap-3 rounded-xl border border-violet-200 bg-violet-50 p-3 text-sm">
        <input
          type="checkbox"
          checked={form.demo}
          onChange={(event) => set("demo", event.target.checked)}
          className="mt-0.5 h-4 w-4"
        />
        <span>
          <strong className="block text-violet-950">Demo processing</strong>
          <span className="text-violet-700">Generate a real test MP4 locally instead of downloading Twitch.</span>
        </span>
      </label>

      {validation && <p className="mt-4 rounded-lg bg-red-50 p-3 text-sm text-red-700">{validation}</p>}

      <button
        type="submit"
        disabled={submitting}
        className="mt-5 w-full rounded-xl bg-twitch px-4 py-3 text-sm font-semibold text-white shadow-sm transition hover:bg-violet-700 disabled:cursor-not-allowed disabled:opacity-60"
      >
        {submitting ? "Creating job…" : "Process video"}
      </button>
    </form>
  );
}
