/**
 * Browser client for BROW-2 declarative journeys (separate from one-shot checks).
 */

import { resolveApiUrl } from "@/lib/api";
import { WebsiteApiError } from "@/lib/websites";

export type JourneyStep = {
  op: string;
  url?: string;
  selector?: string;
  value?: string;
};

export type WebsiteJourney = {
  id: string;
  website_id: string;
  name: string;
  steps: JourneyStep[];
  created_at: string;
  updated_at: string;
};

export type JourneyStepResult = {
  index: number;
  op: string;
  ok: boolean;
  detail: string;
};

export type JourneyRun = {
  id: string;
  journey_id: string;
  website_id: string;
  outcome: "success" | "failed";
  duration_ms: number;
  step_results: JourneyStepResult[];
  error_message: string | null;
  final_url: string | null;
  created_at: string;
};

const RUN_TIMEOUT_MS = 60_000;

export async function listJourneys(websiteId: string, signal?: AbortSignal): Promise<WebsiteJourney[]> {
  const response = await request(`/api/websites/${websiteId}/journeys`, { signal });
  const body: unknown = await response.json();
  if (!Array.isArray(body) || !body.every(isJourney)) {
    throw new WebsiteApiError("The journey list was not in the expected shape.", response.status);
  }
  return body;
}

export async function createJourney(
  websiteId: string,
  input: { name: string; steps: JourneyStep[] },
): Promise<WebsiteJourney> {
  const response = await request(`/api/websites/${websiteId}/journeys`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
  const body: unknown = await response.json();
  if (!isJourney(body)) {
    throw new WebsiteApiError("The saved journey was not in the expected shape.", response.status);
  }
  return body;
}

export async function deleteJourney(journeyId: string): Promise<void> {
  await request(`/api/journeys/${journeyId}`, { method: "DELETE" });
}

export async function runJourney(journeyId: string): Promise<JourneyRun> {
  const response = await request(`/api/journeys/${journeyId}/runs`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ authorized: true }),
    signal: AbortSignal.timeout(RUN_TIMEOUT_MS),
  });
  const body: unknown = await response.json();
  if (!isJourneyRun(body)) {
    throw new WebsiteApiError("The journey run was not in the expected shape.", response.status);
  }
  return body;
}

export async function listJourneyRuns(journeyId: string): Promise<JourneyRun[]> {
  const response = await request(`/api/journeys/${journeyId}/runs`);
  const body: unknown = await response.json();
  if (!Array.isArray(body) || !body.every(isJourneyRun)) {
    throw new WebsiteApiError("The journey run list was not in the expected shape.", response.status);
  }
  return body;
}

async function request(path: string, init: RequestInit = {}): Promise<Response> {
  const apiUrl = resolveApiUrl();
  let response: Response;
  try {
    response = await fetch(`${apiUrl}${path}`, {
      ...init,
      credentials: "include",
      headers: { Accept: "application/json", ...init.headers },
    });
  } catch (error) {
    const timedOut = error instanceof DOMException && error.name === "TimeoutError";
    throw new WebsiteApiError(
      timedOut
        ? "The journey did not finish before the page stopped waiting."
        : `The API could not be reached at ${apiUrl}. ${describe(error)}`,
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
    if (isRecord(body) && Array.isArray(body.detail)) {
      for (const item of body.detail) {
        if (isRecord(item) && typeof item.msg === "string") {
          return item.msg.replace(/^Value error, /, "");
        }
      }
    }
  } catch {
    // Fall through.
  }
  return `The API returned HTTP ${response.status}.`;
}

function isJourney(value: unknown): value is WebsiteJourney {
  return (
    isRecord(value) &&
    typeof value.id === "string" &&
    typeof value.website_id === "string" &&
    typeof value.name === "string" &&
    Array.isArray(value.steps) &&
    typeof value.created_at === "string" &&
    typeof value.updated_at === "string"
  );
}

function isJourneyRun(value: unknown): value is JourneyRun {
  return (
    isRecord(value) &&
    typeof value.id === "string" &&
    typeof value.journey_id === "string" &&
    typeof value.website_id === "string" &&
    (value.outcome === "success" || value.outcome === "failed") &&
    typeof value.duration_ms === "number" &&
    Array.isArray(value.step_results) &&
    (value.error_message === null || typeof value.error_message === "string") &&
    (value.final_url === null || typeof value.final_url === "string") &&
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
