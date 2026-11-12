/** Wire types — mirror gate_monitor.models / gate_monitor.devices on the server. */

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
  last_command?: string | null;
}

export type DoorState = "UNKNOWN" | "OPEN" | "CLOSED" | "OPENING" | "CLOSING" | "JAMMED";
export type CoopCommand = "OPEN" | "CLOSE" | "STOP" | "AUTO" | "MANUAL";

interface DeviceBase {
  id: string;
  name: string;
  online: boolean;
  last_update: string;
  simulated: boolean;
}

export interface CoopStatus extends DeviceBase {
  kind: "coop";
  door: DoorState;
  mode: "auto" | "manual";
  temperature_c: number | null;
  humidity: number | null;
  battery_v: number | null;
  last_opened: string | null;
  last_closed: string | null;
  next_open: string | null;
  next_close: string | null;
}

export type ChargeState = "off" | "bulk" | "absorption" | "float" | "fault";

export interface SolarStatus extends DeviceBase {
  kind: "solar";
  battery_soc: number | null;
  battery_v: number | null;
  battery_a: number | null;
  panel_v: number | null;
  panel_w: number | null;
  load_w: number | null;
  charge_state: ChargeState;
  yield_today_wh: number | null;
}

export type Device = CoopStatus | SolarStatus;

export interface FarmEvent {
  device_id: string;
  ts: number;
  event: string;
  detail?: string | null;
}

export interface CommandResult {
  status: "sent" | "error";
  device?: string;
  command?: string;
  error?: string;
}

export type ServerMessage =
  | { type: "status"; data: GateStatus }
  | { type: "devices"; data: Device[] }
  | { type: "device"; data: Device }
  | { type: "event"; data: FarmEvent }
  | { type: "command_result"; data: CommandResult };

/** One telemetry sample for charts. `t` is epoch ms; other keys are numeric fields. */
export type Sample = { t: number } & Record<string, number>;

export type SocketState = "connecting" | "open" | "closed";
