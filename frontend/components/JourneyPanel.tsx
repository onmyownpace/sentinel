"use client";

import { useCallback, useEffect, useState, type FormEvent } from "react";

import {
  createJourney,
  deleteJourney,
  listJourneyRuns,
  listJourneys,
  runJourney,
  type JourneyRun,
  type WebsiteJourney,
} from "@/lib/journeys";
import { getDeploymentMode } from "@/lib/deployment";
import { WebsiteApiError } from "@/lib/websites";

const DEFAULT_STEPS = `[
  { "op": "navigate", "url": "/" },
  { "op": "assert_url_contains", "value": "/" }
]`;

type JourneyPanelProps = {
  websiteId: string;
  disabled?: boolean;
};

export function JourneyPanel({ websiteId, disabled = false }: JourneyPanelProps) {
  const [journeys, setJourneys] = useState<WebsiteJourney[]>([]);
  const [name, setName] = useState("Smoke path");
  const [stepsJson, setStepsJson] = useState(DEFAULT_STEPS);
  const [error, setError] = useState<string | null>(null);
  const [liveBrowser, setLiveBrowser] = useState(true);
  const [busy, setBusy] = useState(false);
  const [latestRun, setLatestRun] = useState<JourneyRun | null>(null);
  const [history, setHistory] = useState<JourneyRun[] | null>(null);

  const reload = useCallback(async (signal?: AbortSignal) => {
    const rows = await listJourneys(websiteId, signal);
    setJourneys(rows);
  }, [websiteId]);

  useEffect(() => {
    const controller = new AbortController();
    getDeploymentMode(controller.signal).then((mode) => setLiveBrowser(mode.liveBrowserEnabled));
    reload(controller.signal).catch((err: unknown) => {
      if (err instanceof DOMException && err.name === "AbortError") {
        return;
      }
      setError(err instanceof WebsiteApiError ? err.message : "Journeys could not be loaded.");
    });
    return () => controller.abort();
  }, [reload]);

  async function onCreate(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const parsed: unknown = JSON.parse(stepsJson);
      if (!Array.isArray(parsed)) {
        setError("Steps must be a JSON array.");
        return;
      }
      await createJourney(websiteId, { name, steps: parsed as { op: string }[] });
      setStepsJson(DEFAULT_STEPS);
      await reload();
    } catch (err) {
      if (err instanceof SyntaxError) {
        setError("Steps JSON is invalid.");
      } else {
        setError(err instanceof WebsiteApiError ? err.message : "Journey could not be saved.");
      }
    } finally {
      setBusy(false);
    }
  }

  async function onRun(journeyId: string) {
    if (!liveBrowser) {
      setError("Live journeys are disabled in the public shell. Run Sentinel locally for Playwright.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const run = await runJourney(journeyId);
      setLatestRun(run);
      setHistory(await listJourneyRuns(journeyId));
    } catch (err) {
      setError(err instanceof WebsiteApiError ? err.message : "Journey could not be run.");
    } finally {
      setBusy(false);
    }
  }

  async function onDelete(journeyId: string) {
    setBusy(true);
    setError(null);
    try {
      await deleteJourney(journeyId);
      if (latestRun?.journey_id === journeyId) {
        setLatestRun(null);
        setHistory(null);
      }
      await reload();
    } catch (err) {
      setError(err instanceof WebsiteApiError ? err.message : "Journey could not be deleted.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="journey-panel">
      <h3>Journeys</h3>
      <p className="hint tight">
        Declarative mini-journeys (navigate → fill/click → assert), stored separately from one-shot
        checks. SSRF still applies. Not a full browser recorder.
      </p>

      <form className="journey-form" onSubmit={onCreate}>
        <label>
          Name
          <input
            value={name}
            disabled={disabled || busy}
            onChange={(event) => setName(event.target.value)}
            maxLength={120}
            required
          />
        </label>
        <label>
          Steps (JSON)
          <textarea
            value={stepsJson}
            disabled={disabled || busy}
            onChange={(event) => setStepsJson(event.target.value)}
            rows={8}
            spellCheck={false}
          />
        </label>
        <div className="actions">
          <button className="primary" type="submit" disabled={disabled || busy}>
            {busy ? "Working…" : "Save journey"}
          </button>
        </div>
      </form>

      {error ? (
        <p className="field-error" role="alert">
          {error}
        </p>
      ) : null}

      {journeys.length === 0 ? (
        <p className="hint tight">No journeys yet.</p>
      ) : (
        <ul className="journey-list">
          {journeys.map((journey) => (
            <li key={journey.id}>
              <div>
                <strong>{journey.name}</strong>
                <p className="meta">{journey.steps.length} steps</p>
              </div>
              <div className="actions">
                <button
                  type="button"
                  disabled={disabled || busy || !liveBrowser}
                  onClick={() => void onRun(journey.id)}
                  title={!liveBrowser ? "Disabled in public shell" : undefined}
                >
                  Run
                </button>
                <button type="button" disabled={disabled || busy} onClick={() => void onDelete(journey.id)}>
                  Delete
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}

      {latestRun ? (
        <div className="journey-run">
          <p className={latestRun.outcome === "success" ? "ok" : "bad"}>
            Latest run: {latestRun.outcome} · {latestRun.duration_ms} ms
          </p>
          {latestRun.error_message ? <p className="meta">{latestRun.error_message}</p> : null}
          <ul>
            {latestRun.step_results.map((step) => (
              <li key={`${step.index}-${step.op}`}>
                <span className={step.ok ? "ok" : "bad"}>
                  #{step.index + 1} {step.op}
                </span>
                {" · "}
                {step.detail}
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {history && history.length > 1 ? (
        <p className="meta">{history.length} runs stored for the last journey you ran.</p>
      ) : null}
    </div>
  );
}
