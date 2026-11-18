"use client";

import type { StatsPoint } from "@/lib/stats";

type LatencyChartProps = {
  points: StatsPoint[];
  label?: string;
};

/**
 * Local SVG latency sparkline + outcome strip. No chart SaaS.
 * Points are newest-first from the API; we draw oldest → newest left to right.
 */
export function LatencyChart({ points, label = "Latency trend" }: LatencyChartProps) {
  if (points.length === 0) {
    return <p className="hint tight">No samples to chart yet.</p>;
  }

  const ordered = [...points].reverse();
  const maxDuration = Math.max(...ordered.map((point) => point.duration_ms), 1);
  const width = 320;
  const height = 72;
  const padY = 6;
  const usable = height - padY * 2;
  const step = ordered.length === 1 ? 0 : width / (ordered.length - 1);

  const polyline = ordered
    .map((point, index) => {
      const x = ordered.length === 1 ? width / 2 : index * step;
      const y = padY + usable - (point.duration_ms / maxDuration) * usable;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");

  return (
    <div className="latency-chart" aria-label={label}>
      <svg
        className="latency-sparkline"
        viewBox={`0 0 ${width} ${height}`}
        role="img"
        aria-hidden="true"
      >
        <polyline
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinejoin="round"
          strokeLinecap="round"
          points={polyline}
        />
      </svg>
      <div className="latency-bars" aria-label="Recent check outcomes">
        {ordered.map((point) => (
          <div
            key={`${point.created_at}-${point.duration_ms}-${point.outcome}`}
            className={`latency-bar ${point.outcome === "success" ? "ok" : "bad"}`}
            title={`${point.outcome} · ${point.duration_ms} ms · ${new Date(point.created_at).toLocaleString()}`}
            style={{
              height: `${Math.max(8, Math.round((point.duration_ms / maxDuration) * 48))}px`,
            }}
          />
        ))}
      </div>
    </div>
  );
}
