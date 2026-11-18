/**
 * Browser client for email/password sessions.
 *
 * Cookies are HttpOnly and set by the API. Every call uses credentials so the
 * browser sends `sentinel_session` cross-origin to the FastAPI origin.
 */

import { resolveApiUrl } from "@/lib/api";

export type AuthUser = {
  id: string;
  email: string;
  created_at: string;
};

export class AuthApiError extends Error {
  readonly status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "AuthApiError";
    this.status = status;
  }
}

export async function registerAccount(email: string, password: string): Promise<AuthUser> {
  const response = await request("/api/auth/register", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email: email.trim(), password }),
  });
  return readUser(response);
}

export async function loginAccount(email: string, password: string): Promise<AuthUser> {
  const response = await request("/api/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email: email.trim(), password }),
  });
  return readUser(response);
}

export async function logoutAccount(): Promise<void> {
  await request("/api/auth/logout", { method: "POST" });
}

export async function getCurrentUser(signal?: AbortSignal): Promise<AuthUser | null> {
  const apiUrl = resolveApiUrl();
  let response: Response;
  try {
    response = await fetch(`${apiUrl}/api/auth/me`, {
      credentials: "include",
      headers: { Accept: "application/json" },
      signal,
      cache: "no-store",
    });
  } catch (error) {
    throw new AuthApiError(`The API could not be reached at ${apiUrl}. ${describe(error)}`, 0);
  }
  if (response.status === 401) {
    return null;
  }
  if (!response.ok) {
    throw new AuthApiError(await readDetail(response), response.status);
  }
  return readUser(response);
}

async function readUser(response: Response): Promise<AuthUser> {
  const body: unknown = await response.json();
  if (!isAuthUser(body)) {
    throw new AuthApiError("The account payload was not in the expected shape.", response.status);
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
    throw new AuthApiError(`The API could not be reached at ${apiUrl}. ${describe(error)}`, 0);
  }
  if (response.ok) {
    return response;
  }
  throw new AuthApiError(await readDetail(response), response.status);
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

function isAuthUser(value: unknown): value is AuthUser {
  return (
    isRecord(value) &&
    typeof value.id === "string" &&
    typeof value.email === "string" &&
    typeof value.created_at === "string"
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
