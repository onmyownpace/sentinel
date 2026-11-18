/**
 * Public-shell deployment flags from GET /health (additive fields).
 */

import { resolveApiUrl } from "@/lib/api";

export type DeploymentMode = {
  publicShell: boolean;
  liveBrowserEnabled: boolean;
  analysisProvider: string;
  registrationOpen: boolean;
};

const DEFAULT_MODE: DeploymentMode = {
  publicShell: false,
  liveBrowserEnabled: true,
  analysisProvider: "simulated",
  registrationOpen: true,
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

export async function getDeploymentMode(signal?: AbortSignal): Promise<DeploymentMode> {
  const apiUrl = resolveApiUrl();
  try {
    const response = await fetch(`${apiUrl}/health`, {
      cache: "no-store",
      signal: signal ?? AbortSignal.timeout(8000),
    });
    const body: unknown = await response.json();
    if (!isRecord(body)) {
      return DEFAULT_MODE;
    }
    return {
      publicShell: body.public_shell === true,
      liveBrowserEnabled: body.live_browser_enabled !== false,
      analysisProvider:
        typeof body.analysis_provider === "string" ? body.analysis_provider : "simulated",
      registrationOpen: body.registration_open !== false,
    };
  } catch {
    return DEFAULT_MODE;
  }
}
