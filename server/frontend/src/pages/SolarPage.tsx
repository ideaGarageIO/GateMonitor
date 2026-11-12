import { useState } from "react";
import type { FarmState } from "../useFarmSocket";
import type { ChargeState, SolarStatus } from "../types";
import { LiveChart } from "../components/LiveChart";
import { Meter, SimBadge, Stat, WINDOWS, WindowPicker, fmt } from "../components/ui";
import { relativeTime } from "../format";

const CHARGE_LABEL: Record<ChargeState, string> = {
  off: "Not charging",
  bulk: "Bulk charging",
  absorption: "Absorption",
  float: "Float (full)",
  fault: "Fault",
};

function SolarCard({ s, farm, now, windowMs }: { s: SolarStatus; farm: FarmState; now: number; windowMs: number }) {
  const samples = farm.samples[s.id] ?? [];
  const soc = s.battery_soc ?? 0;
  const charging = (s.battery_a ?? 0) > 0.05;

  return (
    <section className="card span-all">
      <div className="card-head">
        <h2>
          {s.name} <SimBadge show={s.simulated} />
        </h2>
        <span className={`pill ${s.online ? "online" : "offline"}`}>
          <span className="dot" />
          {s.online ? "Online" : "Offline"}
        </span>
      </div>

      <div className="solar-hero">
        <div className="hero-number">
          <span className="hero-value">{fmt(s.battery_soc, 0)}</span>
          <span className="hero-unit">%</span>
        </div>
        <div className="hero-side">
          <span className={`charge-badge ${s.charge_state}`}>
            <span aria-hidden>{s.charge_state === "fault" ? "!" : charging ? "⚡" : "•"}</span>
            {CHARGE_LABEL[s.charge_state]}
          </span>
          <Meter pct={soc} />
          <span className="muted small">
            {charging ? "Charging" : "Discharging"} at {fmt(Math.abs(s.battery_a ?? 0), 1)} A · updated{" "}
            {relativeTime(Date.parse(s.last_update), now)}
          </span>
        </div>
      </div>

      <div className="stats">
        <Stat label="Panel power" value={fmt(s.panel_w, 0)} unit="W" sub={`${fmt(s.panel_v, 1)} V`} />
        <Stat label="Load" value={fmt(s.load_w, 0)} unit="W" />
        <Stat label="Battery" value={fmt(s.battery_v, 2)} unit="V" />
        <Stat label="Yield today" value={s.yield_today_wh !== null ? fmt(s.yield_today_wh / 1000, 2) : "--"} unit="kWh" />
      </div>

      <div className="charts">
        <LiveChart title="Panel power" unit="W" field="panel_w" minSpan={20} floor={0}
          readings={samples} windowMs={windowMs} now={now} />
        <LiveChart title="Battery charge" unit="%" field="battery_soc" digits={1} minSpan={2} floor={0} ceil={100}
          readings={samples} windowMs={windowMs} now={now} />
        <LiveChart title="Load" unit="W" field="load_w" minSpan={10} floor={0}
          readings={samples} windowMs={windowMs} now={now} />
      </div>
    </section>
  );
}

export function SolarPage({ farm, now }: { farm: FarmState; now: number }) {
  const [windowMs, setWindowMs] = useState(WINDOWS[2].ms);
  const arrays = Object.values(farm.devices).filter((d): d is SolarStatus => d.kind === "solar");

  if (arrays.length === 0) {
    return (
      <section className="card empty-state">
        <h2>Solar</h2>
        <p className="muted">
          No charge controllers reporting yet. Devices publish JSON to <code>solar/&lt;id&gt;/state</code>.
        </p>
      </section>
    );
  }

  return (
    <>
      <div className="page-head">
        <h2>Solar</h2>
        <WindowPicker value={windowMs} onChange={setWindowMs} />
      </div>
      <div className="grid">
        {arrays.map((s) => (
          <SolarCard key={s.id} s={s} farm={farm} now={now} windowMs={windowMs} />
        ))}
      </div>
    </>
  );
}
