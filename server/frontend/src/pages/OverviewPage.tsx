import type { FarmState } from "../useFarmSocket";
import { GATE_ID } from "../useFarmSocket";
import type { Alert } from "../alerts";
import type { CoopStatus, SolarStatus } from "../types";
import { EventList, Meter, SimBadge, fmt } from "../components/ui";
import { batteryPercent, relativeTime } from "../format";
import type { Tab } from "../App";

interface Props {
  farm: FarmState;
  now: number;
  alerts: Alert[];
  go: (tab: Tab) => void;
}

/** One-glance summary for a phone: every device, every alert, quick gate control. */
export function OverviewPage({ farm, now, alerts, go }: Props) {
  const gate = farm.gate;
  const coops = Object.values(farm.devices).filter((d): d is CoopStatus => d.kind === "coop");
  const solar = Object.values(farm.devices).filter((d): d is SolarStatus => d.kind === "solar");
  const connected = farm.socketState === "open";
  const names: Record<string, string> = {
    [GATE_ID]: "Gate",
    ...Object.fromEntries(Object.values(farm.devices).map((d) => [d.id, d.name])),
  };

  return (
    <div className="grid">
      {alerts.length > 0 && (
        <section className="card span-all alerts" aria-live="polite">
          <h2>Needs attention</h2>
          <ul>
            {alerts.map((a) => (
              <li key={a.id} className={`alert ${a.level}`}>
                <span className="alert-icon" aria-hidden>{a.level === "critical" ? "!" : "▲"}</span>
                <span>{a.text}</span>
                <button className="link" onClick={() => go(a.tab)}>View</button>
              </li>
            ))}
          </ul>
        </section>
      )}

      <div className="tiles span-all">
        <button className="tile" onClick={() => go("gate")}>
          <span className="tile-label">Gate</span>
          <span className={`tile-value state-${(gate?.state ?? "UNKNOWN").toLowerCase()}`}>{gate?.state ?? "UNKNOWN"}</span>
          <span className="tile-sub">
            {gate?.online ? `${fmt(gate.battery_v, 2)} V · ${gate.rssi} dBm` : "Offline"}
          </span>
          {gate?.online && <Meter pct={batteryPercent(gate.battery_mv)} />}
        </button>

        {coops.map((c) => (
          <button key={c.id} className="tile" onClick={() => go("coops")}>
            <span className="tile-label">
              {c.name} <SimBadge show={c.simulated} />
            </span>
            <span className={`tile-value state-${c.door.toLowerCase()}`}>{c.door}</span>
            <span className="tile-sub">
              {fmt(c.temperature_c, 1)} °C · {c.mode === "auto" ? "auto" : "manual"}
            </span>
          </button>
        ))}

        {solar.map((s) => (
          <button key={s.id} className="tile" onClick={() => go("solar")}>
            <span className="tile-label">
              {s.name} <SimBadge show={s.simulated} />
            </span>
            <span className="tile-value">{fmt(s.battery_soc, 0)}%</span>
            <span className="tile-sub">
              {fmt(s.panel_w, 0)} W in · {fmt(s.load_w, 0)} W out
            </span>
            <Meter pct={s.battery_soc ?? 0} />
          </button>
        ))}
      </div>

      <section className="card">
        <h2>Quick gate control</h2>
        <div className="control-buttons">
          {(["open", "stop", "close"] as const).map((c) => (
            <button key={c} className={`btn btn-${c}`} disabled={!connected} onClick={() => farm.sendCommand(GATE_ID, c)}>
              <span className="btn-icon" aria-hidden>{c === "open" ? "▲" : c === "stop" ? "■" : "▼"}</span>
              {c[0].toUpperCase() + c.slice(1)}
            </button>
          ))}
        </div>
        <p className="muted small">
          Gate last reported {gate ? relativeTime(Date.parse(gate.last_update), now) : "never"}.
        </p>
      </section>

      <section className="card">
        <h2>Recent activity</h2>
        <EventList events={farm.events.slice(0, 10)} now={now} names={names} />
      </section>
    </div>
  );
}
