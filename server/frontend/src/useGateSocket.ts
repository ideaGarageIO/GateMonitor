import { useCallback, useEffect, useRef, useState } from "react";
import type {
  GateCommand,
  GateStatus,
  HistoryEntry,
  Reading,
  ServerMessage,
  SocketState,
} from "./types";

/** Keep roughly an hour of readings in memory. */
const MAX_READINGS = 3600;
const MAX_HISTORY = 20;
const BASE_RECONNECT_MS = 1000;
const MAX_RECONNECT_MS = 15000;

function wsUrl(): string {
  const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${proto}//${window.location.host}/ws`;
}

function toReading(s: { last_update: string; battery_v: number; rssi: number; snr: number }): Reading {
  return { t: Date.parse(s.last_update), battery_v: s.battery_v, rssi: s.rssi, snr: s.snr };
}

/**
 * Owns the WebSocket to the FastAPI server: reconnects with backoff,
 * exposes the latest status, a rolling telemetry buffer, and state-change history.
 */
export function useGateSocket() {
  const [socketState, setSocketState] = useState<SocketState>("connecting");
  const [status, setStatus] = useState<GateStatus | null>(null);
  const [readings, setReadings] = useState<Reading[]>([]);
  const [history, setHistory] = useState<HistoryEntry[]>([]);
  const wsRef = useRef<WebSocket | null>(null);
  const lastStateRef = useRef<GateStatus["state"] | null>(null);

  // Backfill from REST so charts and activity aren't empty on first load.
  useEffect(() => {
    let cancelled = false;
    fetch("/api/history")
      .then((r) => (r.ok ? r.json() : []))
      .then((entries: HistoryEntry[]) => {
        if (cancelled || !Array.isArray(entries)) return;
        setHistory(entries.slice(-MAX_HISTORY).reverse());
        const backfill = entries
          .filter((e) => e.rssi !== undefined)
          .map((e) => ({
            t: Date.parse(e.timestamp),
            battery_v: e.battery_mv / 1000,
            rssi: e.rssi ?? 0,
            snr: e.snr ?? 0,
          }));
        // Merge with anything the socket already delivered.
        setReadings((live) => mergeReadings(backfill, live));
      })
      .catch((e) => console.error("Failed to load history", e));
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let attempts = 0;
    let timer: number | undefined;
    let disposed = false;

    const connect = () => {
      setSocketState("connecting");
      const ws = new WebSocket(wsUrl());
      wsRef.current = ws;

      ws.onopen = () => {
        attempts = 0;
        setSocketState("open");
      };

      ws.onmessage = (ev) => {
        let msg: ServerMessage;
        try {
          msg = JSON.parse(ev.data);
        } catch {
          return;
        }
        if (msg.type !== "status") return;
        const next = msg.data;

        // A changed state is "activity"; record it.
        const prevState = lastStateRef.current;
        lastStateRef.current = next.state;
        if (prevState !== null && prevState !== next.state) {
          setHistory((h) =>
            [
              { timestamp: next.last_update, state: next.state, battery_mv: next.battery_mv },
              ...h,
            ].slice(0, MAX_HISTORY),
          );
        }
        setStatus(next);

        // Only chart readings while the gate node is actually reporting.
        if (next.online && next.gateway_online) {
          setReadings((r) => mergeReadings(r, [toReading(next)]));
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
    return () => {
      disposed = true;
      window.clearTimeout(timer);
      wsRef.current?.close();
    };
  }, []);

  const sendCommand = useCallback((command: GateCommand): boolean => {
    const ws = wsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) return false;
    ws.send(JSON.stringify({ type: "command", command }));
    return true;
  }, []);

  return { socketState, status, readings, history, sendCommand };
}

/** Merge two time-sorted reading lists, dropping duplicate timestamps, capped to MAX_READINGS. */
function mergeReadings(a: Reading[], b: Reading[]): Reading[] {
  if (b.length === 0) return a;
  const last = a[a.length - 1];
  // Fast path: live append.
  if (b.length === 1 && (!last || b[0].t > last.t)) {
    const out = a.length >= MAX_READINGS ? a.slice(a.length - MAX_READINGS + 1) : a.slice();
    out.push(b[0]);
    return out;
  }
  const byT = new Map<number, Reading>();
  for (const r of a) byT.set(r.t, r);
  for (const r of b) byT.set(r.t, r);
  return [...byT.values()]
    .filter((r) => Number.isFinite(r.t))
    .sort((x, y) => x.t - y.t)
    .slice(-MAX_READINGS);
}
