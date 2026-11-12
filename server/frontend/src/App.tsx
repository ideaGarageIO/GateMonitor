import { useEffect, useMemo, useState } from "react";
import { useFarmSocket } from "./useFarmSocket";
import { computeAlerts } from "./alerts";
import { Pill } from "./components/ui";
import { OverviewPage } from "./pages/OverviewPage";
import { GatePage } from "./pages/GatePage";
import { CoopsPage } from "./pages/CoopsPage";
import { SolarPage } from "./pages/SolarPage";

export type Tab = "overview" | "gate" | "coops" | "solar";

const TABS: { id: Tab; label: string; icon: string }[] = [
  { id: "overview", label: "Overview", icon: "◎" },
  { id: "gate", label: "Gate", icon: "▤" },
  { id: "coops", label: "Coops", icon: "⌂" },
  { id: "solar", label: "Solar", icon: "☀" },
];

function tabFromHash(): Tab {
  const h = window.location.hash.replace(/^#\/?/, "");
  return (TABS.find((t) => t.id === h)?.id ?? "overview") as Tab;
}

/** Hash routing (#/gate, #/coops...) — works behind any static server and from a home-screen icon. */
function useTab(): [Tab, (t: Tab) => void] {
  const [tab, setTab] = useState<Tab>(tabFromHash);
  useEffect(() => {
    const on = () => setTab(tabFromHash());
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  }, []);
  const go = (t: Tab) => {
    window.location.hash = `/${t}`;
    window.scrollTo({ top: 0 });
  };
  return [tab, go];
}

/** Ticks once a second so relative times and chart time axes keep moving. */
function useNow(intervalMs = 1000): number {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    const id = window.setInterval(() => setNow(Date.now()), intervalMs);
    return () => window.clearInterval(id);
  }, [intervalMs]);
  return now;
}

function Toast({ farm }: { farm: ReturnType<typeof useFarmSocket> }) {
  const [visible, setVisible] = useState(false);
  const r = farm.lastResult;
  useEffect(() => {
    if (!r) return;
    setVisible(true);
    const id = window.setTimeout(() => setVisible(false), 3000);
    return () => window.clearTimeout(id);
  }, [r]);
  if (!r || !visible) return null;
  const ok = r.result.status === "sent";
  return (
    <div className={`toast ${ok ? "ok" : "error"}`} role="status">
      {ok ? `Sent ${r.result.command} to ${r.result.device}` : `Command failed: ${r.result.error}`}
    </div>
  );
}

export function App() {
  const farm = useFarmSocket();
  const now = useNow();
  const [tab, go] = useTab();
  const connected = farm.socketState === "open";
  const alerts = useMemo(
    () => computeAlerts(farm.socketState, farm.gate, farm.devices, now),
    [farm.socketState, farm.gate, farm.devices, now],
  );
  const alertCount = (t: Tab) => alerts.filter((a) => t === "overview" || a.tab === t).length;

  useEffect(() => {
    const n = alerts.filter((a) => a.level === "critical").length;
    document.title = n ? `(${n}) Farm Monitor` : "Farm Monitor";
  }, [alerts]);

  return (
    <div className="container">
      <header>
        <h1>Farm Monitor</h1>
        <div className="indicators">
          <Pill on={connected} title="WebSocket connection to server">Server</Pill>
          <Pill on={connected && !!farm.gate?.mqtt_connected} title="MQTT broker connection">MQTT</Pill>
          <Pill on={connected && !!farm.gate?.gateway_online} title="House gateway heartbeat">Gateway</Pill>
        </div>
      </header>

      <nav className="tabs" aria-label="Monitors">
        {TABS.map((t) => {
          const n = alertCount(t.id);
          return (
            <a
              key={t.id}
              href={`#/${t.id}`}
              className="tab"
              aria-current={tab === t.id ? "page" : undefined}
            >
              <span className="tab-icon" aria-hidden>{t.icon}</span>
              <span className="tab-label">{t.label}</span>
              {n > 0 && <span className="tab-badge" aria-label={`${n} alerts`}>{n}</span>}
            </a>
          );
        })}
      </nav>

      <main>
        {tab === "overview" && <OverviewPage farm={farm} now={now} alerts={alerts} go={go} />}
        {tab === "gate" && <GatePage farm={farm} now={now} />}
        {tab === "coops" && <CoopsPage farm={farm} now={now} />}
        {tab === "solar" && <SolarPage farm={farm} now={now} />}
      </main>

      <Toast farm={farm} />
      <footer>Farm Monitor v0.2.0</footer>
    </div>
  );
}
