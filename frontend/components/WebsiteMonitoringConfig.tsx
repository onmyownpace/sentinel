"use client";

import { useState } from "react";

import { WebsiteNotificationRules } from "@/components/WebsiteNotificationRules";
import { WebsiteThresholds } from "@/components/WebsiteThresholds";
import {
  setWebsiteMonitoring,
  WebsiteApiError,
  type Website,
} from "@/lib/websites";

type WebsiteMonitoringConfigProps = {
  website: Website;
  disabled?: boolean;
  onUpdated: (website: Website) => void;
};

/**
 * DASH-3 consolidated config surface: enrollment, thresholds, notification rules.
 * Sentinel stores preferences; n8n owns the timer/workflow.
 */
export function WebsiteMonitoringConfig({
  website,
  disabled = false,
  onUpdated,
}: WebsiteMonitoringConfigProps) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onToggleEnrollment(enabled: boolean) {
    setBusy(true);
    setError(null);
    try {
      const updated = await setWebsiteMonitoring(website.id, enabled);
      onUpdated(updated);
    } catch (err) {
      setError(
        err instanceof WebsiteApiError
          ? err.message
          : "Scheduled monitoring enrollment could not be updated.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="monitoring-config" aria-label="Monitoring configuration">
      <h3>Monitoring configuration</h3>
      <p className="hint tight">
        Edit enrollment, thresholds, and draft gates here. Sentinel stores these preferences.{" "}
        <strong>n8n owns the timer</strong> — nothing runs on a schedule until you activate{" "}
        <code>scheduled-website-checks</code>, set <code>SCHEDULE_CHECK_TOKEN</code>, and leave
        enrollment on for sites you are allowed to test.
      </p>

      <div className="monitoring-config-block">
        <h4>Enrollment</h4>
        <label className="acknowledge monitoring-toggle">
          <input
            type="checkbox"
            checked={website.monitoring_enabled}
            disabled={disabled || busy}
            onChange={(event) => void onToggleEnrollment(event.target.checked)}
          />
          Include in scheduled monitoring
        </label>
        <p className="meta">
          Status: {website.monitoring_enabled ? "enrolled" : "off"}
          {busy ? " · saving…" : ""}
        </p>
        {error ? (
          <p className="field-error" role="alert">
            {error}
          </p>
        ) : null}
      </div>

      <div className="monitoring-config-block">
        <WebsiteThresholds website={website} disabled={disabled || busy} onUpdated={onUpdated} />
      </div>

      <div className="monitoring-config-block">
        <WebsiteNotificationRules
          website={website}
          disabled={disabled || busy}
          onUpdated={onUpdated}
        />
      </div>
    </section>
  );
}
