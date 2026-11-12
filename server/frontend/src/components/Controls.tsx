import { useEffect, useState } from "react";
import type { GateCommand } from "../types";

interface Props {
  connected: boolean;
  onCommand: (cmd: GateCommand) => boolean;
}

type Feedback = { text: string; kind: "pending" | "error" } | null;

const BUTTONS: { cmd: GateCommand; label: string; icon: string }[] = [
  { cmd: "open", label: "Open", icon: "▲" },
  { cmd: "stop", label: "Stop", icon: "■" },
  { cmd: "close", label: "Close", icon: "▼" },
];

export function Controls({ connected, onCommand }: Props) {
  const [feedback, setFeedback] = useState<Feedback>(null);

  useEffect(() => {
    if (!feedback) return;
    const id = window.setTimeout(() => setFeedback(null), 3000);
    return () => window.clearTimeout(id);
  }, [feedback]);

  const send = (cmd: GateCommand) => {
    if (onCommand(cmd)) setFeedback({ text: `Sent ${cmd.toUpperCase()}`, kind: "pending" });
    else setFeedback({ text: "Not connected to server", kind: "error" });
  };

  return (
    <section className="card control-card">
      <h2>Controls</h2>
      <div className="control-buttons">
        {BUTTONS.map((b) => (
          <button key={b.cmd} className={`btn btn-${b.cmd}`} disabled={!connected} onClick={() => send(b.cmd)}>
            <span className="btn-icon" aria-hidden>
              {b.icon}
            </span>
            {b.label}
          </button>
        ))}
      </div>
      <div className={`command-feedback ${feedback?.kind ?? ""}`} role="status">
        {feedback?.text}
      </div>
    </section>
  );
}
