import { useLayoutEffect, useMemo, useRef, useState } from "react";
import type { Reading } from "../types";
import { clockTime } from "../format";

type Key = "battery_v" | "rssi" | "snr";

interface Props {
  title: string;
  unit: string;
  field: Key;
  readings: Reading[];
  windowMs: number;
  now: number;
  digits?: number;
  /** Minimum visible y-span so a flat signal doesn't look like noise. */
  minSpan: number;
}

const HEIGHT = 150;
const PAD = { top: 10, right: 12, bottom: 22, left: 40 };
/** Break the line when the node went quiet for longer than this. */
const GAP_MS = 60_000;

function niceTicks(min: number, max: number, count = 3): number[] {
  const step = (max - min) / (count - 1);
  return Array.from({ length: count }, (_, i) => min + step * i);
}

export function LiveChart({ title, unit, field, readings, windowMs, now, digits = 0, minSpan }: Props) {
  const wrapRef = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(320);
  const [hoverIdx, setHoverIdx] = useState<number | null>(null);

  useLayoutEffect(() => {
    const el = wrapRef.current;
    if (!el) return;
    const ro = new ResizeObserver(([entry]) => setWidth(Math.max(200, entry.contentRect.width)));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const t0 = now - windowMs;
  const visible = useMemo(() => readings.filter((r) => r.t >= t0), [readings, t0]);
  const latest = readings[readings.length - 1];

  const [yMin, yMax] = useMemo(() => {
    if (visible.length === 0) return [0, minSpan];
    let lo = Infinity;
    let hi = -Infinity;
    for (const r of visible) {
      lo = Math.min(lo, r[field]);
      hi = Math.max(hi, r[field]);
    }
    const span = Math.max(hi - lo, minSpan);
    const mid = (hi + lo) / 2;
    return [mid - span * 0.6, mid + span * 0.6];
  }, [visible, field, minSpan]);

  const innerW = width - PAD.left - PAD.right;
  const innerH = HEIGHT - PAD.top - PAD.bottom;
  const x = (t: number) => PAD.left + ((t - t0) / windowMs) * innerW;
  const y = (v: number) => PAD.top + (1 - (v - yMin) / (yMax - yMin)) * innerH;

  const path = useMemo(() => {
    let d = "";
    let prevT = -Infinity;
    for (const r of visible) {
      const cmd = r.t - prevT > GAP_MS ? "M" : "L";
      d += `${cmd}${x(r.t).toFixed(1)},${y(r[field]).toFixed(1)}`;
      prevT = r.t;
    }
    return d;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [visible, field, width, yMin, yMax, t0, windowMs]);

  const onPointerMove = (e: React.PointerEvent<SVGRectElement>) => {
    if (visible.length === 0) return;
    const box = e.currentTarget.getBoundingClientRect();
    const t = t0 + ((e.clientX - box.left) / box.width) * windowMs;
    // Binary search for the nearest reading in time.
    let lo = 0;
    let hi = visible.length - 1;
    while (lo < hi) {
      const mid = (lo + hi) >> 1;
      if (visible[mid].t < t) lo = mid + 1;
      else hi = mid;
    }
    if (lo > 0 && Math.abs(visible[lo - 1].t - t) < Math.abs(visible[lo].t - t)) lo -= 1;
    setHoverIdx(lo);
  };

  const hover = hoverIdx !== null ? visible[hoverIdx] : undefined;
  const ticks = niceTicks(yMin, yMax);
  const xTicks = [t0, t0 + windowMs / 2, now];
  const fmt = (v: number) => v.toFixed(digits);
  const last = visible[visible.length - 1];

  return (
    <figure className="chart">
      <figcaption className="chart-head">
        <span className="chart-title">{title}</span>
        <span className="chart-value">
          {latest ? fmt(latest[field]) : "--"}
          <span className="chart-unit">{unit}</span>
        </span>
      </figcaption>
      <div className="chart-plot" ref={wrapRef}>
        <svg width={width} height={HEIGHT} role="img" aria-label={`${title} over the last ${Math.round(windowMs / 60000)} minutes`}>
          {ticks.map((v) => (
            <g key={v}>
              <line className="grid" x1={PAD.left} x2={width - PAD.right} y1={y(v)} y2={y(v)} />
              <text className="axis" x={PAD.left - 6} y={y(v)} dy="0.32em" textAnchor="end">
                {fmt(v)}
              </text>
            </g>
          ))}
          {xTicks.map((t, i) => (
            <text
              key={i}
              className="axis"
              x={x(t)}
              y={HEIGHT - 6}
              textAnchor={i === 0 ? "start" : i === 2 ? "end" : "middle"}
            >
              {i === 2 ? "now" : clockTime(t).slice(0, 5)}
            </text>
          ))}
          <path className="series" d={path} />
          {last && <circle className="series-dot live" cx={x(last.t)} cy={y(last[field])} r={4} />}
          {hover && (
            <g pointerEvents="none">
              <line className="crosshair" x1={x(hover.t)} x2={x(hover.t)} y1={PAD.top} y2={PAD.top + innerH} />
              <circle className="series-dot" cx={x(hover.t)} cy={y(hover[field])} r={4} />
            </g>
          )}
          <rect
            x={PAD.left}
            y={PAD.top}
            width={innerW}
            height={innerH}
            fill="transparent"
            onPointerMove={onPointerMove}
            onPointerLeave={() => setHoverIdx(null)}
          />
        </svg>
        {visible.length === 0 && <div className="chart-empty">Waiting for readings…</div>}
        {hover && (
          <div
            className="tooltip"
            style={{
              left: Math.min(Math.max(x(hover.t), 60), width - 60),
              top: Math.max(y(hover[field]) - 12, 0),
            }}
          >
            <strong>
              {fmt(hover[field])} {unit}
            </strong>
            <span>{clockTime(hover.t)}</span>
          </div>
        )}
      </div>
    </figure>
  );
}
