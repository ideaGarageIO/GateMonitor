import type { CoopStatus, Device, GateStatus, SolarStatus, SocketState } from "./types";

export type AlertLevel = "critical" | "warning";
export interface Alert {
  id: string;
  level: AlertLevel;
  tab: "gate" | "coops" | "solar";
  text: string;
}

const GATE_LOW_BATTERY_MV = 11800;
const SOLAR_LOW_SOC = 30;
const COOP_LOW_BATTERY_V = 11.9;
/** Grace period after a scheduled close before an open door is flagged. */
const COOP_LATE_MS = 15 * 60_000;

/** Things a person should look at, derived purely from current state. */
export function computeAlerts(
  socket: SocketState,
  gate: GateStatus | null,
  devices: Record<string, Device>,
  now: number,
): Alert[] {
  const out: Alert[] = [];
  if (socket !== "open") {
    out.push({ id: "server", level: "critical", tab: "gate", text: "Not connected to the monitor server" });
    return out;
  }

  if (gate) {
    if (!gate.mqtt_connected) out.push({ id: "mqtt", level: "critical", tab: "gate", text: "Server can't reach the MQTT broker" });
    else if (!gate.gateway_online) out.push({ id: "gateway", level: "critical", tab: "gate", text: "House gateway is offline" });
    else if (!gate.online) out.push({ id: "gate-offline", level: "critical", tab: "gate", text: "Gate node is not reporting" });
    if (gate.state === "ERROR") out.push({ id: "gate-error", level: "critical", tab: "gate", text: "Gate reports an error (both limit switches?)" });
    if (gate.online && gate.battery_mv && gate.battery_mv < GATE_LOW_BATTERY_MV)
      out.push({ id: "gate-batt", level: "warning", tab: "gate", text: `Gate battery low (${gate.battery_v.toFixed(2)} V)` });
  }

  for (const d of Object.values(devices)) {
    if (!d.online) {
      out.push({ id: `${d.id}-offline`, level: "warning", tab: d.kind === "coop" ? "coops" : "solar", text: `${d.name} is offline` });
      continue;
    }
    if (d.kind === "coop") out.push(...coopAlerts(d, now));
    else out.push(...solarAlerts(d));
  }
  return out;
}

function coopAlerts(c: CoopStatus, now: number): Alert[] {
  const out: Alert[] = [];
  if (c.door === "JAMMED") out.push({ id: `${c.id}-jam`, level: "critical", tab: "coops", text: `${c.name} door is jammed` });
  // It's night when the next scheduled event is an open. Tonight's close was
  // ~24h before the next close; allow a grace period past it.
  if (c.door === "OPEN" && c.next_open && c.next_close) {
    const nextOpen = Date.parse(c.next_open);
    const nextClose = Date.parse(c.next_close);
    if (nextOpen < nextClose && now > nextClose - 86_400_000 + COOP_LATE_MS) {
      out.push({ id: `${c.id}-open-night`, level: "warning", tab: "coops", text: `${c.name} door is open after dark` });
    }
  }
  if (c.battery_v !== null && c.battery_v < COOP_LOW_BATTERY_V)
    out.push({ id: `${c.id}-batt`, level: "warning", tab: "coops", text: `${c.name} battery low (${c.battery_v.toFixed(2)} V)` });
  return out;
}

function solarAlerts(s: SolarStatus): Alert[] {
  const out: Alert[] = [];
  if (s.charge_state === "fault") out.push({ id: `${s.id}-fault`, level: "critical", tab: "solar", text: `${s.name} charge controller fault` });
  if (s.battery_soc !== null && s.battery_soc < SOLAR_LOW_SOC)
    out.push({ id: `${s.id}-soc`, level: "warning", tab: "solar", text: `${s.name} battery at ${s.battery_soc.toFixed(0)}%` });
  return out;
}
