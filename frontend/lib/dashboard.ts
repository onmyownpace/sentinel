/**
 * Browser client for the product dashboard summary.
 */

import { resolveApiUrl } from "@/lib/api";
import { WebsiteApiError } from "@/lib/websites";

export type DashboardWebsite = {
  id: string;
  name: string;
  base_url: string;
  monitoring_enabled: boolean;
  created_at: string;
  updated_at: string;
};

export type DashboardCheck = {
  id: string;
  website_id: string;
  website_name: string;
  outcome: string;
  http_status: number | null;
  duration_ms: number;
  error_message: string | null;
  created_at: string;
};

export type DashboardWebsiteStats = {
  website_id: string;
  window: string;
  check_count: number;
  success_count: number;
  failure_count: number;
  uptime_percent: number | null;
  avg_duration_ms: number | null;
  p95_duration_ms: number | null;
};

export type DashboardHealth = {
  website_count: number;
  monitored_count: number;
  sites_with_checks: number;
  sites_with_failures: number;
  avg_uptime_percent: number | null;
  recent_failure_count: number;
};

export type DashboardSnapshot = {
  websites: DashboardWebsite[];
  recent_checks: DashboardCheck[];
  website_stats: DashboardWebsiteStats[];
  stats_window: string;
  history_window: string;
  recent_check_limit: number;
  health: DashboardHealth;
};

export type DashboardWindow = "24h" | "7d" | "all";

export async function getDashboard(
  signal?: AbortSignal,
  statsWindow: DashboardWindow = "7d",
): Promise<DashboardSnapshot> {
  const apiUrl = resolveApiUrl();
  let response: Response;
  try {
    response = await fetch(
      `${apiUrl}/api/dashboard?stats_window=${encodeURIComponent(statsWindow)}`,
      {
        credentials: "include",
        headers: { Accept: "application/json" },
        signal,
        cache: "no-store",
      },
    );
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
  if (!isDashboard(body)) {
    throw new WebsiteApiError("The dashboard payload was not in the expected shape.", response.status);
  }
  return body;
}

function isDashboard(value: unknown): value is DashboardSnapshot {
  if (
    !isRecord(value) ||
    !Array.isArray(value.websites) ||
    !Array.isArray(value.recent_checks) ||
    !Array.isArray(value.website_stats) ||
    typeof value.stats_window !== "string" ||
    typeof value.history_window !== "string" ||
    typeof value.recent_check_limit !== "number" ||
    !isHealth(value.health)
  ) {
    return false;
  }
  return (
    value.websites.every(isWebsite) &&
    value.recent_checks.every(isCheck) &&
    value.website_stats.every(isStats)
  );
}

function isHealth(value: unknown): value is DashboardHealth {
  return (
    isRecord(value) &&
    typeof value.website_count === "number" &&
    typeof value.monitored_count === "number" &&
    typeof value.sites_with_checks === "number" &&
    typeof value.sites_with_failures === "number" &&
    (value.avg_uptime_percent === null || typeof value.avg_uptime_percent === "number") &&
    typeof value.recent_failure_count === "number"
  );
}

function isWebsite(value: unknown): value is DashboardWebsite {
  return (
    isRecord(value) &&
    typeof value.id === "string" &&
    typeof value.name === "string" &&
    typeof value.base_url === "string" &&
    typeof value.monitoring_enabled === "boolean" &&
    typeof value.created_at === "string" &&
    typeof value.updated_at === "string"
  );
}

function isCheck(value: unknown): value is DashboardCheck {
  return (
    isRecord(value) &&
    typeof value.id === "string" &&
    typeof value.website_id === "string" &&
    typeof value.website_name === "string" &&
    typeof value.outcome === "string" &&
    (value.http_status === null || typeof value.http_status === "number") &&
    typeof value.duration_ms === "number" &&
    (value.error_message === null || typeof value.error_message === "string") &&
    typeof value.created_at === "string"
  );
}

function isStats(value: unknown): value is DashboardWebsiteStats {
  return (
    isRecord(value) &&
    typeof value.website_id === "string" &&
    typeof value.window === "string" &&
    typeof value.check_count === "number" &&
    typeof value.success_count === "number" &&
    typeof value.failure_count === "number" &&
    (value.uptime_percent === null || typeof value.uptime_percent === "number") &&
    (value.avg_duration_ms === null || typeof value.avg_duration_ms === "number") &&
    (value.p95_duration_ms === null || typeof value.p95_duration_ms === "number")
  );
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function describe(error: unknown): string {
  if (error instanceof Error) {
    if (error.cause instanceof Error && error.cause.message) {
      return `${error.message}: ${error.cause.message}`;
    }
    return error.message;
  }
  return "Unknown error";
}
