"use client";

import { useEffect, useState, type FormEvent } from "react";

import { getMonitoringState, type MonitoringState } from "@/lib/monitoring";
import {
  setWebsiteThresholds,
  WebsiteApiError,
  type Website,
} from "@/lib/websites";

type WebsiteThresholdsProps = {
  website: Website;
  disabled: boolean;
  onUpdated: (website: Website) => void;
};

export function WebsiteThresholds({ website, disabled, onUpdated }: WebsiteThresholdsProps) {
  const [latency, setLatency] = useState(website.latency_threshold_ms?.toString() ?? "");
  const [failures, setFailures] = useState(website.failure_threshold_count?.toString() ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [state, setState] = useState<MonitoringState | null>(null);

  useEffect(() => {
    setLatency(website.latency_threshold_ms?.toString() ?? "");
    setFailures(website.failure_threshold_count?.toString() ?? "");
  }, [website.latency_threshold_ms, website.failure_threshold_count]);

  useEffect(() => {
    const controller = new AbortController();
    getMonitoringState(website.id, controller.signal)
      .then(setState)
      .catch(() => setState(null));
    return () => controller.abort();
  }, [website.id, website.latency_threshold_ms, website.failure_threshold_count]);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const latencyValue = parseOptionalInt(latency);
      const failureValue = parseOptionalInt(failures);
      if (latencyValue === undefined || failureValue === undefined) {
        setError("Thresholds must be whole numbers, or left blank.");
        return;
      }
      const updated = await setWebsiteThresholds(website.id, {
        latency_threshold_ms: latencyValue,
        failure_threshold_count: failureValue,
      });
      onUpdated(updated);
      setState(await getMonitoringState(website.id));
    } catch (err) {
      setError(err instanceof WebsiteApiError ? err.message : "Thresholds could not be saved.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="threshold-panel">
      <h4>Thresholds & recovery</h4>
      <p className="hint tight">
        Optional limits for n8n branching. Empty latency means ignore duration. Empty failure count
        means one failed check is enough for <code>still_failing</code>. Sentinel stores the values;
        n8n still owns the timer.
      </p>
      {state ? (
        <p className="meta">
          State:{" "}
          <span className={state.still_failing ? "bad" : state.recovered ? "ok" : ""}>
            {state.status}
          </span>
          {state.still_failing ? " · still failing" : ""}
          {state.recovered ? " · recovered" : ""}
          {state.latency_breached ? " · latency breached" : ""}
          {` · consecutive failures ${state.consecutive_failures}`}
          {state.should_notify_fail ? " · notify fail" : ""}
          {state.should_notify_latency ? " · notify latency" : ""}
          {state.should_notify_recover ? " · notify recover" : ""}
        </p>
      ) : null}
      <form className="threshold-form" onSubmit={onSubmit}>
        <label>
          Latency max (ms)
          <input
            type="number"
            min={1}
            max={120000}
            value={latency}
            disabled={disabled || busy}
            onChange={(event) => setLatency(event.target.value)}
            placeholder="unset"
          />
        </label>
        <label>
          Consecutive failures
          <input
            type="number"
            min={1}
            max={20}
            value={failures}
            disabled={disabled || busy}
            onChange={(event) => setFailures(event.target.value)}
            placeholder="1"
          />
        </label>
        <div className="actions">
          <button type="submit" disabled={disabled || busy}>
            {busy ? "Saving…" : "Save thresholds"}
          </button>
        </div>
      </form>
      {error ? (
        <p className="field-error" role="alert">
          {error}
        </p>
      ) : null}
    </div>
  );
}

function parseOptionalInt(value: string): number | null | undefined {
  const trimmed = value.trim();
  if (!trimmed) {
    return null;
  }
  const parsed = Number(trimmed);
  if (!Number.isInteger(parsed)) {
    return undefined;
  }
  return parsed;
}
