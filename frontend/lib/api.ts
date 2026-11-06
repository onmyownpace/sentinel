/**
 * Server-side reader for the Sentinel API health endpoints.
 *
 * This module runs in the Next.js server process. The browser receives the
 * rendered HTML and does not call the API itself in this milestone.
 */

const DEFAULT_API_URL = "http://localhost:8000";
// Longer than the API's database connect timeout so a down database comes
// back as HTTP 503, which this page can explain, rather than as a fetch abort.
const REQUEST_TIMEOUT_MS = 8000;

export type HealthBody = {
  status: string;
  service: string;
  version: string;
  environment: string;
};

export type ReadinessBody = HealthBody & {
  checks: {
    database: string;
  };
};

export type ApiSnapshot = {
  apiUrl: string;
  reached: boolean;
  error: string | null;
  livenessStatus: number | null;
  liveness: HealthBody | null;
  readinessStatus: number | null;
  readiness: ReadinessBody | null;
};

export function resolveApiUrl(): string {
  const configured = process.env.NEXT_PUBLIC_API_URL?.trim();
  if (!configured) {
    return DEFAULT_API_URL;
  }
  return configured.replace(/\/$/, "");
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

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function isHealthBody(value: unknown): value is HealthBody {
  if (!isRecord(value)) {
    return false;
  }
  return (
    typeof value.status === "string" &&
    typeof value.service === "string" &&
    typeof value.version === "string" &&
    typeof value.environment === "string"
  );
}

function isReadinessBody(value: unknown): value is ReadinessBody {
  if (!isRecord(value)) {
    return false;
  }
  // Read `checks` from the raw record before the health predicate narrows `value`.
  const checks = value.checks;
  return isHealthBody(value) && isRecord(checks) && typeof checks.database === "string";
}

async function readJson(path: string, apiUrl: string): Promise<{ status: number; body: unknown }> {
  const response = await fetch(`${apiUrl}${path}`, {
    cache: "no-store",
    signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS),
  });
  const body: unknown = await response.json();
  return { status: response.status, body };
}

export async function getApiSnapshot(): Promise<ApiSnapshot> {
  const apiUrl = resolveApiUrl();
  const empty: ApiSnapshot = {
    apiUrl,
    reached: false,
    error: null,
    livenessStatus: null,
    liveness: null,
    readinessStatus: null,
    readiness: null,
  };

  try {
    const liveness = await readJson("/health", apiUrl);
    const readiness = await readJson("/health/ready", apiUrl);
    if (!isHealthBody(liveness.body) || !isReadinessBody(readiness.body)) {
      return {
        ...empty,
        error: "The API responded, but the health payload was not in the expected shape.",
      };
    }
    return {
      apiUrl,
      reached: true,
      error: null,
      livenessStatus: liveness.status,
      liveness: liveness.body,
      readinessStatus: readiness.status,
      readiness: readiness.body,
    };
  } catch (error) {
    return { ...empty, error: describe(error) };
  }
}
