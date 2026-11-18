"use client";

import { useEffect, useState } from "react";

import { LatencyChart } from "@/components/LatencyChart";
import { getWebsiteStats, type StatsWindow, type WebsiteStats } from "@/lib/stats";
import { WebsiteApiError } from "@/lib/websites";

type WebsiteStatsPanelProps = {
  websiteId: string;
};

export function WebsiteStatsPanel({ websiteId }: WebsiteStatsPanelProps) {
  const [windowName, setWindowName] = useState<StatsWindow>("7d");
  const [stats, setStats] = useState<WebsiteStats | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    getWebsiteStats(websiteId, windowName, controller.signal)
      .then(setStats)
      .catch((err: unknown) => {
        if (err instanceof DOMException && err.name === "AbortError") {
          return;
        }
        setStats(null);
        setError(err instanceof WebsiteApiError ? err.message : "Stats could not be loaded.");
      })
      .finally(() => setLoading(false));
    return () => controller.abort();
  }, [websiteId, windowName]);

  return (
    <div className="stats-panel">
      <div className="stats-toolbar">
        <h3>Uptime & latency</h3>
        <label className="stats-window">
          Window
          <select
            value={windowName}
            onChange={(event) => setWindowName(event.target.value as StatsWindow)}
          >
            <option value="24h">Last 24 hours</option>
            <option value="7d">Last 7 days</option>
            <option value="all">Recent sample</option>
          </select>
        </label>
      </div>
      {loading ? <p className="hint tight">Loading stats…</p> : null}
      {error ? (
        <p className="field-error" role="alert">
          {error}
        </p>
      ) : null}
      {stats && !loading ? <StatsBody stats={stats} /> : null}
    </div>
  );
}

function StatsBody({ stats }: { stats: WebsiteStats }) {
  if (stats.check_count === 0) {
    return <p className="hint tight">No checks in this window yet.</p>;
  }

  return (
    <div className="stats-body">
      <dl className="stats-grid">
        <div>
          <dt>Uptime</dt>
          <dd className={stats.uptime_percent != null && stats.uptime_percent < 100 ? "bad" : "ok"}>
            {stats.uptime_percent != null ? `${stats.uptime_percent}%` : "—"}
          </dd>
        </div>
        <div>
          <dt>Checks</dt>
          <dd>
            {stats.success_count}/{stats.check_count} ok
          </dd>
        </div>
        <div>
          <dt>Avg</dt>
          <dd>{stats.avg_duration_ms != null ? `${Math.round(stats.avg_duration_ms)} ms` : "—"}</dd>
        </div>
        <div>
          <dt>p95</dt>
          <dd>{stats.p95_duration_ms != null ? `${stats.p95_duration_ms} ms` : "—"}</dd>
        </div>
      </dl>
      <p className="hint tight">
        Sample of up to {stats.sample_limit} newest checks in window <code>{stats.window}</code>.
        Chart is local SVG — no paid analytics.
      </p>
      <LatencyChart points={stats.points} />
    </div>
  );
}
