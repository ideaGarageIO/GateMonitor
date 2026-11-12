/** Wire types — mirror gate_monitor.models (GateStatus.to_dict / HistoryEntry.to_dict). */

export type GateStateName = "UNKNOWN" | "CLOSED" | "OPEN" | "MOVING" | "ERROR";
export type GateCommand = "open" | "close" | "stop" | "status";

export interface GateStatus {
  state: GateStateName;
  state_code: number;
  battery_mv: number;
  battery_v: number;
  rssi: number;
  snr: number;
  online: boolean;
  last_update: string;
  mqtt_connected: boolean;
  gateway_online: boolean;
}

export interface HistoryEntry {
  timestamp: string;
  state: GateStateName;
  battery_mv: number;
  rssi?: number;
  snr?: number;
}

export type ServerMessage = { type: "status"; data: GateStatus };

/** One point on the live telemetry charts. `t` is epoch ms. */
export interface Reading {
  t: number;
  battery_v: number;
  rssi: number;
  snr: number;
}

export type SocketState = "connecting" | "open" | "closed";
