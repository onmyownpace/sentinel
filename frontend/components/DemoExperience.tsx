"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { CheckResult } from "@/components/CheckResult";
import type { FailureAnalysis } from "@/lib/analysis";
import type { WebsiteCheck } from "@/lib/checks";
import {
  createPublicDemoAnalysis,
  getPublicDemo,
  runPublicProbe,
  type PublicDemoSnapshot,
} from "@/lib/publicDemo";
import { WebsiteApiError } from "@/lib/websites";

export function DemoExperience() {
  const [snapshot, setSnapshot] = useState<PublicDemoSnapshot | null>(null);
  const [analysis, setAnalysis] = useState<FailureAnalysis | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [analyzing, setAnalyzing] = useState(false);
  const [probeUrl, setProbeUrl] = useState("https://example.com");
  const [authorized, setAuthorized] = useState(false);
  const [probing, setProbing] = useState(false);
  const [probeError, setProbeError] = useState<string | null>(null);
  const [probeResult, setProbeResult] = useState<WebsiteCheck | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    getPublicDemo(controller.signal)
      .then((data) => {
        setSnapshot(data);
        setAnalysis(data.analysis);
      })
      .catch((err: unknown) => {
        if (controller.signal.aborted) {
          return;
        }
        setError(err instanceof Error ? err.message : "Could not load the public demo.");
      })
      .finally(() => {
        if (!controller.signal.aborted) {
          setLoading(false);
        }
      });
    return () => controller.abort();
  }, []);

  async function onAnalyze() {
    if (!snapshot?.failed_check_id) {
      return;
    }
    setAnalyzing(true);
    setError(null);
    try {
      const result = await createPublicDemoAnalysis(snapshot.failed_check_id);
      setAnalysis(result);
    } catch (err) {
      setError(
        err instanceof WebsiteApiError ? err.message : "Could not run demo analysis.",
      );
    } finally {
      setAnalyzing(false);
    }
  }

  async function onProbe() {
    setProbing(true);
    setProbeError(null);
    try {
      const result = await runPublicProbe(probeUrl.trim());
      setProbeResult(result);
      setAuthorized(false);
    } catch (err) {
      setProbeResult(null);
      setProbeError(
        err instanceof WebsiteApiError ? err.message : "The lightweight check could not be started.",
      );
    } finally {
      setProbing(false);
    }
  }

  if (loading) {
    return <p className="hint">Loading demo…</p>;
  }

  if (error && !snapshot) {
    return (
      <p className="banner warn" role="alert">
        {error}
      </p>
    );
  }

  if (!snapshot) {
    return (
      <p className="banner warn" role="alert">
        Public demo is not available on this deployment.
      </p>
    );
  }

  const failed = snapshot.checks.find((row) => row.id === snapshot.failed_check_id) ?? null;
  const ok = snapshot.checks.find((row) => row.outcome === "success") ?? null;

  return (
    <div className="demo-experience">
      <section className="card demo-site-card" aria-label="Test a site">
        <h2>Test a site</h2>
        <p className="hint tight">
          Enter any public http(s) URL for a <strong>lightweight HTTP check</strong> — real status
          code and latency, no login, no Chromium. Optional analysis is available on failures.
        </p>
        <label htmlFor="probe-url">
          URL
          <input
            id="probe-url"
            type="url"
            name="probe-url"
            value={probeUrl}
            disabled={probing}
            placeholder="https://example.com"
            spellCheck={false}
            onChange={(event) => setProbeUrl(event.target.value)}
          />
        </label>
        <label className="acknowledge">
          <input
            type="checkbox"
            checked={authorized}
            disabled={probing}
            onChange={(event) => setAuthorized(event.target.checked)}
          />
          I am authorized to test this website.
        </label>
        <div className="actions">
          <button
            type="button"
            className="primary"
            disabled={probing || !authorized || probeUrl.trim().length < 8}
            onClick={() => void onProbe()}
          >
            {probing ? "Checking…" : "Run lightweight check"}
          </button>
        </div>
        {probeError ? (
          <p className="banner bad" role="alert">
            {probeError}
          </p>
        ) : null}
        {probeResult ? <CheckResult check={probeResult} disabled={probing} /> : null}
      </section>

      <section className="card demo-site-card" aria-label="Demo site">
        <div className="site-summary-heading">
          <div>
            <h2>
              <span className="demo-chip">Demo</span> {snapshot.website.name}
            </h2>
            <p className="meta">{snapshot.website.base_url} · sample portfolio data</p>
          </div>
          <div className="status-pills">
            <span className="status-pill bad">1 failure</span>
            <span className="status-pill ok">{snapshot.checks.length} checks</span>
          </div>
        </div>
        <p className="next-action">
          Next: inspect the seeded failure below, then run <strong>Analyze failure</strong> — or use
          the URL form above for a live lightweight check.
        </p>
        <p className="hint tight">
          Prefer the full console?{" "}
          <Link href="/dashboard">Open Dashboard</Link>
          {" · "}
          <Link href={`/websites/${snapshot.website.id}`}>Site health</Link>
        </p>
      </section>

      <section className="card" aria-label="Check history">
        <h2>Seeded check history</h2>
        <ul className="demo-check-list">
          {failed ? (
            <li className="demo-check-row fail">
              <div>
                <span className="bad">HTTP {failed.http_status ?? "—"}</span>
                <strong> Service unavailable</strong>
                <p className="meta">{failed.duration_ms} ms · sample failure</p>
              </div>
              <Link className="button-link" href={`/checks/${failed.id}`}>
                Open check
              </Link>
            </li>
          ) : null}
          {ok ? (
            <li className="demo-check-row">
              <div>
                <span className="ok">HTTP {ok.http_status ?? "—"}</span>
                <strong> Homepage reachable</strong>
                <p className="meta">{ok.duration_ms} ms</p>
              </div>
            </li>
          ) : null}
        </ul>
      </section>

      {failed ? (
        <section className="card demo-analysis-card" aria-label="Failure analysis">
          <h2>AI failure analysis</h2>
          <p className="hint tight">
            Simulated on the public portfolio shell — no paid model call for this sample.
          </p>
          {error ? (
            <p className="banner warn" role="alert">
              {error}
            </p>
          ) : null}
          {!analysis ? (
            <div className="actions">
              <button
                type="button"
                className="primary"
                disabled={analyzing}
                onClick={() => void onAnalyze()}
              >
                {analyzing ? "Analyzing…" : "Analyze failure"}
              </button>
            </div>
          ) : (
            <DemoAnalysisResult analysis={analysis} />
          )}
        </section>
      ) : null}
    </div>
  );
}

