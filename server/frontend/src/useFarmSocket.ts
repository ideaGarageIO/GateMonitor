import { useCallback, useEffect, useRef, useState } from "react";
import type {
  CommandResult,
  Device,
  FarmEvent,
  GateStatus,
  Sample,
  ServerMessage,
  SocketState,
} from "./types";

/** ~1 hour of 1 Hz samples per device. */
const MAX_SAMPLES = 3600;
const MAX_EVENTS = 100;
const BACKFILL_MINUTES = 60;
const BASE_RECONNECT_MS = 1000;
const MAX_RECONNECT_MS = 15000;
export const GATE_ID = "gate";

function wsUrl(): string {
  const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${proto}//${window.location.host}/ws`;
}

/** Numeric fields of a status object, as a chart sample. */
function toSample(t: number, obj: object): Sample {
  const s: Sample = { t } as Sample;
  for (const [k, v] of Object.entries(obj)) {
    if (typeof v === "number" && Number.isFinite(v)) s[k] = v;
  }
  return s;
}

function gateSample(g: GateStatus): Sample {
  return { t: Date.parse(g.last_update), battery_v: g.battery_v, rssi: g.rssi, snr: g.snr } as Sample;
}

/** Merge time-sorted sample lists, de-duplicating by timestamp, capped. */
export function mergeSamples(a: Sample[], b: Sample[]): Sample[] {
  if (b.length === 0) return a;
  const last = a[a.length - 1];
  if (b.length === 1 && (!last || b[0].t > last.t)) {
    const out = a.length >= MAX_SAMPLES ? a.slice(a.length - MAX_SAMPLES + 1) : a.slice();
    out.push(b[0]);
    return out;
  }
  const byT = new Map<number, Sample>();
  for (const s of a) byT.set(s.t, s);
  for (const s of b) byT.set(s.t, s);
  return [...byT.values()]
    .filter((s) => Number.isFinite(s.t))
    .sort((x, y) => x.t - y.t)
    .slice(-MAX_SAMPLES);
}

async function fetchJson<T>(url: string, fallback: T): Promise<T> {
  try {
    const r = await fetch(url);
    return r.ok ? ((await r.json()) as T) : fallback;
  } catch {
    return fallback;
  }
}

/**
 * Single WebSocket to the server for every device. Keeps the latest status per
 * device, a rolling telemetry buffer per device (backfilled from SQLite), and
 * the activity log.
 */
export function useFarmSocket() {
  const [socketState, setSocketState] = useState<SocketState>("connecting");
  const [gate, setGate] = useState<GateStatus | null>(null);
  const [devices, setDevices] = useState<Record<string, Device>>({});
  const [samples, setSamples] = useState<Record<string, Sample[]>>({});
  const [events, setEvents] = useState<FarmEvent[]>([]);
  const [lastResult, setLastResult] = useState<{ at: number; result: CommandResult } | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const backfilled = useRef<Set<string>>(new Set());

  const addSamples = useCallback((id: string, list: Sample[]) => {
    setSamples((all) => ({ ...all, [id]: mergeSamples(all[id] ?? [], list) }));
  }, []);

  const backfill = useCallback(
    (id: string) => {
      if (backfilled.current.has(id)) return;
      backfilled.current.add(id);
      fetchJson<Sample[]>(`/api/readings/${encodeURIComponent(id)}?minutes=${BACKFILL_MINUTES}`, []).then(
        (list) => Array.isArray(list) && list.length && addSamples(id, list),
      );
    },
    [addSamples],
  );

  useEffect(() => {
    backfill(GATE_ID);
    fetchJson<FarmEvent[]>(`/api/events?limit=${MAX_EVENTS}`, []).then((list) => {
      if (!Array.isArray(list)) return;
      setEvents((live) => {
        const seen = new Set(live.map((e) => `${e.device_id}:${e.ts}:${e.event}`));
        return [...live, ...list.filter((e) => !seen.has(`${e.device_id}:${e.ts}:${e.event}`))]
          .sort((a, b) => b.ts - a.ts)
          .slice(0, MAX_EVENTS);
      });
    });
  }, [backfill]);

  useEffect(() => {
    let attempts = 0;
    let timer: number | undefined;
    let disposed = false;

    const onDevice = (d: Device) => {
      setDevices((all) => ({ ...all, [d.id]: d }));
      if (d.online) addSamples(d.id, [toSample(Date.parse(d.last_update), d)]);
      backfill(d.id);
    };

    const handle = (msg: ServerMessage) => {
      switch (msg.type) {
        case "status":
          setGate(msg.data);
          if (msg.data.online && msg.data.gateway_online && msg.data.battery_mv) {
            addSamples(GATE_ID, [gateSample(msg.data)]);
          }
          break;
        case "devices":
          msg.data.forEach(onDevice);
          break;
        case "device":
          onDevice(msg.data);
          break;
        case "event":
          setEvents((e) => [msg.data, ...e].slice(0, MAX_EVENTS));
          break;
        case "command_result":
          setLastResult({ at: Date.now(), result: msg.data });
          break;
      }
    };

    const connect = () => {
      setSocketState("connecting");
      const ws = new WebSocket(wsUrl());
      wsRef.current = ws;
      ws.onopen = () => {
        attempts = 0;
        setSocketState("open");
      };
      ws.onmessage = (ev) => {
        try {
          handle(JSON.parse(ev.data) as ServerMessage);
        } catch (e) {
          console.warn("Bad message", e);
        }
      };
      ws.onclose = () => {
        wsRef.current = null;
        setSocketState("closed");
        if (disposed) return;
        const delay = Math.min(MAX_RECONNECT_MS, BASE_RECONNECT_MS * 2 ** attempts);
        attempts += 1;
        timer = window.setTimeout(connect, delay);
      };
      ws.onerror = () => ws.close();
    };

    connect();
    // Phones suspend background tabs; reconnect immediately on return.
    const onVisible = () => {
      if (document.visibilityState === "visible" && !wsRef.current && !disposed) {
        window.clearTimeout(timer);
        attempts = 0;
        connect();
      }
    };
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      disposed = true;
      window.clearTimeout(timer);
      document.removeEventListener("visibilitychange", onVisible);
      wsRef.current?.close();
    };
  }, [addSamples, backfill]);

  /** Send a command over the socket. Returns false if not connected. */
  const sendCommand = useCallback((device: string, command: string): boolean => {
    const ws = wsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) return false;
    ws.send(JSON.stringify({ type: "command", device, command }));
    return true;
  }, []);

  return { socketState, gate, devices, samples, events, lastResult, sendCommand };
}

export type FarmState = ReturnType<typeof useFarmSocket>;
