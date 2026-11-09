/**
 * Browser client for website checks.
 *
 * A check can take as long as the API's navigation budget. The request waits
 * up to 40 seconds so the page can show the stored result instead of giving up
 * while Chromium is still running.
 */

import { resolveApiUrl } from "@/lib/api";
import { WebsiteApiError } from "@/lib/websites";

export type CheckOutcome = "success" | "failed";

export type FailedRequest = {
  url: string;
  error: string;
};

export type WebsiteCheck = {
  id: string;
  website_id: string;
  outcome: CheckOutcome;
  http_status: number | null;
  page_title: string | null;
  final_url: string | null;
  duration_ms: number;
  console_errors: string[];
  failed_requests: FailedRequest[];
  error_message: string | null;
  created_at: string;
};

const CHECK_TIMEOUT_MS = 40_000;

export async function runWebsiteCheck(websiteId: string): Promise<WebsiteCheck> {
  const response = await request(`/api/websites/${websiteId}/checks`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ authorized: true }),
    signal: AbortSignal.timeout(CHECK_TIMEOUT_MS),
  });
  return readCheck(response);
}

export async function listWebsiteChecks(websiteId: string): Promise<WebsiteCheck[]> {
  const response = await request(`/api/websites/${websiteId}/checks`);
  const body: unknown = await response.json();
  if (!Array.isArray(body) || !body.every(isWebsiteCheck)) {
    throw new WebsiteApiError("The check history was not in the expected shape.", response.status);
  }
  return body;
}

async function readCheck(response: Response): Promise<WebsiteCheck> {
  const body: unknown = await response.json();
  if (!isWebsiteCheck(body)) {
    throw new WebsiteApiError("The check result was not in the expected shape.", response.status);
  }
  return body;
}

async function request(path: string, init: RequestInit = {}): Promise<Response> {
  const apiUrl = resolveApiUrl();
  let response: Response;
  try {
    response = await fetch(`${apiUrl}${path}`, {
      ...init,
      headers: { Accept: "application/json", ...init.headers },
    });
  } catch (error) {
    const timedOut = error instanceof DOMException && error.name === "TimeoutError";
    throw new WebsiteApiError(
      timedOut
        ? "The check did not finish before the page stopped waiting. Open the history again in a moment."
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
    // A non-JSON error body still needs a sentence the page can show.
  }
  return `The API returned HTTP ${response.status}.`;
}

function isWebsiteCheck(value: unknown): value is WebsiteCheck {
  if (!isRecord(value)) {
    return false;
  }
  return (
    typeof value.id === "string" &&
    typeof value.website_id === "string" &&
    (value.outcome === "success" || value.outcome === "failed") &&
    (value.http_status === null || typeof value.http_status === "number") &&
    (value.page_title === null || typeof value.page_title === "string") &&
    (value.final_url === null || typeof value.final_url === "string") &&
    typeof value.duration_ms === "number" &&
    Array.isArray(value.console_errors) &&
    value.console_errors.every((item) => typeof item === "string") &&
    Array.isArray(value.failed_requests) &&
    value.failed_requests.every(isFailedRequest) &&
    (value.error_message === null || typeof value.error_message === "string") &&
    typeof value.created_at === "string"
  );
}

function isFailedRequest(value: unknown): value is FailedRequest {
  return isRecord(value) && typeof value.url === "string" && typeof value.error === "string";
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
