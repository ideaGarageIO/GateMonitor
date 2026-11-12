import { useState } from "react";
import type { FarmState } from "../useFarmSocket";
import type { CoopCommand, CoopStatus, DoorState } from "../types";
import { LiveChart } from "../components/LiveChart";
import { EventList, SimBadge, Stat, WINDOWS, WindowPicker, fmt } from "../components/ui";
import { relativeTime } from "../format";

const DOOR_ICON: Record<DoorState, string> = {
  OPEN: "▲",
  CLOSED: "■",
  OPENING: "↑",
  CLOSING: "↓",
  JAMMED: "!",
  UNKNOWN: "?",
};

function timeOfDay(iso: string | null): string {
  if (!iso) return "--";
  return new Date(iso).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
}

function CoopCard({ coop, farm, now, windowMs }: { coop: CoopStatus; farm: FarmState; now: number; windowMs: number }) {
  const send = (c: CoopCommand) => farm.sendCommand(coop.id, c);
  const connected = farm.socketState === "open" && coop.online;
  const moving = coop.door === "OPENING" || coop.door === "CLOSING";
  const samples = farm.samples[coop.id] ?? [];
  const nextEvent =
    coop.next_open && coop.next_close
      ? Date.parse(coop.next_open) < Date.parse(coop.next_close)
        ? `Opens at ${timeOfDay(coop.next_open)}`
        : `Closes at ${timeOfDay(coop.next_close)}`
      : null;

  return (
    <section className="card coop-card">
      <div className="card-head">
        <h2>
          {coop.name} <SimBadge show={coop.simulated} />
        </h2>
        <span className={`pill ${coop.online ? "online" : "offline"}`}>
          <span className="dot" />
          {coop.online ? "Online" : "Offline"}
        </span>
      </div>

      <div className="status-display">
        <div className={`gate-state ${coop.door.toLowerCase()}`}>
          <span className={`state-icon ${moving ? "spin" : ""}`} aria-hidden>
            {DOOR_ICON[coop.door]}
          </span>
          <div>
            <span className="state-text">{coop.door}</span>
            <span className="state-sub">
              {coop.mode === "auto" ? nextEvent ?? "On schedule" : "Manual — schedule paused"}
            </span>
          </div>
        </div>
      </div>

      {coop.door === "JAMMED" && (
        <div className="banner critical" role="alert">
          <strong>Door jammed.</strong> Check for an obstruction, then press Stop and retry.
        </div>
      )}

      <div className="control-buttons">
        <button className="btn btn-open" disabled={!connected || coop.door === "OPEN"} onClick={() => send("OPEN")}>
          <span className="btn-icon" aria-hidden>▲</span>Open
        </button>
        <button className="btn btn-stop" disabled={!connected} onClick={() => send("STOP")}>
          <span className="btn-icon" aria-hidden>■</span>Stop
        </button>
        <button className="btn btn-close" disabled={!connected || coop.door === "CLOSED"} onClick={() => send("CLOSE")}>
          <span className="btn-icon" aria-hidden>▼</span>Close
        </button>
      </div>

      <label className="toggle">
        <input
          type="checkbox"
          checked={coop.mode === "auto"}
          disabled={!connected}
          onChange={(e) => send(e.target.checked ? "AUTO" : "MANUAL")}
        />
        <span className="toggle-track" aria-hidden />
        Sunrise / sunset schedule
      </label>

      <div className="stats">
        <Stat label="Temperature" value={fmt(coop.temperature_c, 1)} unit="°C" />
        <Stat label="Humidity" value={fmt(coop.humidity, 0)} unit="%" />
        <Stat label="Battery" value={fmt(coop.battery_v, 2)} unit="V" />
        <Stat
          label="Last opened"
          value={coop.last_opened ? relativeTime(Date.parse(coop.last_opened), now) : "--"}
          sub={timeOfDay(coop.last_opened)}
        />
        <Stat
          label="Last closed"
          value={coop.last_closed ? relativeTime(Date.parse(coop.last_closed), now) : "--"}
          sub={timeOfDay(coop.last_closed)}
        />
        <Stat label="Updated" value={relativeTime(Date.parse(coop.last_update), now)} />
      </div>

      <LiveChart title="Temperature" unit="°C" field="temperature_c" digits={1} minSpan={2}
        readings={samples} windowMs={windowMs} now={now} />
    </section>
  );
}

export function CoopsPage({ farm, now }: { farm: FarmState; now: number }) {
  const [windowMs, setWindowMs] = useState(WINDOWS[1].ms);
  const coops = Object.values(farm.devices).filter((d): d is CoopStatus => d.kind === "coop");
  const ids = new Set(coops.map((c) => c.id));
  const names = Object.fromEntries(coops.map((c) => [c.id, c.name]));
  const events = farm.events.filter((e) => ids.has(e.device_id)).slice(0, 25);

  if (coops.length === 0) {
    return (
      <section className="card empty-state">
        <h2>Chicken Coops</h2>
        <p className="muted">
          No coops reporting yet. Devices publish JSON to <code>coop/&lt;id&gt;/state</code>, or start the server
          with <code>SIMULATE_DEVICES=true</code>.
        </p>
      </section>
    );
  }

  return (
    <>
      <div className="page-head">
        <h2>Chicken Coops</h2>
        <WindowPicker value={windowMs} onChange={setWindowMs} />
      </div>
      <div className="grid two">
        {coops.map((c) => (
          <CoopCard key={c.id} coop={c} farm={farm} now={now} windowMs={windowMs} />
        ))}
        <section className="card span-all">
          <h2>Door Activity</h2>
          <EventList events={events} now={now} names={names} />
        </section>
      </div>
    </>
  );
}
