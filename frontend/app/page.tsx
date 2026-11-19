import Link from "next/link";

const sampleChecks = [
  { status: "503", label: "Service unavailable", duration: 88, failed: true },
  { status: "200", label: "Homepage reachable", duration: 142, failed: false },
];

export default function HomePage() {
  return (
    <main className="portfolio-demo">
      <header className="portfolio-intro">
        <span className="portfolio-badge">Read-only demo</span>
        <h1>Website monitoring</h1>
        <p>Explore a sample check history and see how Sentinel explains a failure.</p>
      </header>

      <section className="card portfolio-checks" aria-labelledby="sample-site">
        <h2 id="sample-site">Example status page</h2>
        <p className="hint">example.com · Sample data</p>
        <div className="portfolio-metrics">
          <div><strong>2</strong><span>Checks</span></div>
          <div><strong>1</strong><span>Failure</span></div>
          <div><strong>115 ms</strong><span>Average response</span></div>
        </div>
        <h3>Check history</h3>
        {sampleChecks.map(({ status, label, duration, failed }) => (
          <details key={status} className="portfolio-check">
            <summary>
              <span className={failed ? "bad" : "ok"}>HTTP {status}</span>
              <span>{label}</span>
              <span className="hint">{duration} ms</span>
            </summary>
            {failed ? (
              <div className="portfolio-analysis">
                <strong>Sample failure analysis</strong>
                <p>The server returned HTTP 503. Check service health and recent deployments before retrying.</p>
              </div>
            ) : (
              <p className="portfolio-analysis">The sample homepage returned HTTP 200.</p>
            )}
          </details>
        ))}
      </section>
      <section className="portfolio-capabilities" aria-labelledby="capabilities">
        <h2 id="capabilities">What Sentinel can do</h2>
        <div className="portfolio-feature-grid">
          <article className="card">
            <h3>Uptime and latency trends</h3>
            <p>Compare availability and response times across a time window.</p>
          </article>
          <article className="card">
            <h3>Failure investigation</h3>
            <p>Inspect failed checks, identify recurring patterns, and draft incident summaries.</p>
          </article>
          <article className="card">
            <h3>Browser journeys</h3>
            <p>Run multi-step flows, reusable scenarios, and screenshot capture in a local installation.</p>
          </article>
          <article className="card">
            <h3>Scheduled monitoring</h3>
            <p>Run scheduled checks and deliver incident updates through a local n8n workflow.</p>
          </article>
        </div>
      </section>
      <p className="hint"><Link href="/login">Sign in to your workspace</Link></p>
    </main>
  );
}
