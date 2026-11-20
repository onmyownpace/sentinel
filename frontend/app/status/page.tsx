import { getApiSnapshot } from "@/lib/api";

export const dynamic = "force-dynamic";

function tone(value: string | null | undefined): string {
  if (value === "ok") {
    return "ok";
  }
  if (value === null || value === undefined) {
    return "";
  }
  return "bad";
}

export default async function StatusPage() {
  const snapshot = await getApiSnapshot();
  const database = snapshot.readiness?.checks.database ?? null;

  return (
    <main>
      <header className="workspace-hero">
        <p className="workspace-kicker">Diagnostics</p>
        <h1>Status</h1>
        <p>
          Operator view of API process liveness and PostgreSQL readiness. This is not the
          product dashboard — use Dashboard for monitoring.
        </p>
      </header>

      <section className="card" aria-label="Runtime status">
        <h2>Runtime status</h2>
        {snapshot.reached && snapshot.liveness && snapshot.readiness ? (
          <dl>
            <div>
              <dt>API process</dt>
              <dd className={tone(snapshot.liveness.status)}>
                {snapshot.liveness.status} ({snapshot.livenessStatus})
              </dd>
            </div>
            <div>
              <dt>Database</dt>
              <dd className={tone(database)}>
                {database} ({snapshot.readinessStatus})
              </dd>
            </div>
            <div>
              <dt>Service</dt>
              <dd>{snapshot.liveness.service}</dd>
            </div>
            <div>
              <dt>Version</dt>
              <dd>{snapshot.liveness.version}</dd>
            </div>
            <div>
              <dt>Environment</dt>
              <dd>{snapshot.liveness.environment}</dd>
            </div>
            <div>
              <dt>Public shell</dt>
              <dd>{snapshot.liveness.public_shell ? "yes (demo — no live Chromium)" : "no"}</dd>
            </div>
            <div>
              <dt>Live browser</dt>
              <dd>{snapshot.liveness.live_browser_enabled === false ? "disabled" : "enabled"}</dd>
            </div>
            <div>
              <dt>Analysis</dt>
              <dd>{snapshot.liveness.analysis_provider ?? "simulated"}</dd>
            </div>
            <div>
              <dt>Analysis model</dt>
              <dd>{snapshot.liveness.analysis_model ?? "simulated-local"}</dd>
            </div>
            <div>
              <dt>Analysis endpoint host</dt>
              <dd>
                {snapshot.liveness.analysis_provider === "openai"
                  ? snapshot.liveness.analysis_base_host ?? "default (api.openai.com)"
                  : "n/a (simulated)"}
              </dd>
            </div>
            <div>
              <dt>API address</dt>
              <dd>{snapshot.apiUrl}</dd>
            </div>
          </dl>
        ) : (
          <p className="bad">The API could not be read. {snapshot.error}</p>
        )}
        {snapshot.reached ? (
          <p className="hint">
            <a href={`${snapshot.apiUrl}/docs`}>Open the API documentation</a>
          </p>
        ) : null}
        {snapshot.reached && database !== "ok" ? (
          <p className="hint">
            PostgreSQL did not answer. Start it with Docker Compose from the
            repository root, then refresh this page.
          </p>
        ) : null}
        {!snapshot.reached ? (
          <p className="hint">
            Start the API from the backend directory, then refresh. The
            expected address is {snapshot.apiUrl}.
          </p>
        ) : null}
      </section>
    </main>
  );
}
