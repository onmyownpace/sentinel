"use client";

import { useEffect, useState } from "react";

import { getDeploymentMode, type DeploymentMode } from "@/lib/deployment";

/**
 * Honest portfolio banner when PUBLIC_SHELL is on: no live Chromium here.
 */
export function PublicShellBanner() {
  const [mode, setMode] = useState<DeploymentMode | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    getDeploymentMode(controller.signal).then(setMode);
    return () => controller.abort();
  }, []);

  if (!mode?.publicShell) {
    return null;
  }

  return (
    <aside className="public-shell-banner" role="status" aria-label="Public shell notice">
      <p>
        <strong>Public shell (demo).</strong> This deployment runs on free-tier hosting without
        live Playwright/Chromium. Check history labelled{" "}
        <em>Demo result — not a live browser check</em> is sample data for exploring the
        dashboard. Live browser checks, journeys, and n8n schedules need a{" "}
        <strong>local</strong> or full-capacity deployment. AI here is{" "}
        <code>{mode.analysisProvider}</code> only (no external AI API).
      </p>
    </aside>
  );
}
