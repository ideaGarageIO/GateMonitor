/** 12V lead-acid: 11.0V = 0%, 12.6V = 100%. */
export function batteryPercent(mv: number): number {
  const pct = ((mv - 11000) / (12600 - 11000)) * 100;
  return Math.max(0, Math.min(100, pct));
}

export function relativeTime(t: number, now: number): string {
  const diff = Math.max(0, now - t);
  if (diff < 5_000) return "just now";
  if (diff < 60_000) return `${Math.floor(diff / 1000)}s ago`;
  if (diff < 3_600_000) return `${Math.floor(diff / 60_000)}m ago`;
  if (diff < 86_400_000) return `${Math.floor(diff / 3_600_000)}h ago`;
  return new Date(t).toLocaleString();
}

export function clockTime(t: number): string {
  return new Date(t).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}
