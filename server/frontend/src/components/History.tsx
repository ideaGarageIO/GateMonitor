import type { HistoryEntry } from "../types";
import { relativeTime } from "../format";

export function History({ entries, now }: { entries: HistoryEntry[]; now: number }) {
  return (
    <section className="card history-card">
      <h2>Recent Activity</h2>
      {entries.length === 0 ? (
        <p className="muted">No activity recorded</p>
      ) : (
        <ul className="history-list">
          {entries.map((e, i) => (
            <li key={`${e.timestamp}-${i}`} className="history-item">
              <span className={`state-badge ${e.state.toLowerCase()}`}>{e.state}</span>
              <span className="muted">{relativeTime(Date.parse(e.timestamp), now)}</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
