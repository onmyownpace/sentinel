"use client";

import { useCallback, useEffect, useState, type FormEvent } from "react";

import { listJourneys, type WebsiteJourney } from "@/lib/journeys";
import { getDeploymentMode } from "@/lib/deployment";
import {
  createScenario,
  deleteScenario,
  listScenarioRuns,
  listScenarios,
  runScenario,
  type ScenarioRun,
  type WebsiteScenario,
} from "@/lib/scenarios";
import { WebsiteApiError } from "@/lib/websites";

type ScenarioPanelProps = {
  websiteId: string;
  disabled?: boolean;
};

export function ScenarioPanel({ websiteId, disabled = false }: ScenarioPanelProps) {
  const [scenarios, setScenarios] = useState<WebsiteScenario[]>([]);
  const [journeys, setJourneys] = useState<WebsiteJourney[]>([]);
  const [name, setName] = useState("Login smoke (library)");
  const [description, setDescription] = useState("");
  const [journeyId, setJourneyId] = useState("");
  const [scheduleEligible, setScheduleEligible] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [latestRun, setLatestRun] = useState<ScenarioRun | null>(null);
  const [history, setHistory] = useState<ScenarioRun[] | null>(null);
  const [liveBrowser, setLiveBrowser] = useState(true);

  const reload = useCallback(
    async (signal?: AbortSignal) => {
      const [scenarioRows, journeyRows] = await Promise.all([
        listScenarios(websiteId, signal),
        listJourneys(websiteId, signal),
      ]);
      setScenarios(scenarioRows);
      setJourneys(journeyRows);
      setJourneyId((current) => {
        if (current && journeyRows.some((row) => row.id === current)) {
          return current;
        }
        return journeyRows[0]?.id ?? "";
      });
    },
    [websiteId],
  );

  useEffect(() => {
    const controller = new AbortController();
    getDeploymentMode(controller.signal).then((mode) => setLiveBrowser(mode.liveBrowserEnabled));
    reload(controller.signal).catch((err: unknown) => {
      if (err instanceof DOMException && err.name === "AbortError") {
        return;
      }
      setError(err instanceof WebsiteApiError ? err.message : "Scenarios could not be loaded.");
    });
    return () => controller.abort();
  }, [reload]);

  async function onCreate(event: FormEvent) {
    event.preventDefault();
    if (!journeyId) {
      setError("Save a journey first, then attach it as a scenario.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await createScenario(websiteId, {
        name,
        journey_id: journeyId,
        description: description.trim() || null,
        schedule_eligible: scheduleEligible,
      });
      setDescription("");
      setScheduleEligible(false);
      await reload();
    } catch (err) {
      setError(err instanceof WebsiteApiError ? err.message : "Scenario could not be saved.");
    } finally {
      setBusy(false);
    }
  }

  async function onRun(scenarioId: string) {
    if (!liveBrowser) {
      setError("Live scenarios are disabled in the public shell. Run Sentinel locally for Playwright.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const run = await runScenario(scenarioId);
      setLatestRun(run);
      setHistory(await listScenarioRuns(scenarioId));
    } catch (err) {
      setError(err instanceof WebsiteApiError ? err.message : "Scenario could not be run.");
    } finally {
      setBusy(false);
    }
  }

  async function onDelete(scenarioId: string) {
    setBusy(true);
    setError(null);
    try {
      await deleteScenario(scenarioId);
      if (latestRun?.scenario_id === scenarioId) {
        setLatestRun(null);
        setHistory(null);
      }
      await reload();
    } catch (err) {
      setError(err instanceof WebsiteApiError ? err.message : "Scenario could not be deleted.");
    } finally {
      setBusy(false);
    }
  }

  function journeyLabel(id: string): string {
    return journeys.find((row) => row.id === id)?.name ?? id.slice(0, 8);
  }

  return (
    <div className="journey-panel scenario-panel">
      <h3>Scenario library</h3>
      <p className="hint tight">
        Named reusable entries that wrap an existing <strong>journey</strong>. Run on demand.{" "}
        <code>schedule_eligible</code> is stored for later enrollment — not wired to n8n yet.
      </p>

      <form className="journey-form" onSubmit={onCreate}>
        <label>
          Scenario name
          <input
            value={name}
            disabled={disabled || busy}
            onChange={(event) => setName(event.target.value)}
            maxLength={120}
            required
          />
        </label>
        <label>
          Description (optional)
          <input
            value={description}
            disabled={disabled || busy}
            onChange={(event) => setDescription(event.target.value)}
            maxLength={500}
          />
        </label>
        <label>
          Journey
          <select
            value={journeyId}
            disabled={disabled || busy || journeys.length === 0}
            onChange={(event) => setJourneyId(event.target.value)}
            required
          >
            {journeys.length === 0 ? (
              <option value="">No journeys yet</option>
            ) : (
              journeys.map((journey) => (
                <option key={journey.id} value={journey.id}>
                  {journey.name} ({journey.steps.length} steps)
                </option>
              ))
            )}
          </select>
        </label>
        <label className="checkbox-row">
          <input
            type="checkbox"
            checked={scheduleEligible}
            disabled={disabled || busy}
            onChange={(event) => setScheduleEligible(event.target.checked)}
          />
          Mark schedule-eligible (enrollment later)
        </label>
        <div className="actions">
          <button className="primary" type="submit" disabled={disabled || busy || !journeyId}>
            {busy ? "Working…" : "Save scenario"}
          </button>
        </div>
      </form>

      {error ? (
        <p className="field-error" role="alert">
          {error}
        </p>
      ) : null}

      {scenarios.length === 0 ? (
        <p className="hint tight">No scenarios yet. Create a journey, then add it to the library.</p>
      ) : (
        <ul className="journey-list">
          {scenarios.map((scenario) => (
            <li key={scenario.id}>
              <div>
                <strong>{scenario.name}</strong>
                <p className="meta">
                  Journey: {journeyLabel(scenario.journey_id)}
                  {scenario.schedule_eligible ? " · schedule-eligible" : ""}
                </p>
                {scenario.description ? <p className="meta">{scenario.description}</p> : null}
              </div>
              <div className="actions">
                <button
                  type="button"
                  disabled={disabled || busy || !liveBrowser}
                  onClick={() => void onRun(scenario.id)}
                  title={!liveBrowser ? "Disabled in public shell" : undefined}
                >
                  Run
                </button>
                <button
                  type="button"
                  disabled={disabled || busy}
                  onClick={() => void onDelete(scenario.id)}
                >
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
            Latest scenario run: {latestRun.outcome} · {latestRun.duration_ms} ms
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
        <p className="meta">{history.length} runs stored for the last scenario you ran.</p>
      ) : null}
    </div>
  );
}
