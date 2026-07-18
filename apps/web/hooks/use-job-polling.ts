"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError } from "@/lib/api";

type Pollable = { status: string };
const terminal = new Set(["ready", "completed", "failed", "cancelled"]);

export function useJobPolling<T extends Pollable>(
  id: string | null,
  fetcher: (id: string, signal?: AbortSignal) => Promise<T>,
  initial: T | null = null,
) {
  const [value, setValue] = useState<T | null>(initial);
  const [error, setError] = useState<ApiError | null>(null);
  const attempts = useRef(0);

  const refresh = useCallback(
    async (signal?: AbortSignal) => {
      if (!id) return null;
      try {
        const next = await fetcher(id, signal);
        setValue(next);
        setError(null);
        attempts.current = 0;
        return next;
      } catch (caught) {
        if (signal?.aborted) return null;
        attempts.current += 1;
        setError(
          caught instanceof ApiError
            ? caught
            : new ApiError("Could not refresh this job.", 0, String(caught)),
        );
        return null;
      }
    },
    [fetcher, id],
  );

  useEffect(() => {
    if (!id) return;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout> | undefined;
    const poll = async () => {
      const next = await refresh(controller.signal);
      if (!controller.signal.aborted && next && !terminal.has(next.status)) {
        timer = setTimeout(poll, Math.min(5000, 1200 + attempts.current * 600));
      }
    };
    void poll();
    return () => {
      controller.abort();
      if (timer) clearTimeout(timer);
    };
  }, [id, refresh]);

  return { value, error, refresh };
}
