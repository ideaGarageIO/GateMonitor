import type { ReactNode } from "react";
import type { FarmEvent } from "../types";
import { relativeTime } from "../format";

export function Pill({ on, children, title }: { on: boolean; children: ReactNode; title?: string }) {
  return (
    <span className={`pill ${on ? "online" : "offline"}`} title={title}>
      <span className="dot" />
      {children}
    </span>
  );
}

export function SimBadge({ show }: { show: boolean }) {
  return show ? (
    <span className="sim-badge" title="Simulated device — no hardware yet">
      SIM
    </span>
  ) : null;
}

export function Stat({ label, value, unit, sub }: { label: string; value: ReactNode; unit?: string; sub?: ReactNode }) {
  return (
    <div className="stat">
      <span className="stat-label">{label}</span>
      <span className="stat-value">
        {value}
        {unit && <span className="stat-unit">{unit}</span>}
      </span>
      {sub && <span className="stat-sub">{sub}</span>}
    </div>
  );
}

export function Meter({ pct, tone }: { pct: number; tone?: "good" | "warning" | "critical" }) {
  const t = tone ?? (pct < 20 ? "critical" : pct < 50 ? "warning" : "good");
  return (
    <div className="meter" role="meter" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(pct)}>
      <div className={`meter-fill ${t}`} style={{ width: `${Math.max(0, Math.min(100, pct))}%` }} />
    </div>
  );
}

export const WINDOWS = [
  { label: "5m", ms: 5 * 60_000 },
  { label: "15m", ms: 15 * 60_000 },
  { label: "1h", ms: 60 * 60_000 },
];

export function WindowPicker({ value, onChange }: { value: number; onChange: (ms: number) => void }) {
  return (
    <div className="segmented" role="group" aria-label="Time window">
      {WINDOWS.map((w) => (
        <button key={w.label} aria-pressed={value === w.ms} onClick={() => onChange(w.ms)}>
          {w.label}
        </button>
      ))}
    </div>
  );
}

export function fmt(v: number | null | undefined, digits = 0): string {
  return v === null || v === undefined || !Number.isFinite(v) ? "--" : v.toFixed(digits);
}

const EVENT_TONE: Record<string, string> = {
  open: "open",
  closed: "closed",
  moving: "moving",
  jammed: "error",
  error: "error",
  offline: "error",
  online: "open",
  unknown: "unknown",
};

export function EventList({
  events,
  now,
  names,
  empty = "No activity recorded",
}: {
  events: FarmEvent[];
  now: number;
  names?: Record<string, string>;
  empty?: string;
}) {
  if (events.length === 0) return <p className="muted">{empty}</p>;
  return (
    <ul className="history-list">
      {events.map((e) => (
        <li key={`${e.device_id}-${e.ts}-${e.event}`} className="history-item">
          <span className="history-main">
            <span className={`state-badge ${EVENT_TONE[e.event] ?? "unknown"}`}>{e.event.toUpperCase()}</span>
            {names && <span className="history-device">{names[e.device_id] ?? e.device_id}</span>}
          </span>
          <span className="muted" title={new Date(e.ts).toLocaleString()}>
            {relativeTime(e.ts, now)}
          </span>
        </li>
      ))}
    </ul>
  );
}
