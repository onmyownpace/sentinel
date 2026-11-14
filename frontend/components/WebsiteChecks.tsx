"use client";

import { useState } from "react";

import { CheckResult } from "@/components/CheckResult";
import { listWebsiteChecks, runWebsiteCheck, type WebsiteCheck } from "@/lib/checks";
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
  const [history, setHistory] = useState<WebsiteCheck[] | null>(null);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyError, setHistoryError] = useState<string | null>(null);

  async function onRun() {
    setRunning(true);
    setError(null);
    try {
      const result = await runWebsiteCheck(websiteId);
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

  async function loadHistory() {
    setHistoryLoading(true);
    setHistoryError(null);
    try {
      setHistory(await listWebsiteChecks(websiteId));
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

  return (
    <div className="check-panel" aria-busy={running || historyLoading}>
      {confirming ? (
        <div>
          <p className="hint tight">
            Sentinel will open this URL in Chromium on this machine. Run a check only if you are
            allowed to test the site.
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
              {running ? "Checking…" : "Run check"}
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
            {running ? "Checking…" : "Run check"}
          </button>
          <button type="button" disabled={disabled || running} onClick={() => void onToggleHistory()}>
            {historyOpen ? "Hide history" : "Check history"}
          </button>
        </div>
      )}

      {error ? (
        <p className="banner bad" role="alert">
          {error}
        </p>
      ) : null}
      {latest ? <CheckResult check={latest} /> : null}

      {historyOpen ? (
        <div className="check-history">
          {historyLoading ? <p className="hint tight">Loading check history…</p> : null}
          {historyError ? (
            <p className="banner bad" role="alert">
              {historyError}
            </p>
          ) : null}
          {history && history.length === 0 ? <p className="hint tight">No checks yet.</p> : null}
          {history && history.length > 0 ? (
            <ul className="check-history-list">
              {history.map((check) => (
                <li key={check.id}>
                  <CheckResult check={check} />
                </li>
              ))}
            </ul>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
