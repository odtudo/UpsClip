"use client";

import type { StreamerProfile } from "@/lib/api";
import {
  cleanExportDefaults,
  horizontalDefaults,
  verticalDefaults,
  type EditSettings,
} from "@/types/workflow";

const presets = [
  {
    id: "vertical",
    label: "Vertical Short",
    detail: "9:16 · Smart layout · Subtitles",
    value: verticalDefaults,
  },
  {
    id: "horizontal",
    label: "Horizontal Long-form",
    detail: "Source layout · Clean audio",
    value: horizontalDefaults,
  },
  {
    id: "clean",
    label: "Clean Export",
    detail: "Minimum processing",
    value: cleanExportDefaults,
  },
] as const;

function Switch({
  checked,
  onChange,
  title,
  description,
  disabled = false,
}: {
  checked: boolean;
  onChange: (value: boolean) => void;
  title: string;
  description: string;
  disabled?: boolean;
}) {
  return (
    <label
      className={`flex items-start justify-between gap-5 rounded-md border border-line bg-elevated p-4 ${disabled ? "opacity-50" : "cursor-pointer"}`}
    >
      <span>
        <strong className="block text-sm">{title}</strong>
        <span className="mt-1 block text-xs leading-5 text-secondary">
          {description}
        </span>
      </span>
      <input
        type="checkbox"
        className="mt-1 h-4 w-4"
        checked={checked}
        disabled={disabled}
        onChange={(event) => onChange(event.target.checked)}
      />
    </label>
  );
}

export function ClipEditor({
  value,
  onChange,
  profiles,
  workflow,
}: {
  value: EditSettings;
  onChange: (value: EditSettings) => void;
  profiles: StreamerProfile[];
  workflow: "vertical" | "horizontal";
}) {
  const set = <K extends keyof EditSettings>(key: K, next: EditSettings[K]) =>
    onChange({ ...value, [key]: next });
  return (
    <div className="grid gap-6 xl:grid-cols-[18rem_1fr]">
      <aside>
        <h2 className="text-sm font-semibold">Presets</h2>
        <div className="mt-3 space-y-2">
          {presets
            .filter(
              (preset) => workflow === "vertical" || preset.id !== "vertical",
            )
            .map((preset) => (
              <button
                key={preset.id}
                type="button"
                onClick={() => onChange({ ...preset.value })}
                className={`w-full rounded-md border p-3 text-left ${value.outputFormat === preset.value.outputFormat && value.generateSubtitles === preset.value.generateSubtitles && value.removeSilences === preset.value.removeSilences ? "border-accent bg-accent/10" : "border-line bg-card hover:bg-active"}`}
              >
                <strong className="block text-sm">{preset.label}</strong>
                <span className="mt-1 block text-xs text-secondary">
                  {preset.detail}
                </span>
              </button>
            ))}
        </div>
      </aside>
      <div className="space-y-6">
        <section>
          <h2 className="font-semibold">Basic</h2>
          <p className="mt-1 text-sm text-secondary">
            Choose only processing that improves this clip.
          </p>
          <div className="mt-4 grid gap-3 md:grid-cols-2">
            <Switch
              checked={value.removeSilences}
              onChange={(next) => set("removeSilences", next)}
              title="Shorten long silences"
              description="Reduce extended pauses while preserving natural speech."
            />
            <Switch
              checked={value.normalizeAudio}
              onChange={(next) => set("normalizeAudio", next)}
              title="Normalize audio"
              description="Apply stable loudness normalization to the final timeline."
            />
            <Switch
              checked={value.generateSubtitles}
              onChange={(next) => set("generateSubtitles", next)}
              title="Burn automatic subtitles"
              description="Generate and embed subtitles directly into the video."
            />
            <Switch
              checked={value.smartVerticalLayout}
              onChange={(next) => set("smartVerticalLayout", next)}
              disabled={workflow === "horizontal"}
              title="Smart Vertical Layout"
              description={
                workflow === "horizontal"
                  ? "Available only for vertical output."
                  : "Keep the streamer and main content visible in 9:16."
              }
            />
          </div>
        </section>
        {workflow === "vertical" && value.smartVerticalLayout && (
          <section>
            <label className="block text-sm font-medium">
              Streamer profile
              <select
                className="field mt-2 max-w-sm"
                value={value.streamerProfile}
                onChange={(event) => set("streamerProfile", event.target.value)}
              >
                <option value="auto">Auto detect</option>
                {profiles.map((profile) => (
                  <option key={profile.id} value={profile.id}>
                    {profile.display_name}
                  </option>
                ))}
              </select>
            </label>
          </section>
        )}
        <section className="surface p-4">
          <h2 className="text-sm font-semibold">Output</h2>
          <dl className="mt-3 grid grid-cols-2 gap-3 text-sm">
            <div>
              <dt className="text-secondary">Orientation</dt>
              <dd className="mt-1 font-medium">
                {value.outputFormat === "vertical"
                  ? "Vertical · 9:16"
                  : "Horizontal · source"}
              </dd>
            </div>
            <div>
              <dt className="text-secondary">Resolution</dt>
              <dd className="mt-1 font-medium">
                {value.outputFormat === "vertical"
                  ? "1080 × 1920"
                  : "Source resolution"}
              </dd>
            </div>
          </dl>
        </section>
      </div>
    </div>
  );
}
