export function parseTimestamp(value: string): number | null {
  const clean = value.trim();
  if (/^\d+(?:\.\d+)?$/.test(clean)) return Number(clean);
  const parts = clean.split(":");
  if (
    parts.length < 2 ||
    parts.length > 3 ||
    parts.some((part) => !/^\d+$/.test(part))
  ) {
    return null;
  }
  const numbers = parts.map(Number);
  const [hours, minutes, seconds] =
    parts.length === 3 ? numbers : [0, ...numbers];
  if (minutes > 59 || seconds > 59) return null;
  return hours * 3600 + minutes * 60 + seconds;
}

export function formatTimestamp(seconds: number): string {
  const value = Math.max(0, Math.round(seconds));
  const hours = Math.floor(value / 3600);
  const minutes = Math.floor((value % 3600) / 60);
  const remainder = value % 60;
  return hours
    ? `${hours.toString().padStart(2, "0")}:${minutes.toString().padStart(2, "0")}:${remainder.toString().padStart(2, "0")}`
    : `${minutes.toString().padStart(2, "0")}:${remainder.toString().padStart(2, "0")}`;
}

export function validateSource(
  url: string,
  start?: string,
  end?: string,
): Record<string, string> {
  const errors: Record<string, string> = {};
  try {
    const parsed = new URL(url);
    if (
      !["twitch.tv", "www.twitch.tv", "m.twitch.tv"].includes(
        parsed.hostname,
      ) ||
      !parsed.pathname.includes("/videos/")
    ) {
      errors.url = "Enter a Twitch VOD URL containing /videos/.";
    }
  } catch {
    errors.url = "Enter a valid Twitch VOD URL.";
  }
  if (start !== undefined && end !== undefined) {
    const startValue = parseTimestamp(start);
    const endValue = parseTimestamp(end);
    if (startValue === null) errors.start = "Use MM:SS, HH:MM:SS, or seconds.";
    if (endValue === null) errors.end = "Use MM:SS, HH:MM:SS, or seconds.";
    if (startValue !== null && endValue !== null && endValue <= startValue) {
      errors.end = "End must be later than start.";
    }
  }
  return errors;
}
