/**
 * Browser client for the website registry.
 *
 * The status page still reads health from the Next.js server. This module
 * runs in the browser, so the API must allow the page's origin.
 */

import { resolveApiUrl } from "@/lib/api";

export type Website = {
  id: string;
  name: string;
  base_url: string;
  created_at: string;
  updated_at: string;
};

export type WebsiteInput = {
  name: string;
  base_url: string;
};

export type FieldErrors = {
  form?: string;
  name?: string;
  baseUrl?: string;
};

export class WebsiteApiError extends Error {
  readonly status: number;
  readonly fieldErrors: FieldErrors;

  constructor(message: string, status: number, fieldErrors: FieldErrors = {}) {
    super(message);
    this.name = "WebsiteApiError";
    this.status = status;
    this.fieldErrors = fieldErrors;
  }
}

const NAME_LIMIT = 120;

export function validateWebsiteInput(input: WebsiteInput): FieldErrors {
  const errors: FieldErrors = {};
  const name = input.name.trim();
  if (!name) {
    errors.name = "Name is required.";
  } else if (name.length > NAME_LIMIT) {
    errors.name = "Name must be 120 characters or fewer.";
  }

  const urlError = validateBaseUrl(input.base_url);
  if (urlError) {
    errors.baseUrl = urlError;
  }
  return errors;
}

function validateBaseUrl(value: string): string | null {
  const trimmed = value.trim();
  if (!trimmed) {
    return "Base URL is required.";
  }
  if (/\s/.test(trimmed)) {
    return "Base URL must not contain spaces.";
  }

  let url: URL;
  try {
    url = new URL(trimmed);
  } catch {
    return "Enter an absolute HTTP or HTTPS URL.";
  }
  if (url.protocol !== "http:" && url.protocol !== "https:") {
    return "Base URL must start with http:// or https://.";
  }
  if (url.username || url.password) {
    return "Base URL must not include a username or password.";
  }
  if (url.search || url.hash) {
    return "Base URL must not include a query or fragment.";
  }
  if (!url.hostname) {
    return "Base URL must include a host.";
  }
  return null;
}

export async function listWebsites(signal?: AbortSignal): Promise<Website[]> {
  const response = await request("/api/websites", { signal });
  const body: unknown = await response.json();
  if (!Array.isArray(body) || !body.every(isWebsite)) {
    throw new WebsiteApiError("The website list was not in the expected shape.", response.status);
  }
  return body;
}

export async function createWebsite(input: WebsiteInput): Promise<Website> {
  const response = await request("/api/websites", {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify({ name: input.name.trim(), base_url: input.base_url.trim() }),
  });
  const body: unknown = await response.json();
  if (!isWebsite(body)) {
    throw new WebsiteApiError("The saved website was not in the expected shape.", response.status);
  }
  return body;
}

export async function deleteWebsite(id: string): Promise<void> {
  await request(`/api/websites/${id}`, { method: "DELETE" });
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
    throw new WebsiteApiError(
      `The API could not be reached at ${apiUrl}. ${describe(error)}`,
      0,
    );
  }

  if (response.ok) {
    return response;
  }

  const detail = await readDetail(response);
  throw new WebsiteApiError(detail.message, response.status, detail.fieldErrors);
}

async function readDetail(response: Response): Promise<{ message: string; fieldErrors: FieldErrors }> {
  try {
    const body: unknown = await response.json();
    if (!isRecord(body)) {
      return { message: `The API returned HTTP ${response.status}.`, fieldErrors: {} };
    }
    if (typeof body.detail === "string") {
      const fieldErrors: FieldErrors =
        response.status === 409 ? { baseUrl: body.detail } : { form: body.detail };
      return { message: body.detail, fieldErrors };
    }
    if (Array.isArray(body.detail)) {
      const fieldErrors = fieldErrorsFromDetail(body.detail);
      const message = fieldErrors.form ?? fieldErrors.name ?? fieldErrors.baseUrl ?? "Check the form and try again.";
      return { message, fieldErrors };
    }
  } catch {
    // A non-JSON error body still needs a sentence the page can show.
  }
  return { message: `The API returned HTTP ${response.status}.`, fieldErrors: { form: `The API returned HTTP ${response.status}.` } };
}

function fieldErrorsFromDetail(detail: unknown[]): FieldErrors {
  const errors: FieldErrors = {};
  for (const item of detail) {
    if (!isRecord(item) || typeof item.msg !== "string") {
      continue;
    }
    const message = item.msg.replace(/^Value error, /, "");
    const location = Array.isArray(item.loc) ? item.loc.map(String) : [];
    if (location.includes("name")) {
      errors.name = message;
    } else if (location.includes("base_url")) {
      errors.baseUrl = message;
    } else {
      errors.form = message;
    }
  }
  return errors;
}

function isWebsite(value: unknown): value is Website {
  if (!isRecord(value)) {
    return false;
  }
  return (
    typeof value.id === "string" &&
    typeof value.name === "string" &&
    typeof value.base_url === "string" &&
    typeof value.created_at === "string" &&
    typeof value.updated_at === "string"
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
