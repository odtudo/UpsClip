import type { ClipProjectState } from "@/types/workflow";

const prefix = "clipping-studio:project:";

export function loadProject(id: string): ClipProjectState | null {
  if (typeof window === "undefined") return null;
  try {
    const value = window.localStorage.getItem(`${prefix}${id}`);
    return value ? (JSON.parse(value) as ClipProjectState) : null;
  } catch {
    return null;
  }
}

export function saveProject(id: string, state: ClipProjectState): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(`${prefix}${id}`, JSON.stringify(state));
}
