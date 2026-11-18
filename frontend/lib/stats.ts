/**
 * Browser client for per-website uptime / latency summaries (MON-1).
 */

import { resolveApiUrl } from "@/lib/api";
import { WebsiteApiError } from "@/lib/websites";

export type StatsWindow = "24h" | "7d" | "all";

export type StatsPoint = {
  created_at: string;
  outcome: string;
  duration_ms: number;
  http_status: number | null;
};

export type WebsiteStats = {
  website_id: string;
  window: StatsWindow;
  sample_limit: number;
  check_count: number;
  success_count: number;
  failure_count: number;
  uptime_percent: number | null;
  avg_duration_ms: number | null;
  p95_duration_ms: number | null;
  points: StatsPoint[];
};

export async function getWebsiteStats(
  websiteId: string,
  window: StatsWindow = "7d",
  signal?: AbortSignal,
): Promise<WebsiteStats> {
  const apiUrl = resolveApiUrl();
  const url = `${apiUrl}/api/websites/${websiteId}/stats?window=${encodeURIComponent(window)}`;
  let response: Response;
  try {
    response = await fetch(url, {
      credentials: "include",
      headers: { Accept: "application/json" },
      signal,
      cache: "no-store",
    });
  } catch (error) {
    throw new WebsiteApiError(
      `The API could not be reached at ${apiUrl}. ${describe(error)}`,
      0,
    );
  }
  if (response.status === 401) {
    throw new WebsiteApiError("Sign in required.", 401);
  }
  if (!response.ok) {
    throw new WebsiteApiError(`The API returned HTTP ${response.status}.`, response.status);
  }
  const body: unknown = await response.json();
  if (!isWebsiteStats(body)) {
    throw new WebsiteApiError("The stats payload was not in the expected shape.", response.status);
  }
  return body;
}

function isWebsiteStats(value: unknown): value is WebsiteStats {
  if (!isRecord(value) || !Array.isArray(value.points)) {
    return false;
  }
  return (
    typeof value.website_id === "string" &&
    (value.window === "24h" || value.window === "7d" || value.window === "all") &&
    typeof value.sample_limit === "number" &&
    typeof value.check_count === "number" &&
    typeof value.success_count === "number" &&
    typeof value.failure_count === "number" &&
    (value.uptime_percent === null || typeof value.uptime_percent === "number") &&
    (value.avg_duration_ms === null || typeof value.avg_duration_ms === "number") &&
    (value.p95_duration_ms === null || typeof value.p95_duration_ms === "number") &&
    value.points.every(isPoint)
  );
}

function isPoint(value: unknown): value is StatsPoint {
  return (
    isRecord(value) &&
    typeof value.created_at === "string" &&
    typeof value.outcome === "string" &&
    typeof value.duration_ms === "number" &&
    (value.http_status === null || typeof value.http_status === "number")
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
