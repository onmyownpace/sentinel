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

export default async function HomePage() {
  const snapshot = await getApiSnapshot();
  const database = snapshot.readiness?.checks.database ?? null;

  return (
    <main>
      <h1>Sentinel</h1>
      <p>
        Foundation milestone. This page asks the API whether the process is up
        and whether PostgreSQL answered a connectivity check.
      </p>

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
