import type { GateStatus } from "../types";
import { batteryPercent, relativeTime } from "../format";

const STATE_ICON: Record<GateStatus["state"], string> = {
  OPEN: "▲",
  CLOSED: "■",
  MOVING: "↔",
  ERROR: "!",
  UNKNOWN: "?",
};

export function StatusCard({ status, now }: { status: GateStatus | null; now: number }) {
  const state = status?.state ?? "UNKNOWN";
  const online = !!status?.online;
  const pct = status ? batteryPercent(status.battery_mv) : 0;
  const updated = status ? Date.parse(status.last_update) : NaN;
  // Re-key on each update so the value flash animation replays.
  const flashKey = status?.last_update ?? "none";

  return (
    <section className="card status-card">
      <h2>Gate Status</h2>
      <div className="status-display">
        <div className={`gate-state ${state.toLowerCase()}`}>
          <span className="state-icon" aria-hidden>
            {STATE_ICON[state]}
          </span>
          <span className="state-text">{state}</span>
        </div>
        <div className={`pill ${online ? "online" : "offline"}`}>
          <span className="dot" />
          {online ? "Online" : "Offline"}
        </div>
      </div>

      <dl className="status-details" key={flashKey}>
        <div className="detail">
          <dt>Battery</dt>
          <dd className="flash">{status?.battery_mv ? `${status.battery_v.toFixed(2)} V` : "--"}</dd>
          <div className="battery-bar" aria-hidden>
            <div
              className={`battery-level ${pct < 20 ? "low" : pct < 50 ? "medium" : ""}`}
              style={{ width: `${pct}%` }}
            />
          </div>
        </div>
        <div className="detail">
          <dt>Signal (RSSI)</dt>
          <dd className="flash">{status?.rssi ? `${status.rssi} dBm` : "--"}</dd>
        </div>
        <div className="detail">
          <dt>SNR</dt>
          <dd className="flash">{status?.snr !== undefined && status.rssi ? `${status.snr} dB` : "--"}</dd>
        </div>
        <div className="detail">
          <dt>Last update</dt>
          <dd>{Number.isFinite(updated) ? relativeTime(updated, now) : "--"}</dd>
        </div>
      </dl>
    </section>
  );
}
