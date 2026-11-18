/**
 * Browser client for AI-3 incident summary drafts.
 */

import { resolveApiUrl } from "@/lib/api";
import { WebsiteApiError } from "@/lib/websites";

export type IncidentDraft = {
  id: string;
  website_id: string;
  website_name: string;
  base_url: string;
  failed_check_limit: number;
  failed_check_count: number;
  source_fingerprint: string;
  check_ids: string[];
  analysis_ids: string[];
  paragraph: string;
  text: string;
  severity: string;
  observations: string[];
  limitations: string;
  model_name: string;
  provider: string;
  created_at: string;
};

const TIMEOUT_MS = 60_000;

export async function createIncidentDraft(
  websiteId: string,
  options?: { limit?: number; refresh?: boolean },
): Promise<IncidentDraft> {
  const params = new URLSearchParams();
  if (options?.limit != null) {
    params.set("limit", String(options.limit));
  }
  if (options?.refresh) {
    params.set("refresh", "true");
  }
  const query = params.toString();
  const path = `/api/websites/${websiteId}/incident-drafts${query ? `?${query}` : ""}`;
  const response = await request(path, {
    method: "POST",
    signal: AbortSignal.timeout(TIMEOUT_MS),
  });
  return readDraft(response);
}

export async function listIncidentDrafts(websiteId: string): Promise<IncidentDraft[]> {
  const response = await request(`/api/websites/${websiteId}/incident-drafts`);
  const body: unknown = await response.json();
  if (!Array.isArray(body) || !body.every(isIncidentDraft)) {
    throw new WebsiteApiError(
      "The incident draft list was not in the expected shape.",
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
        ? "The incident draft did not finish before the page stopped waiting."
        : `The API could not be reached at ${apiUrl}. ${describe(error)}`,
      0,
    );
  }
  if (response.ok) {
    return response;
  }
  throw new WebsiteApiError(await readDetail(response), response.status);
}

async function readDraft(response: Response): Promise<IncidentDraft> {
  const body: unknown = await response.json();
  if (!isIncidentDraft(body)) {
    throw new WebsiteApiError("The incident draft was not in the expected shape.", response.status);
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

function isIncidentDraft(value: unknown): value is IncidentDraft {
  return (
    isRecord(value) &&
    typeof value.id === "string" &&
    typeof value.website_id === "string" &&
    typeof value.website_name === "string" &&
    typeof value.base_url === "string" &&
    typeof value.failed_check_limit === "number" &&
    typeof value.failed_check_count === "number" &&
    typeof value.source_fingerprint === "string" &&
    Array.isArray(value.check_ids) &&
    Array.isArray(value.analysis_ids) &&
    typeof value.paragraph === "string" &&
    typeof value.text === "string" &&
    typeof value.severity === "string" &&
    Array.isArray(value.observations) &&
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
