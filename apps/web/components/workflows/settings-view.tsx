"use client";

import { useEffect, useState } from "react";
import { getSetupStatus, type SetupStatus } from "@/lib/api";

export function SettingsView() {
  const [setup, setSetup] = useState<SetupStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    void getSetupStatus()
      .then(setSetup)
      .catch((caught) =>
        setError(
          caught instanceof Error ? caught.message : "Settings unavailable.",
        ),
      );
  }, []);
  const checks = setup
    ? ([
        ["FFmpeg", setup.ffmpeg_available],
        ["ffprobe", setup.ffprobe_available],
        ["yt-dlp", setup.ytdlp_available],
        ["Local storage", setup.data_writable],
        ["SQLite", setup.database_accessible],
        ["Smart Vertical", setup.smart_vertical_ready],
      ] as const)
    : [];
  return (
    <div>
      <p className="eyebrow">Workspace</p>
      <h1 className="mt-2 text-3xl font-semibold">Settings</h1>
      <p className="mt-3 text-secondary">
        Connections and local processing capabilities. Sensitive paths and
        credentials are never displayed.
      </p>
      {error && (
        <p className="mt-6 rounded-md bg-danger/10 p-4 text-red-200">{error}</p>
      )}
      <div className="mt-8 grid gap-5 lg:grid-cols-2">
        <section className="surface p-6">
          <h2 className="text-lg font-semibold">Connections</h2>
          <div className="mt-5 flex items-center justify-between rounded-md border border-line bg-elevated p-4">
            <div>
              <strong className="text-sm">YouTube</strong>
              <p className="mt-1 text-xs text-secondary">
                Existing local OAuth connection
              </p>
            </div>
            <span
              className={
                setup?.youtube_ready
                  ? "text-sm text-success"
                  : "text-sm text-warning"
              }
            >
              {setup?.youtube_ready ? "Connected" : "Disconnected"}
            </span>
          </div>
          {!setup?.youtube_ready && (
            <div className="mt-4 rounded-md bg-warning/10 p-4 text-sm leading-6 text-amber-200">
              Place the Google Desktop OAuth client in the configured
              credentials directory, then run{" "}
              <code className="rounded bg-black/30 px-1.5 py-0.5">
                ./scripts/youtube_auth.sh
              </code>
              . Restart the API afterward.
            </div>
          )}
        </section>
        <section className="surface p-6">
          <h2 className="text-lg font-semibold">System</h2>
          <div className="mt-5 grid gap-3 sm:grid-cols-2">
            {checks.map(([label, ready]) => (
              <div
                key={label}
                className="rounded-md border border-line bg-elevated p-3"
              >
                <p className="text-xs text-secondary">{label}</p>
                <p
                  className={`mt-1 text-sm font-medium ${ready ? "text-success" : "text-danger"}`}
                >
                  {ready ? "Ready" : "Unavailable"}
                </p>
              </div>
            ))}
          </div>
        </section>
        <section className="surface p-6 lg:col-span-2">
          <h2 className="text-lg font-semibold">Processing defaults</h2>
          <p className="mt-2 text-sm text-secondary">
            Workflow presets are stored locally per project: Vertical Short
            enables Smart Vertical, subtitles, silence shortening, and
            normalization. Horizontal Long-form preserves source layout and
            keeps subtitles optional.
          </p>
        </section>
      </div>
    </div>
  );
}
