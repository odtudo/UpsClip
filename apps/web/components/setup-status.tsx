import { SetupStatus as SetupStatusValue } from "@/lib/api";

type Props = { status: SetupStatusValue | null };

export function SetupStatus({ status }: Props) {
  const checks = status
    ? [
        ["FFmpeg", status.ffmpeg_available],
        ["ffprobe", status.ffprobe_available],
        ["yt-dlp", status.ytdlp_available],
        ["Data storage", status.data_writable],
        ["Database", status.database_accessible],
        [`Smart vertical (${status.face_detector_name})`, status.smart_vertical_ready],
      ] as const
    : [];
  return (
    <section className="mb-7 rounded-2xl border border-zinc-200 bg-white p-5 shadow-sm">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-zinc-500">Configuration</p>
          <h2 className="mt-1 text-xl font-semibold">Real-service readiness</h2>
        </div>
        <span className={`rounded-full px-3 py-1 text-xs font-semibold ${status?.youtube_ready ? "bg-emerald-100 text-emerald-700" : "bg-amber-100 text-amber-800"}`}>
          YouTube {status?.youtube_ready ? "ready" : "authorization needed"}
        </span>
      </div>
      {!status ? <p className="mt-4 text-sm text-zinc-500">Configuration status unavailable.</p> : (
        <>
          <div className="mt-4 flex flex-wrap gap-2">
            {checks.map(([label, ok]) => <span key={label} className={`rounded-lg px-2.5 py-1 text-xs font-medium ${ok ? "bg-emerald-50 text-emerald-700" : "bg-red-50 text-red-700"}`}>{label}: {ok ? "ready" : "missing"}</span>)}
          </div>
          <p className="mt-4 text-sm text-zinc-600">
            YouTube client file: {status.youtube_client_secret_present ? "present" : "missing"} · OAuth token: {status.youtube_token_present ? (status.youtube_token_usable ? "usable" : "invalid") : "missing"}
          </p>
          <p className="mt-2 text-sm text-zinc-600">Public Twitch VODs need no API key. Cookies are {status.twitch_cookies_present ? "configured" : "optional and not configured"}.</p>
          {status.messages.length > 0 && <ul className="mt-3 list-disc space-y-1 pl-5 text-sm text-amber-800">{status.messages.map((message) => <li key={message}>{message}</li>)}</ul>}
        </>
      )}
    </section>
  );
}
