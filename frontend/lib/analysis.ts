/**
 * Browser client for on-demand AI failure analysis of a stored check.
 *
 * Analysis does not start a new browser check. The request waits for the
 * provider; forty seconds matches the check client so a slow model still
 * returns into the panel instead of timing out early.
 */

import { resolveApiUrl } from "@/lib/api";
import { WebsiteApiError } from "@/lib/websites";

export type AnalysisSeverity = "low" | "medium" | "high" | "critical";
export type AnalysisConfidence = "low" | "medium" | "high";

export type PossibleCause = {
  cause: string;
  confidence: AnalysisConfidence;
  evidence: string;
};

export type AnalysisProvider = "simulated" | "openai";

export type FailureAnalysis = {
  id: string;
  check_id: string;
  summary: string;
  severity: AnalysisSeverity;
  confirmed_observations: string[];
  possible_causes: PossibleCause[];
  recommended_investigation_steps: string[];
  limitations: string;
  model_name: string;
  provider: AnalysisProvider;
  created_at: string;
};

const ANALYSIS_TIMEOUT_MS = 40_000;

export async function createCheckAnalysis(checkId: string): Promise<FailureAnalysis> {
  const response = await request(`/api/checks/${checkId}/analysis`, {
    method: "POST",
    signal: AbortSignal.timeout(ANALYSIS_TIMEOUT_MS),
  });
  return readAnalysis(response);
}

export async function getCheckAnalysis(checkId: string): Promise<FailureAnalysis | null> {
  const apiUrl = resolveApiUrl();
  let response: Response;
  try {
    response = await fetch(`${apiUrl}/api/checks/${checkId}/analysis`, {
      credentials: "include",
      headers: { Accept: "application/json" },
      signal: AbortSignal.timeout(ANALYSIS_TIMEOUT_MS),
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
  return readAnalysis(response);
}

async function readAnalysis(response: Response): Promise<FailureAnalysis> {
  const body: unknown = await response.json();
  if (!isFailureAnalysis(body)) {
    throw new WebsiteApiError("The analysis was not in the expected shape.", response.status);
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
        ? "The analysis did not finish before the page stopped waiting. Try again in a moment."
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
    if (!isRecord(body)) {
      return `The API returned HTTP ${response.status}.`;
    }
    if (typeof body.detail === "string") {
      return body.detail;
    }
    if (Array.isArray(body.detail)) {
      for (const item of body.detail) {
        if (isRecord(item) && typeof item.msg === "string") {
          return item.msg.replace(/^Value error, /, "");
        }
      }
    }
  } catch {
    // Non-JSON bodies still need a sentence for the panel.
  }
  return `The API returned HTTP ${response.status}.`;
}

function isFailureAnalysis(value: unknown): value is FailureAnalysis {
  if (!isRecord(value)) {
    return false;
  }
  return (
    typeof value.id === "string" &&
    typeof value.check_id === "string" &&
    typeof value.summary === "string" &&
    isSeverity(value.severity) &&
    Array.isArray(value.confirmed_observations) &&
    value.confirmed_observations.every((item) => typeof item === "string") &&
    Array.isArray(value.possible_causes) &&
    value.possible_causes.every(isPossibleCause) &&
    Array.isArray(value.recommended_investigation_steps) &&
    value.recommended_investigation_steps.every((item) => typeof item === "string") &&
    typeof value.limitations === "string" &&
    typeof value.model_name === "string" &&
    (value.provider === "simulated" || value.provider === "openai") &&
    typeof value.created_at === "string"
  );
}

function isPossibleCause(value: unknown): value is PossibleCause {
  return (
    isRecord(value) &&
    typeof value.cause === "string" &&
    isConfidence(value.confidence) &&
    typeof value.evidence === "string"
  );
}

function isSeverity(value: unknown): value is AnalysisSeverity {
  return value === "low" || value === "medium" || value === "high" || value === "critical";
}

function isConfidence(value: unknown): value is AnalysisConfidence {
  return value === "low" || value === "medium" || value === "high";
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
