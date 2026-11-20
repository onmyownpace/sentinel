"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { IncidentDraftPanel } from "@/components/IncidentDraftPanel";
import { JourneyPanel } from "@/components/JourneyPanel";
import { PatternHintsPanel } from "@/components/PatternHintsPanel";
import { ScenarioPanel } from "@/components/ScenarioPanel";
import { WebsiteChecks } from "@/components/WebsiteChecks";
import { WebsiteMonitoringConfig } from "@/components/WebsiteMonitoringConfig";
import { WebsiteStatsPanel } from "@/components/WebsiteStats";
import { getMonitoringState, type MonitoringState } from "@/lib/monitoring";
import { getWebsite, WebsiteApiError, type Website } from "@/lib/websites";

type SiteHealthPanelProps = {
  websiteId: string;
};

type HealthTab = "overview" | "investigate" | "automation";

const TABS: { id: HealthTab; label: string }[] = [
  { id: "overview", label: "Overview" },
  { id: "investigate", label: "Investigate" },
  { id: "automation", label: "Automation" },
];

export function SiteHealthPanel({ websiteId }: SiteHealthPanelProps) {
  const router = useRouter();
  const [website, setWebsite] = useState<Website | null>(null);
  const [state, setState] = useState<MonitoringState | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<HealthTab>("overview");

  useEffect(() => {
    const controller = new AbortController();
    setError(null);
    Promise.all([
      getWebsite(websiteId, controller.signal),
      getMonitoringState(websiteId, controller.signal).catch(() => null),
    ])
      .then(([site, monitoring]) => {
        setWebsite(site);
        setState(monitoring);
      })
      .catch((err: unknown) => {
        if (controller.signal.aborted) {
          return;
        }
        if (err instanceof WebsiteApiError && err.status === 401) {
          router.replace("/login");
          return;
        }
        if (err instanceof WebsiteApiError && err.status === 404) {
          setError("That website was not found.");
          return;
        }
        setError(err instanceof Error ? err.message : "Could not load this site.");
      });
    return () => controller.abort();
  }, [websiteId, router]);

  if (error) {
    return (
      <div className="registry">
        <p className="banner warn" role="alert">
          {error}
        </p>
        <p>
          <Link href="/dashboard">Back to dashboard</Link>
        </p>
      </div>
    );
  }

  if (!website) {
    return <p className="hint">Loading site health…</p>;
  }

  const failing = Boolean(state?.still_failing || state?.status === "failing");
  const recovered = Boolean(state?.recovered || state?.status === "healthy");
  const isDemo = website.name.trim().startsWith("[Demo]");

  return (
    <div className="registry site-health">
      <p className="crumb">
        <Link href="/dashboard">Dashboard</Link>
        {" · "}
        <Link href="/websites">Websites</Link>
        {" · "}
        {website.name}
      </p>

      <section className="card site-summary" aria-label="Site summary">
        <div className="site-summary-heading">
          <div>
            <h2>
              {isDemo ? <span className="demo-chip">Demo</span> : null} {website.name}
            </h2>
            {isDemo ? (
              <p className="meta">Sample portfolio data — not live monitoring</p>
            ) : null}
            <p className="meta">
              <a href={website.base_url} target="_blank" rel="noreferrer">
                {website.base_url}
              </a>
            </p>
            <p className="meta">
              Monitoring: {website.monitoring_enabled ? "enrolled" : "off"}
              {website.latency_threshold_ms != null
                ? ` · latency budget ${website.latency_threshold_ms} ms`
                : ""}
              {website.failure_threshold_count != null
                ? ` · failure threshold ${website.failure_threshold_count}`
                : ""}
            </p>
          </div>
          {state ? (
            <div className="status-pills" aria-label="Monitoring state">
              <span className={`status-pill ${failing ? "bad" : recovered ? "ok" : ""}`}>
                {state.status}
              </span>
              {state.still_failing ? (
                <span className="status-pill outline bad">still failing</span>
              ) : null}
              {state.recovered ? <span className="status-pill outline ok">recovered</span> : null}
            </div>
          ) : null}
        </div>
        <p className="next-action">
          {failing ? (
            <>
              Next: open recent failed checks below, then run <strong>Analyze failure</strong> on
              Check detail.
            </>
          ) : website.monitoring_enabled ? (
            <>Next: review Overview trends, or open Automation to adjust thresholds and journeys.</>
          ) : (
            <>
              Next: enroll monitoring under <strong>Automation</strong>, or run a check from
              Overview.
            </>
          )}
        </p>
      </section>

      <div className="console-tabs" role="tablist" aria-label="Site health tools">
        {TABS.map((item) => (
          <button
            key={item.id}
            type="button"
            role="tab"
            id={`health-tab-${item.id}`}
            aria-selected={tab === item.id}
            aria-controls={`health-panel-${item.id}`}
            className={tab === item.id ? "console-tab active" : "console-tab"}
            onClick={() => setTab(item.id)}
          >
            {item.label}
          </button>
        ))}
      </div>

      {tab === "overview" ? (
        <div
          className="tab-panel"
          role="tabpanel"
          id="health-panel-overview"
          aria-labelledby="health-tab-overview"
        >
          <section className="card" aria-label="Uptime and latency">
            <WebsiteStatsPanel websiteId={website.id} />
          </section>
          <section className="card" aria-label="Recent checks">
            <h2>Recent checks</h2>
            <p className="hint tight">
              Open a failed check for analysis and screenshot when captured.
            </p>
            <WebsiteChecks websiteId={website.id} disabled={false} />
          </section>
        </div>
      ) : null}

      {tab === "investigate" ? (
        <div
          className="tab-panel"
          role="tabpanel"
          id="health-panel-investigate"
          aria-labelledby="health-tab-investigate"
        >
          <section className="card tool-section" aria-label="Patterns">
            <header className="tool-section-header">
              <h2>Patterns</h2>
              <p className="hint tight">Summarize recurring failures and latency spikes.</p>
            </header>
            <PatternHintsPanel websiteId={website.id} />
          </section>
          <section className="card tool-section" aria-label="Incident draft">
            <header className="tool-section-header">
              <h2>Incident draft</h2>
              <p className="hint tight">Draft incident notes from recent failed checks.</p>
            </header>
            <IncidentDraftPanel websiteId={website.id} />
          </section>
        </div>
      ) : null}

      {tab === "automation" ? (
        <div
          className="tab-panel"
          role="tabpanel"
          id="health-panel-automation"
          aria-labelledby="health-tab-automation"
        >
          <section className="card tool-section" aria-label="Scheduling">
            <header className="tool-section-header">
              <h2>Scheduling</h2>
              <p className="hint tight">
                Enrollment, thresholds, and draft gates. n8n owns the timer — Sentinel stores
                preferences only.
              </p>
            </header>
            <WebsiteMonitoringConfig
              website={website}
              onUpdated={(updated) => {
                setWebsite(updated);
                getMonitoringState(updated.id)
                  .then(setState)
                  .catch(() => setState(null));
              }}
            />
          </section>
          <section className="card tool-section" aria-label="Journeys">
            <header className="tool-section-header">
              <h2>Journeys</h2>
              <p className="hint tight">
                Multi-step browser paths for flows you care about beyond a single page load.
              </p>
            </header>
            <JourneyPanel websiteId={website.id} />
          </section>
          <section className="card tool-section" aria-label="Scenarios">
            <header className="tool-section-header">
              <h2>Scenarios</h2>
              <p className="hint tight">Saved journey templates you can re-run against this site.</p>
            </header>
            <ScenarioPanel websiteId={website.id} />
          </section>
        </div>
      ) : null}
    </div>
  );
}
