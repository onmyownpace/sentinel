"use client";

import { useEffect, useState } from "react";

import { CheckResult } from "@/components/CheckResult";
import {
  listWebsiteChecks,
  runWebsiteCheck,
  type CheckHistoryWindow,
  type WebsiteCheck,
} from "@/lib/checks";
import { getDeploymentMode } from "@/lib/deployment";
import { runPublicDemoWebsiteCheck } from "@/lib/publicDemo";
import { WebsiteApiError } from "@/lib/websites";

type WebsiteChecksProps = {
  websiteId: string;
  disabled: boolean;
};

export function WebsiteChecks({ websiteId, disabled }: WebsiteChecksProps) {
  const [confirming, setConfirming] = useState(false);
  const [authorized, setAuthorized] = useState(false);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [latest, setLatest] = useState<WebsiteCheck | null>(null);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [historyWindow, setHistoryWindow] = useState<CheckHistoryWindow>("7d");
  const [history, setHistory] = useState<WebsiteCheck[] | null>(null);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyError, setHistoryError] = useState<string | null>(null);
  const [liveBrowser, setLiveBrowser] = useState(true);
  const [publicShell, setPublicShell] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    getDeploymentMode(controller.signal).then((mode) => {
      setLiveBrowser(mode.liveBrowserEnabled);
      setPublicShell(mode.publicShell);
    });
    return () => controller.abort();
  }, []);

  async function onRun() {
    setRunning(true);
    setError(null);
    try {
      const result = liveBrowser
        ? await runWebsiteCheck(websiteId)
        : await runLightweight(websiteId, publicShell);
      setLatest(result);
      setConfirming(false);
      setAuthorized(false);
      if (historyOpen) {
        await loadHistory();
      }
    } catch (caught) {
      setError(caught instanceof WebsiteApiError ? caught.message : "The check could not be started.");
    } finally {
      setRunning(false);
    }
  }

  async function loadHistory(windowName: CheckHistoryWindow = historyWindow) {
    setHistoryLoading(true);
    setHistoryError(null);
    try {
      setHistory(await listWebsiteChecks(websiteId, { window: windowName, limit: 20 }));
    } catch (caught) {
      setHistory(null);
      setHistoryError(
        caught instanceof WebsiteApiError ? caught.message : "The check history could not be loaded.",
      );
    } finally {
      setHistoryLoading(false);
    }
  }

  async function onToggleHistory() {
    const next = !historyOpen;
    setHistoryOpen(next);
    if (next && history === null && !historyLoading) {
      await loadHistory();
    }
  }

  async function onHistoryWindowChange(next: CheckHistoryWindow) {
    setHistoryWindow(next);
    if (historyOpen) {
      await loadHistory(next);
    }
  }

  const runLabel = liveBrowser ? "Run check" : "Run lightweight check";

  return (
    <div className="check-panel" aria-busy={running || historyLoading}>
      {!liveBrowser ? (
        <p className="banner warn" role="status">
          Live browser checks are off in the public shell.{" "}
          <strong>Run lightweight check</strong> performs a real HTTP GET (status, latency, title) —
          not full Chromium automation. Seeded demo history stays available below.
        </p>
      ) : null}
      {confirming ? (
        <div>
          <p className="hint tight">
            {liveBrowser
              ? "Sentinel will open this URL in Chromium on this machine. Run a check only if you are allowed to test the site."
              : "Sentinel will send a lightweight HTTP GET to this site’s public URL and record the status code. Confirm you are allowed to test it."}
          </p>
          <label className="acknowledge">
            <input
              type="checkbox"
              checked={authorized}
              disabled={running || disabled}
              onChange={(event) => setAuthorized(event.target.checked)}
            />
            I am authorized to test this website.
          </label>
          <div className="actions">
            <button
              className="primary"
              type="button"
              disabled={!authorized || running || disabled}
              onClick={() => void onRun()}
            >
              {running ? "Checking…" : runLabel}
            </button>
            <button
              type="button"
              disabled={running}
              onClick={() => {
                setConfirming(false);
                setAuthorized(false);
              }}
            >
              Cancel
            </button>
          </div>
        </div>
      ) : (
        <div className="actions">
          <button type="button" disabled={disabled || running} onClick={() => setConfirming(true)}>
            {running ? "Checking…" : runLabel}
          </button>
          <button type="button" disabled={disabled || running} onClick={() => void onToggleHistory()}>
            {historyOpen
              ? "Hide history"
              : liveBrowser
                ? "Check history"
                : "Check history (includes demo results)"}
          </button>
        </div>
      )}

      {error ? (
        <p className="banner bad" role="alert">
          {error}
        </p>
      ) : null}
      {latest ? <CheckResult check={latest} disabled={disabled || running} /> : null}

      {historyOpen ? (
        <div className="check-history">
          <div className="stats-toolbar">
            <p className="hint tight">
              Capped history (max 20 shown here; API max 50). Window filters by <code>created_at</code>.
            </p>
            <label className="stats-window">
              Window
              <select
                value={historyWindow}
                disabled={disabled || historyLoading}
                onChange={(event) => void onHistoryWindowChange(event.target.value as CheckHistoryWindow)}
              >
                <option value="24h">Last 24 hours</option>
                <option value="7d">Last 7 days</option>
                <option value="all">Recent sample</option>
              </select>
            </label>
          </div>
          {historyLoading ? <p className="hint tight">Loading check history…</p> : null}
          {historyError ? (
            <p className="banner bad" role="alert">
              {historyError}
            </p>
          ) : null}
          {history && history.length === 0 ? (
            <p className="hint tight">No checks in this window.</p>
          ) : null}
          {history && history.length > 0 ? (
            <ul className="check-history-list">
              {history.map((check) => (
                <li key={check.id}>
                  <CheckResult check={check} disabled={disabled || running} />
                </li>
              ))}
            </ul>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

async function runLightweight(websiteId: string, publicShell: boolean): Promise<WebsiteCheck> {
  if (publicShell) {
    try {
      return await runPublicDemoWebsiteCheck(websiteId);
    } catch (error) {
      // Signed-in workspace sites are not on the public demo route — fall through.
      if (!(error instanceof WebsiteApiError) || error.status !== 404) {
        throw error;
      }
    }
  }
  return runWebsiteCheck(websiteId);
}
