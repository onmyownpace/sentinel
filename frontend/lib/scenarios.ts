/**
 * Browser client for BROW-3 scenario library (named wrappers around BROW-2 journeys).
 */

import { resolveApiUrl } from "@/lib/api";
import { WebsiteApiError } from "@/lib/websites";

export type WebsiteScenario = {
  id: string;
  website_id: string;
  journey_id: string;
  name: string;
  description: string | null;
  schedule_eligible: boolean;
  created_at: string;
  updated_at: string;
};

export type ScenarioStepResult = {
  index: number;
  op: string;
  ok: boolean;
  detail: string;
};

export type ScenarioRun = {
  id: string;
  scenario_id: string;
  website_id: string;
  journey_id: string;
  outcome: "success" | "failed";
  duration_ms: number;
  step_results: ScenarioStepResult[];
  error_message: string | null;
  final_url: string | null;
  created_at: string;
};

const RUN_TIMEOUT_MS = 60_000;

export async function listScenarios(
  websiteId: string,
  signal?: AbortSignal,
): Promise<WebsiteScenario[]> {
  const response = await request(`/api/websites/${websiteId}/scenarios`, { signal });
  const body: unknown = await response.json();
  if (!Array.isArray(body) || !body.every(isScenario)) {
    throw new WebsiteApiError("The scenario list was not in the expected shape.", response.status);
  }
  return body;
}

export async function createScenario(
  websiteId: string,
  input: {
    name: string;
    journey_id: string;
    description?: string | null;
    schedule_eligible?: boolean;
  },
): Promise<WebsiteScenario> {
  const response = await request(`/api/websites/${websiteId}/scenarios`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      name: input.name,
      journey_id: input.journey_id,
      description: input.description ?? null,
      schedule_eligible: input.schedule_eligible ?? false,
    }),
  });
  const body: unknown = await response.json();
  if (!isScenario(body)) {
    throw new WebsiteApiError("The saved scenario was not in the expected shape.", response.status);
  }
  return body;
}

export async function deleteScenario(scenarioId: string): Promise<void> {
  await request(`/api/scenarios/${scenarioId}`, { method: "DELETE" });
}

export async function runScenario(scenarioId: string): Promise<ScenarioRun> {
  const response = await request(`/api/scenarios/${scenarioId}/runs`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ authorized: true }),
    signal: AbortSignal.timeout(RUN_TIMEOUT_MS),
  });
  const body: unknown = await response.json();
  if (!isScenarioRun(body)) {
    throw new WebsiteApiError("The scenario run was not in the expected shape.", response.status);
  }
  return body;
}

export async function listScenarioRuns(scenarioId: string): Promise<ScenarioRun[]> {
  const response = await request(`/api/scenarios/${scenarioId}/runs`);
  const body: unknown = await response.json();
  if (!Array.isArray(body) || !body.every(isScenarioRun)) {
    throw new WebsiteApiError(
      "The scenario run list was not in the expected shape.",
      response.status,
    );
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
        ? "The scenario did not finish before the page stopped waiting."
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

function isScenario(value: unknown): value is WebsiteScenario {
  return (
    isRecord(value) &&
    typeof value.id === "string" &&
    typeof value.website_id === "string" &&
    typeof value.journey_id === "string" &&
    typeof value.name === "string" &&
    (value.description === null || typeof value.description === "string") &&
    typeof value.schedule_eligible === "boolean" &&
    typeof value.created_at === "string" &&
    typeof value.updated_at === "string"
  );
}

function isScenarioRun(value: unknown): value is ScenarioRun {
  return (
    isRecord(value) &&
    typeof value.id === "string" &&
    typeof value.scenario_id === "string" &&
    typeof value.website_id === "string" &&
    typeof value.journey_id === "string" &&
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
