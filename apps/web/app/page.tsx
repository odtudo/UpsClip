"use client";

import { useCallback, useEffect, useState } from "react";
import { JobCard } from "@/components/job-card";
import { JobForm } from "@/components/job-form";
import { SetupStatus } from "@/components/setup-status";
import { VodAnalysis } from "@/components/vod-analysis";
import { VodInspector } from "@/components/vod-inspector";
import { CreateJobInput, Job, SetupStatus as SetupStatusValue, StreamerProfile, createJob, deleteJob, getSetupStatus, listJobs, listProfiles } from "@/lib/api";

const activeStatuses = new Set(["queued", "inspecting", "downloading", "trimming", "analyzing", "detecting_scenes", "analyzing_layouts", "composing", "transcribing", "rendering", "finalizing", "uploading"]);

export default function Home() {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [setup, setSetup] = useState<SetupStatusValue | null>(null);
  const [profiles, setProfiles] = useState<StreamerProfile[]>([]);
  const [mode, setMode] = useState<"manual" | "automatic" | "inspector">("manual");

  const refresh = useCallback(async () => {
    try {
      const [nextJobs, nextSetup, nextProfiles] = await Promise.all([listJobs(), getSetupStatus(), listProfiles()]);
      setJobs(nextJobs);
      setSetup(nextSetup);
      setProfiles(nextProfiles);
      setError(null);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "The API is unavailable");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const initialLoad = window.setTimeout(() => void refresh(), 0);
    return () => window.clearTimeout(initialLoad);
  }, [refresh]);

  useEffect(() => {
    if (!jobs.some((job) => activeStatuses.has(job.status))) return;
    const timer = window.setInterval(() => void refresh(), 2000);
    return () => window.clearInterval(timer);
  }, [jobs, refresh]);

  async function submit(input: CreateJobInput) {
    setSubmitting(true);
    setError(null);
    try {
      const job = await createJob(input);
      setJobs((current) => [job, ...current]);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "The job could not be created");
    } finally {
      setSubmitting(false);
    }
  }

  async function remove(id: string) {
    setError(null);
    try {
      await deleteJob(id);
      setJobs((current) => current.filter((job) => job.id !== id));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "The job could not be deleted");
    }
  }

  return (
    <main className="mx-auto min-h-screen max-w-7xl px-4 py-10 sm:px-6 lg:px-8">
      <header className="mb-9 max-w-3xl">
        <p className="text-sm font-semibold uppercase tracking-[0.2em] text-twitch">Local video workshop</p>
        <h1 className="mt-3 text-4xl font-bold tracking-tight sm:text-5xl">Turn a Twitch moment into a finished clip.</h1>
        <p className="mt-4 text-base leading-7 text-zinc-600">
          Download one authorized VOD interval, trim it exactly, apply restrained edits, preview locally, then choose whether to upload.
        </p>
      </header>

      {error && (
        <div className="mb-6 flex items-start justify-between gap-4 rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-700">
          <span>{error}</span>
          <button className="font-semibold" onClick={() => setError(null)}>Dismiss</button>
        </div>
      )}

      <SetupStatus status={setup} />

      <div className="mb-6 flex w-fit rounded-xl bg-zinc-200 p-1">
        <button onClick={() => setMode("manual")} className={`rounded-lg px-4 py-2 text-sm font-semibold ${mode === "manual" ? "bg-white shadow-sm" : "text-zinc-600"}`}>Manual</button>
        <button onClick={() => setMode("automatic")} className={`rounded-lg px-4 py-2 text-sm font-semibold ${mode === "automatic" ? "bg-white shadow-sm" : "text-zinc-600"}`}>Automatic VOD Analysis</button>
        <button onClick={() => setMode("inspector")} className={`rounded-lg px-4 py-2 text-sm font-semibold ${mode === "inspector" ? "bg-white shadow-sm" : "text-zinc-600"}`}>VOD Inspector</button>
      </div>

      {mode === "automatic" ? <VodAnalysis onGenerate={submit} /> : mode === "inspector" ? <VodInspector /> : <div className="grid items-start gap-7 lg:grid-cols-[23rem_1fr]">
        <JobForm submitting={submitting} onSubmit={submit} profiles={profiles} />

        <section>
          <div className="mb-4 flex items-end justify-between">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.18em] text-zinc-500">Persistent local history</p>
              <h2 className="mt-1 text-2xl font-semibold">Jobs</h2>
            </div>
            <button className="text-sm font-semibold text-twitch" onClick={() => void refresh()}>Refresh</button>
          </div>

          {loading ? (
            <div className="rounded-2xl border border-zinc-200 bg-white p-8 text-sm text-zinc-500">Loading jobs…</div>
          ) : jobs.length === 0 ? (
            <div className="rounded-2xl border border-dashed border-zinc-300 bg-white/70 p-10 text-center">
              <p className="font-semibold">No jobs yet</p>
              <p className="mt-1 text-sm text-zinc-500">The demo checkbox lets you test the complete local render flow immediately.</p>
            </div>
          ) : (
            <div className="space-y-4">
              {jobs.map((job) => (
                <JobCard key={job.id} job={job} youtubeReady={Boolean(setup?.youtube_ready)} onChanged={refresh} onDelete={remove} />
              ))}
            </div>
          )}
        </section>
      </div>}
    </main>
  );
}
