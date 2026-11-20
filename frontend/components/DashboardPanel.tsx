"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import {
  DashboardCheck,
  DashboardHealth,
  DashboardSnapshot,
  DashboardWebsite,
  DashboardWebsiteStats,
  DashboardWindow,
  getDashboard,
} from "@/lib/dashboard";

export function DashboardPanel() {
  const [windowName, setWindowName] = useState<DashboardWindow>("7d");
  const [data, setData] = useState<DashboardSnapshot | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    getDashboard(controller.signal, windowName)
      .then(setData)
      .catch((err: unknown) => {
        if (controller.signal.aborted) {
          return;
        }
        setError(err instanceof Error ? err.message : "Could not load the dashboard.");
      })
      .finally(() => {
        if (!controller.signal.aborted) {
          setLoading(false);
        }
      });
    return () => controller.abort();
  }, [windowName]);

  const statsById = useMemo(() => {
    const map = new Map<string, DashboardWebsiteStats>();
    if (!data) {
      return map;
    }
    for (const row of data.website_stats) {
      map.set(row.website_id, row);
    }
    return map;
  }, [data]);

  const recentFailures = useMemo(
    () => (data ? data.recent_checks.filter((check) => check.outcome !== "success") : []),
    [data],
  );

  if (error) {
    return (
      <p className="banner warn" role="alert">
        {error}
      </p>
    );
  }
  if (!data || loading) {
    return <p className="hint">Loading dashboard…</p>;
  }

  return (
    <div className="registry dashboard-panel">
      <AttentionCard
        health={data.health}
        windowName={data.stats_window}
        failures={recentFailures}
        hasSites={data.websites.length > 0}
      />

      <section className="card health-overview" aria-label="Health overview">
        <div className="stats-toolbar">
          <h2>Health overview</h2>
          <label className="stats-window">
            Window
            <select
              value={windowName}
              onChange={(event) => setWindowName(event.target.value as DashboardWindow)}
            >
              <option value="24h">Last 24 hours</option>
              <option value="7d">Last 7 days</option>
              <option value="all">Recent sample</option>
            </select>
          </label>
        </div>
        <HealthGrid health={data.health} windowName={data.stats_window} />
      </section>

      <section className="card" aria-label="Your websites">
        <h2>Your websites</h2>
        <p className="hint tight">
          Open site health for Overview, Investigate, and Automation.
        </p>
        {data.websites.length === 0 ? (
          <p className="hint">
            No sites yet. <Link href="/websites">Register one</Link>.
          </p>
        ) : (
          <ul className="website-list">
            {data.websites.map((site) => (
              <WebsiteRow key={site.id} site={site} stats={statsById.get(site.id) ?? null} />
            ))}
          </ul>
        )}
      </section>

      <section className="card" aria-label="Recent checks">
        <h2>Recent checks</h2>
        <p className="hint tight">
          Window <code>{data.history_window}</code> · capped at {data.recent_check_limit} rows.
        </p>
        {data.recent_checks.length === 0 ? (
          <p className="hint">
            No checks in this window. Run one from a site health page or the websites registry.
          </p>
        ) : (
          <ul className="check-history-list">
            {data.recent_checks.map((check) => (
              <CheckRow key={check.id} check={check} />
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}

function AttentionCard({
  health,
  windowName,
  failures,
  hasSites,
}: {
  health: DashboardHealth;
  windowName: string;
  failures: DashboardCheck[];
  hasSites: boolean;
}) {
  const leadFailure = failures[0] ?? null;

  if (!hasSites) {
    return (
      <section className="card attention-card" aria-label="Needs attention">
        <h2>Needs attention</h2>
        <p className="next-action">
          Next: <Link href="/websites">register a website</Link>, then run a check from Site health.
        </p>
        <div className="actions">
          <Link className="button-link primary" href="/websites">
            Manage websites
          </Link>
        </div>
      </section>
    );
  }

  if (health.recent_failure_count === 0) {
    return (
      <section className="card attention-card ok-tone" aria-label="Needs attention">
        <h2>Needs attention</h2>
        <p>
          No recent failures in window <code>{windowName}</code>.
        </p>
        <p className="next-action">
          Next: skim Overview trends, or open a site to tune Automation scheduling.
        </p>
        <div className="actions">
          <Link className="button-link" href="/websites">
            Manage websites
          </Link>
        </div>
      </section>
    );
  }

  return (
    <section className="card attention-card" aria-label="Needs attention">
      <h2>Needs attention</h2>
      <p>
        {health.recent_failure_count} recent failure
        {health.recent_failure_count === 1 ? "" : "s"} across {health.sites_with_failures} site
        {health.sites_with_failures === 1 ? "" : "s"} in window <code>{windowName}</code>.
      </p>
      <p className="next-action">
        Next: open a failed check, run analysis, then use Site Health → Investigate for patterns or
        an incident draft.
      </p>
      {leadFailure ? (
        <ul className="check-history-list attention-failures">
          <li>
            <p>
              <span className="bad">{leadFailure.outcome}</span>
              {" · "}
              <Link href={`/checks/${leadFailure.id}`}>
                {leadFailure.website_name} · {leadFailure.duration_ms} ms
              </Link>
            </p>
            {leadFailure.error_message ? (
              <p className="meta">{leadFailure.error_message}</p>
            ) : null}
            <p className="meta">
              <Link href={`/checks/${leadFailure.id}`}>Analyze this failure</Link>
              {" · "}
              <Link href={`/websites/${leadFailure.website_id}`}>Open site health</Link>
            </p>
          </li>
        </ul>
      ) : null}
      <div className="actions">
        <Link className="button-link" href="/websites">
          Manage websites
        </Link>
      </div>
    </section>
  );
}

function HealthGrid({
  health,
  windowName,
}: {
  health: DashboardHealth;
  windowName: string;
}) {
  return (
    <>
      <dl className="health-grid">
        <div>
          <dt>Sites</dt>
          <dd>{health.website_count}</dd>
        </div>
        <div>
          <dt>Monitored</dt>
          <dd>{health.monitored_count}</dd>
        </div>
        <div>
          <dt>With checks</dt>
          <dd>{health.sites_with_checks}</dd>
        </div>
        <div>
          <dt>Sites with failures</dt>
          <dd className={health.sites_with_failures > 0 ? "bad" : "ok"}>
            {health.sites_with_failures}
          </dd>
        </div>
        <div>
          <dt>Avg uptime</dt>
          <dd
            className={
              health.avg_uptime_percent != null && health.avg_uptime_percent < 100 ? "bad" : "ok"
            }
          >
            {health.avg_uptime_percent != null ? `${health.avg_uptime_percent}%` : "—"}
          </dd>
        </div>
        <div>
          <dt>Recent failures</dt>
          <dd className={health.recent_failure_count > 0 ? "bad" : "ok"}>
            {health.recent_failure_count}
          </dd>
        </div>
      </dl>
      <p className="hint tight">
        Roll-up for window <code>{windowName}</code>.
      </p>
    </>
  );
}

function WebsiteRow({
  site,
  stats,
}: {
  site: DashboardWebsite;
  stats: DashboardWebsiteStats | null;
}) {
  const isDemo = site.name.trim().startsWith("[Demo]");
  return (
    <li className="website">
      <div>
        <h3>
          {isDemo ? <span className="demo-chip">Demo</span> : null}{" "}
          <Link href={`/websites/${site.id}`}>{site.name}</Link>
        </h3>
        {isDemo ? (
          <p className="meta">Sample portfolio data — not live monitoring</p>
        ) : null}
        <p className="meta">{site.base_url}</p>
        <p className="meta">Monitoring: {site.monitoring_enabled ? "enrolled" : "off"}</p>
        {stats ? (
          <p className="meta">
            Uptime{" "}
            <span
              className={
                stats.uptime_percent != null && stats.uptime_percent < 100 ? "bad" : "ok"
              }
            >
              {stats.uptime_percent != null ? `${stats.uptime_percent}%` : "n/a"}
            </span>
            {" · "}
            {stats.check_count} checks
            {stats.avg_duration_ms != null
              ? ` · avg ${Math.round(stats.avg_duration_ms)} ms`
              : ""}
            {stats.p95_duration_ms != null ? ` · p95 ${stats.p95_duration_ms} ms` : ""}
          </p>
        ) : null}
        <p className="meta">
          <Link href={`/websites/${site.id}`}>Open site health</Link>
        </p>
      </div>
    </li>
  );
}

function CheckRow({ check }: { check: DashboardCheck }) {
  const failed = check.outcome !== "success";
  const isDemo =
    typeof check.error_message === "string" &&
    check.error_message.includes("Demo result — not a live browser check");
  return (
    <li>
      <p>
        <span className={failed ? "bad" : "ok"}>{check.outcome}</span>
        {isDemo ? (
          <>
            {" · "}
            <span className="demo-chip">Demo</span>
          </>
        ) : null}
        {" · "}
        <Link href={`/websites/${check.website_id}`}>{check.website_name}</Link>
        {" · "}
        {check.duration_ms} ms
        {check.http_status != null ? ` · HTTP ${check.http_status}` : ""}
      </p>
      <p className="meta">{new Date(check.created_at).toLocaleString()}</p>
      {check.error_message ? <p className="meta">{check.error_message}</p> : null}
      <p className="meta">
        {failed ? (
          <Link href={`/checks/${check.id}`}>Analyze this failure</Link>
        ) : (
          <Link href={`/checks/${check.id}`}>Open check detail</Link>
        )}
      </p>
    </li>
  );
}
