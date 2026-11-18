/**
 * Browser client for AI-2 historical pattern hints on one website.
 */

import { resolveApiUrl } from "@/lib/api";
import { WebsiteApiError } from "@/lib/websites";

export type PatternHintItem = {
  kind: string;
  title: string;
  detail: string;
  confidence: string;
  evidence: string;
};

export type PatternHints = {
  id: string;
  website_id: string;
  window: string;
  sample_limit: number;
  check_count: number;
  failure_count: number;
  based_on_latest_check_id: string | null;
  summary: string;
  severity: string;
  patterns: PatternHintItem[];
  confirmed_observations: string[];
  recommended_investigation_steps: string[];
  limitations: string;
  model_name: string;
  provider: string;
  created_at: string;
};

const TIMEOUT_MS = 60_000;

export async function createPatternHints(
  websiteId: string,
  options?: { window?: string; refresh?: boolean },
): Promise<PatternHints> {
  const params = new URLSearchParams();
  if (options?.window) {
    params.set("window", options.window);
  }
  if (options?.refresh) {
    params.set("refresh", "true");
  }
  const query = params.toString();
  const path = `/api/websites/${websiteId}/pattern-hints${query ? `?${query}` : ""}`;
  const response = await request(path, {
    method: "POST",
    signal: AbortSignal.timeout(TIMEOUT_MS),
  });
  return readHints(response);
}

export async function getPatternHints(websiteId: string): Promise<PatternHints | null> {
  const apiUrl = resolveApiUrl();
  let response: Response;
  try {
    response = await fetch(`${apiUrl}/api/websites/${websiteId}/pattern-hints`, {
      credentials: "include",
      headers: { Accept: "application/json" },
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
  return readHints(response);
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
        ? "Pattern hints did not finish before the page stopped waiting."
        : `The API could not be reached at ${apiUrl}. ${describe(error)}`,
      0,
    );
  }
  if (response.ok) {
    return response;
  }
  throw new WebsiteApiError(await readDetail(response), response.status);
}

async function readHints(response: Response): Promise<PatternHints> {
  const body: unknown = await response.json();
  if (!isPatternHints(body)) {
    throw new WebsiteApiError("Pattern hints were not in the expected shape.", response.status);
  }
  return body;
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

function isPatternHints(value: unknown): value is PatternHints {
  return (
    isRecord(value) &&
    typeof value.id === "string" &&
    typeof value.website_id === "string" &&
    typeof value.window === "string" &&
    typeof value.sample_limit === "number" &&
    typeof value.check_count === "number" &&
    typeof value.failure_count === "number" &&
    (value.based_on_latest_check_id === null || typeof value.based_on_latest_check_id === "string") &&
    typeof value.summary === "string" &&
    typeof value.severity === "string" &&
    Array.isArray(value.patterns) &&
    Array.isArray(value.confirmed_observations) &&
    Array.isArray(value.recommended_investigation_steps) &&
    typeof value.limitations === "string" &&
    typeof value.model_name === "string" &&
    typeof value.provider === "string" &&
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
