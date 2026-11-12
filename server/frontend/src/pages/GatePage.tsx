import { useState } from "react";
import type { FarmState } from "../useFarmSocket";
import { GATE_ID } from "../useFarmSocket";
import { StatusCard } from "../components/StatusCard";
import { Controls } from "../components/Controls";
import { LiveChart } from "../components/LiveChart";
import { EventList, WINDOWS, WindowPicker } from "../components/ui";
import { clockTime } from "../format";

export function GatePage({ farm, now }: { farm: FarmState; now: number }) {
  const [windowMs, setWindowMs] = useState(WINDOWS[0].ms);
  const samples = farm.samples[GATE_ID] ?? [];
  const connected = farm.socketState === "open";
  const events = farm.events.filter((e) => e.device_id === GATE_ID).slice(0, 25);

  return (
    <div className="grid">
      <StatusCard status={farm.gate} now={now} />
      <Controls connected={connected} onCommand={(c) => farm.sendCommand(GATE_ID, c)} />

      <section className="card span-all">
        <div className="card-head">
          <h2>Live Telemetry</h2>
          <WindowPicker value={windowMs} onChange={setWindowMs} />
        </div>
        <div className="charts">
          <LiveChart title="Battery" unit="V" field="battery_v" digits={2} minSpan={0.2}
            readings={samples} windowMs={windowMs} now={now} />
          <LiveChart title="Signal (RSSI)" unit="dBm" field="rssi" minSpan={10}
            readings={samples} windowMs={windowMs} now={now} />
          <LiveChart title="SNR" unit="dB" field="snr" digits={1} minSpan={4}
            readings={samples} windowMs={windowMs} now={now} />
        </div>
        <details className="table-view">
          <summary>Show readings table</summary>
          <table>
            <thead>
              <tr><th>Time</th><th>Battery (V)</th><th>RSSI (dBm)</th><th>SNR (dB)</th></tr>
            </thead>
            <tbody>
              {samples.slice(-15).reverse().map((r) => (
                <tr key={r.t}>
                  <td>{clockTime(r.t)}</td>
                  <td>{r.battery_v?.toFixed(2)}</td>
                  <td>{r.rssi}</td>
                  <td>{r.snr}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </details>
      </section>

      <section className="card span-all">
        <h2>Gate Activity</h2>
        <EventList events={events} now={now} />
      </section>
    </div>
  );
}
