/**
 * Browser client for MON-2 monitoring state + AUTO-2 notify intents.
 */

import { resolveApiUrl } from "@/lib/api";
import { WebsiteApiError } from "@/lib/websites";

export type MonitoringStatus = "unknown" | "healthy" | "failing" | "degraded" | "recovered";

export type MonitoringState = {
  website_id: string;
  status: MonitoringStatus;
  recovered: boolean;
  still_failing: boolean;
  latency_breached: boolean;
  latency_threshold_ms: number | null;
  failure_threshold_count: number;
  consecutive_failures: number;
  latest_outcome: string | null;
  latest_duration_ms: number | null;
  latest_http_status: number | null;
  latest_created_at: string | null;
  previous_outcome: string | null;
  notify_on_fail: boolean;
  notify_on_recover: boolean;
  notify_on_latency: boolean;
  should_notify_fail: boolean;
  should_notify_recover: boolean;
  should_notify_latency: boolean;
};

export async function getMonitoringState(
  websiteId: string,
  signal?: AbortSignal,
): Promise<MonitoringState> {
  const apiUrl = resolveApiUrl();
  let response: Response;
  try {
    response = await fetch(`${apiUrl}/api/websites/${websiteId}/monitoring-state`, {
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
  if (!isMonitoringState(body)) {
    throw new WebsiteApiError(
      "The monitoring-state payload was not in the expected shape.",
      response.status,
    );
  }
  return body;
}

function isMonitoringState(value: unknown): value is MonitoringState {
  if (!isRecord(value)) {
    return false;
  }
  return (
    typeof value.website_id === "string" &&
    typeof value.status === "string" &&
    typeof value.recovered === "boolean" &&
    typeof value.still_failing === "boolean" &&
    typeof value.latency_breached === "boolean" &&
    (value.latency_threshold_ms === null || typeof value.latency_threshold_ms === "number") &&
    typeof value.failure_threshold_count === "number" &&
    typeof value.consecutive_failures === "number" &&
    typeof value.notify_on_fail === "boolean" &&
    typeof value.notify_on_recover === "boolean" &&
    typeof value.notify_on_latency === "boolean" &&
    typeof value.should_notify_fail === "boolean" &&
    typeof value.should_notify_recover === "boolean" &&
    typeof value.should_notify_latency === "boolean"
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
