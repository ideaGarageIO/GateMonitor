import { useEffect, useState } from "react";
import { useGateSocket } from "./useGateSocket";
import { StatusCard } from "./components/StatusCard";
import { Controls } from "./components/Controls";
import { History } from "./components/History";
import { LiveChart } from "./components/LiveChart";
import { clockTime } from "./format";

const WINDOWS = [
  { label: "5m", ms: 5 * 60_000 },
  { label: "15m", ms: 15 * 60_000 },
  { label: "1h", ms: 60 * 60_000 },
];

/** Ticks once a second so relative times and the chart's time axis keep moving. */
function useNow(intervalMs = 1000): number {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    const id = window.setInterval(() => setNow(Date.now()), intervalMs);
    return () => window.clearInterval(id);
  }, [intervalMs]);
  return now;
}

function Indicator({ label, on, title }: { label: string; on: boolean; title: string }) {
  return (
    <div className={`pill ${on ? "online" : "offline"}`} title={title}>
      <span className="dot" />
      {label}
    </div>
  );
}

export function App() {
  const { socketState, status, readings, history, sendCommand } = useGateSocket();
  const now = useNow();
  const [windowMs, setWindowMs] = useState(WINDOWS[0].ms);
  const connected = socketState === "open";

  return (
    <div className="container">
      <header>
        <h1>Gate Monitor</h1>
        <div className="indicators">
          <Indicator label="Server" on={connected} title="WebSocket connection to server" />
          <Indicator label="MQTT" on={connected && !!status?.mqtt_connected} title="MQTT broker connection" />
          <Indicator label="Gateway" on={connected && !!status?.gateway_online} title="House gateway heartbeat" />
        </div>
      </header>

      <main className="grid">
        <StatusCard status={status} now={now} />
        <Controls connected={connected} onCommand={sendCommand} />

        <section className="card telemetry-card">
          <div className="card-head">
            <h2>Live Telemetry</h2>
            <div className="segmented" role="group" aria-label="Time window">
              {WINDOWS.map((w) => (
                <button key={w.label} aria-pressed={windowMs === w.ms} onClick={() => setWindowMs(w.ms)}>
                  {w.label}
                </button>
              ))}
            </div>
          </div>
          <div className="charts">
            <LiveChart title="Battery" unit="V" field="battery_v" digits={2} minSpan={0.2}
              readings={readings} windowMs={windowMs} now={now} />
            <LiveChart title="Signal (RSSI)" unit="dBm" field="rssi" minSpan={10}
              readings={readings} windowMs={windowMs} now={now} />
            <LiveChart title="SNR" unit="dB" field="snr" digits={1} minSpan={4}
              readings={readings} windowMs={windowMs} now={now} />
          </div>
          <details className="table-view">
            <summary>Show readings table</summary>
            <table>
              <thead>
                <tr><th>Time</th><th>Battery (V)</th><th>RSSI (dBm)</th><th>SNR (dB)</th></tr>
              </thead>
              <tbody>
                {readings.slice(-15).reverse().map((r) => (
                  <tr key={r.t}>
                    <td>{clockTime(r.t)}</td>
                    <td>{r.battery_v.toFixed(2)}</td>
                    <td>{r.rssi}</td>
                    <td>{r.snr}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </details>
        </section>

        <History entries={history} now={now} />
      </main>

      <footer>Gate Monitor v0.2.0</footer>
    </div>
  );
}
