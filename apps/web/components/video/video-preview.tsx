"use client";

import { useState } from "react";

export function VideoPreview({
  src,
  orientation,
  title,
}: {
  src: string | null;
  orientation: "vertical" | "horizontal";
  title: string;
}) {
  const [state, setState] = useState<"loading" | "ready" | "error">("loading");
  if (!src)
    return (
      <div className="surface grid aspect-video place-items-center p-8 text-sm text-secondary">
        Preview is not available yet.
      </div>
    );
  return (
    <div className={orientation === "vertical" ? "mx-auto max-w-sm" : "w-full"}>
      <div
        className={`relative overflow-hidden rounded-lg border border-line bg-black ${orientation === "vertical" ? "aspect-[9/16]" : "aspect-video"}`}
      >
        {state === "loading" && (
          <div className="absolute inset-0 grid place-items-center bg-black text-sm text-secondary">
            Loading video…
          </div>
        )}
        <video
          key={src}
          aria-label={title}
          className="h-full w-full object-contain"
          controls
          preload="metadata"
          src={src}
          onLoadedMetadata={() => setState("ready")}
          onError={() => setState("error")}
        />
        {state === "error" && (
          <div className="absolute inset-0 grid place-items-center bg-black/90 p-6 text-center text-sm text-red-300">
            The browser could not play this preview. The source file may still
            be finalizing or use an unsupported format.
          </div>
        )}
      </div>
    </div>
  );
}