function DemoAnalysisResult({ analysis }: { analysis: FailureAnalysis }) {
  return (
    <div className="analysis-result demo-analysis-result">
      <p className="banner warn" role="status">
        Simulated analysis — local heuristics only. This is not output from a live AI model.
      </p>
      <p className="meta">
        Provider: {analysis.provider} · Severity: {analysis.severity} · Model:{" "}
        {analysis.model_name}
      </p>
      <p>{analysis.summary}</p>
      <section>
        <p className="meta">Confirmed observations</p>
        <ul>
          {analysis.confirmed_observations.map((item, index) => (
            <li key={`${index}:${item}`}>{item}</li>
          ))}
        </ul>
      </section>
      <section>
        <p className="meta">Possible causes</p>
        <ul>
          {analysis.possible_causes.map((item, index) => (
            <li key={`${index}:${item.cause}`}>
              {item.cause} · confidence {item.confidence}
              <br />
              <span className="meta">Evidence: {item.evidence}</span>
            </li>
          ))}
        </ul>
      </section>
      <section>
        <p className="meta">Recommended investigation steps</p>
        <ol>
          {analysis.recommended_investigation_steps.map((item, index) => (
            <li key={`${index}:${item}`}>{item}</li>
          ))}
        </ol>
      </section>
      <p className="meta">Limitations: {analysis.limitations}</p>
    </div>
  );
}
