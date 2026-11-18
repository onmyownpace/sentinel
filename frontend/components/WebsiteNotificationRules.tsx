"use client";

import { useEffect, useState, type FormEvent } from "react";

import {
  setWebsiteNotificationRules,
  WebsiteApiError,
  type Website,
} from "@/lib/websites";

type WebsiteNotificationRulesProps = {
  website: Website;
  disabled: boolean;
  onUpdated: (website: Website) => void;
};

export function WebsiteNotificationRules({
  website,
  disabled,
  onUpdated,
}: WebsiteNotificationRulesProps) {
  const [onFail, setOnFail] = useState(website.notify_on_fail);
  const [onRecover, setOnRecover] = useState(website.notify_on_recover);
  const [onLatency, setOnLatency] = useState(website.notify_on_latency);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setOnFail(website.notify_on_fail);
    setOnRecover(website.notify_on_recover);
    setOnLatency(website.notify_on_latency);
  }, [website.notify_on_fail, website.notify_on_recover, website.notify_on_latency]);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const updated = await setWebsiteNotificationRules(website.id, {
        notify_on_fail: onFail,
        notify_on_recover: onRecover,
        notify_on_latency: onLatency,
      });
      onUpdated(updated);
    } catch (err) {
      setError(
        err instanceof WebsiteApiError ? err.message : "Notification rules could not be saved.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="threshold-panel notify-rules-panel">
      <h4>Notification rules</h4>
      <p className="hint tight">
        Gates which drafts the scheduled n8n workflow may POST to your free webhook (Slack /
        Discord / webhook.site). Defaults are on. No paid email. n8n still owns delivery timing.
      </p>
      <form className="notify-rules-form" onSubmit={onSubmit}>
        <label className="acknowledge">
          <input
            type="checkbox"
            checked={onFail}
            disabled={disabled || busy}
            onChange={(event) => setOnFail(event.target.checked)}
          />
          On fail (consecutive failures ≥ threshold)
        </label>
        <label className="acknowledge">
          <input
            type="checkbox"
            checked={onRecover}
            disabled={disabled || busy}
            onChange={(event) => setOnRecover(event.target.checked)}
          />
          On recover (failure → success)
        </label>
        <label className="acknowledge">
          <input
            type="checkbox"
            checked={onLatency}
            disabled={disabled || busy}
            onChange={(event) => setOnLatency(event.target.checked)}
          />
          On latency over threshold
        </label>
        <div className="actions">
          <button type="submit" disabled={disabled || busy}>
            {busy ? "Saving…" : "Save notification rules"}
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
