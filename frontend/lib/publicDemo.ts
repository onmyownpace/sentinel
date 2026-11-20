/**
 * Anonymous portfolio demo client — no session cookie required.
 *
 * Scoped to the seeded [Demo] site on the API. Non-demo ids return 404.
 */

import { resolveApiUrl } from "@/lib/api";
import type { FailureAnalysis } from "@/lib/analysis";
import type { WebsiteCheck } from "@/lib/checks";
import type { DashboardSnapshot, DashboardWindow } from "@/lib/dashboard";
import { WebsiteApiError, type Website } from "@/lib/websites";

export type PublicDemoSnapshot = {
  website: Website;
  checks: WebsiteCheck[];
  failed_check_id: string | null;
  analysis: FailureAnalysis | null;
};

export async function getPublicDemo(signal?: AbortSignal): Promise<PublicDemoSnapshot> {
  const response = await request("/api/public/demo", { signal });
  const body: unknown = await response.json();
  if (!isPublicDemoSnapshot(body)) {
    throw new WebsiteApiError("The public demo payload was not in the expected shape.", response.status);
  }
  return body;
}

export async function getPublicDemoDashboard(
  signal?: AbortSignal,
  statsWindow: DashboardWindow = "7d",
): Promise<DashboardSnapshot> {
  const response = await request(
    `/api/public/demo/dashboard?stats_window=${encodeURIComponent(statsWindow)}`,
    { signal },
  );
  const body: unknown = await response.json();
  if (!isDashboard(body)) {
    throw new WebsiteApiError(
      "The public demo dashboard was not in the expected shape.",
      response.status,
    );
  }
  return body;
}

export async function getPublicDemoWebsite(
  websiteId: string,
  signal?: AbortSignal,
): Promise<Website> {
  const response = await request(`/api/public/demo/websites/${websiteId}`, { signal });
  const body: unknown = await response.json();
  if (!isWebsite(body)) {
    throw new WebsiteApiError("The demo website was not in the expected shape.", response.status);
  }
  return body;
}

export async function listPublicDemoChecks(
  websiteId: string,
  signal?: AbortSignal,
): Promise<WebsiteCheck[]> {
  const response = await request(`/api/public/demo/websites/${websiteId}/checks`, { signal });
  const body: unknown = await response.json();
  if (!Array.isArray(body) || !body.every(isWebsiteCheck)) {
    throw new WebsiteApiError("The demo check history was not in the expected shape.", response.status);
  }
  return body;
}

export async function getPublicDemoCheck(
  checkId: string,
  signal?: AbortSignal,
): Promise<WebsiteCheck> {
  const response = await request(`/api/public/demo/checks/${checkId}`, { signal });
  const body: unknown = await response.json();
  if (!isWebsiteCheck(body)) {
    throw new WebsiteApiError("The demo check was not in the expected shape.", response.status);
  }
  return body;
}

export async function createPublicDemoAnalysis(checkId: string): Promise<FailureAnalysis> {
  const response = await request(`/api/public/demo/checks/${checkId}/analysis`, {
    method: "POST",
    signal: AbortSignal.timeout(40_000),
  });
  const body: unknown = await response.json();
  if (!isFailureAnalysis(body)) {
    throw new WebsiteApiError("The demo analysis was not in the expected shape.", response.status);
  }
  return body;
}

export async function getPublicDemoAnalysis(checkId: string): Promise<FailureAnalysis | null> {
  const apiUrl = resolveApiUrl();
  let response: Response;
  try {
    response = await fetch(`${apiUrl}/api/public/demo/checks/${checkId}/analysis`, {
      headers: { Accept: "application/json" },
      signal: AbortSignal.timeout(40_000),
      cache: "no-store",
    });
  } catch (error) {
    throw new WebsiteApiError(
      `The API could not be reached at ${apiUrl}. ${describe(error)}`,
      0,
    );
  }
  if (response.status === 404) {
    return null;
  }
  if (!response.ok) {
    throw new WebsiteApiError(await readDetail(response), response.status);
  }
  const body: unknown = await response.json();
  if (!isFailureAnalysis(body)) {
    throw new WebsiteApiError("The demo analysis was not in the expected shape.", response.status);
  }
  return body;
}

