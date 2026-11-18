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

export function SiteHealthPanel({ websiteId }: SiteHealthPanelProps) {
  const router = useRouter();
  const [website, setWebsite] = useState<Website | null>(null);
  const [state, setState] = useState<MonitoringState | null>(null);
  const [error, setError] = useState<string | null>(null);

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
        <p className="banner warn">{error}</p>
        <p>
          <Link href="/dashboard">Back to dashboard</Link>
        </p>
      </div>
    );
  }

  if (!website) {
    return <p className="hint">Loading site health…</p>;
  }

  return (
    <div className="registry site-health">
      <p className="crumb">
        <Link href="/dashboard">Dashboard</Link>
        {" · "}
        <Link href="/websites">Websites</Link>
        {" · "}
        {website.name}
      </p>

      <section className="card" aria-label="Site summary">
        <h2>{website.name}</h2>
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
        {state ? (
          <p className="meta">
            State:{" "}
            <span
              className={
                state.still_failing ? "bad" : state.recovered || state.status === "healthy" ? "ok" : ""
              }
            >
              {state.status}
            </span>
            {state.still_failing ? " · still failing" : ""}
            {state.recovered ? " · recovered" : ""}
          </p>
        ) : null}
        <p className="hint tight">
          Use <strong>Monitoring configuration</strong> below for enrollment, thresholds, and draft
          gates. n8n still owns the schedule timer.
        </p>
      </section>

      <section className="card" aria-label="Monitoring configuration">
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

      <section className="card" aria-label="Uptime and latency">
        <WebsiteStatsPanel websiteId={website.id} />
      </section>

      <section className="card" aria-label="Historical pattern hints">
        <PatternHintsPanel websiteId={website.id} />
      </section>

      <section className="card" aria-label="Incident summary draft">
        <IncidentDraftPanel websiteId={website.id} />
      </section>

      <section className="card" aria-label="Journeys">
        <JourneyPanel websiteId={website.id} />
      </section>

      <section className="card" aria-label="Scenario library">
        <ScenarioPanel websiteId={website.id} />
      </section>

      <section className="card" aria-label="Checks">
        <h2>Checks</h2>
        <p className="hint tight">
          Open a stored check for full detail, AI analysis, and screenshot when captured.
        </p>
        <WebsiteChecks websiteId={website.id} disabled={false} />
      </section>
    </div>
  );
}