async function request(path: string, init: RequestInit = {}): Promise<Response> {
  const apiUrl = resolveApiUrl();
  let response: Response;
  try {
    response = await fetch(`${apiUrl}${path}`, {
      ...init,
      // Public demo does not need cookies; omit credentials intentionally.
      headers: { Accept: "application/json", ...init.headers },
      cache: "no-store",
    });
  } catch (error) {
    throw new WebsiteApiError(
      `The API could not be reached at ${apiUrl}. ${describe(error)}`,
      0,
    );
  }
  if (response.ok) {
    return response;
  }
  throw new WebsiteApiError(await readDetail(response), response.status);
}

async function readDetail(response: Response): Promise<string> {
  try {
    const body: unknown = await response.json();
    if (isRecord(body) && typeof body.detail === "string") {
      return body.detail;
    }
  } catch {
    // Fall through.
  }
  return `The API returned HTTP ${response.status}.`;
}

function isPublicDemoSnapshot(value: unknown): value is PublicDemoSnapshot {
  return (
    isRecord(value) &&
    isWebsite(value.website) &&
    Array.isArray(value.checks) &&
    value.checks.every(isWebsiteCheck) &&
    (value.failed_check_id === null || typeof value.failed_check_id === "string") &&
    (value.analysis === null || isFailureAnalysis(value.analysis))
  );
}

function isDashboard(value: unknown): value is DashboardSnapshot {
  return (
    isRecord(value) &&
    Array.isArray(value.websites) &&
    Array.isArray(value.recent_checks) &&
    Array.isArray(value.website_stats) &&
    isRecord(value.health) &&
    typeof value.stats_window === "string"
  );
}

function isWebsite(value: unknown): value is Website {
  return (
    isRecord(value) &&
    typeof value.id === "string" &&
    typeof value.name === "string" &&
    typeof value.base_url === "string" &&
    typeof value.monitoring_enabled === "boolean" &&
    (value.latency_threshold_ms === null ||
      value.latency_threshold_ms === undefined ||
      typeof value.latency_threshold_ms === "number") &&
    (value.failure_threshold_count === null ||
      value.failure_threshold_count === undefined ||
      typeof value.failure_threshold_count === "number") &&
    (value.notify_on_fail === undefined || typeof value.notify_on_fail === "boolean") &&
    (value.notify_on_recover === undefined || typeof value.notify_on_recover === "boolean") &&
    (value.notify_on_latency === undefined || typeof value.notify_on_latency === "boolean") &&
    typeof value.created_at === "string" &&
    typeof value.updated_at === "string"
  );
}

function isWebsiteCheck(value: unknown): value is WebsiteCheck {
  return (
    isRecord(value) &&
    typeof value.id === "string" &&
    typeof value.website_id === "string" &&
    (value.outcome === "success" || value.outcome === "failed") &&
    (value.http_status === null || typeof value.http_status === "number") &&
    typeof value.duration_ms === "number" &&
    Array.isArray(value.console_errors) &&
    Array.isArray(value.failed_requests) &&
    (value.error_message === null || typeof value.error_message === "string") &&
    typeof value.created_at === "string"
  );
}

function isFailureAnalysis(value: unknown): value is FailureAnalysis {
  return (
    isRecord(value) &&
    typeof value.id === "string" &&
    typeof value.check_id === "string" &&
    typeof value.summary === "string" &&
    typeof value.severity === "string" &&
    Array.isArray(value.confirmed_observations) &&
    Array.isArray(value.possible_causes) &&
    Array.isArray(value.recommended_investigation_steps) &&
    typeof value.limitations === "string" &&
    typeof value.model_name === "string" &&
    (value.provider === "simulated" || value.provider === "openai") &&
    typeof value.created_at === "string"
  );
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function describe(error: unknown): string {
  if (error instanceof Error) {
    return error.message;
  }
  return "Unknown error";
}
