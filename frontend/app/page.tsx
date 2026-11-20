import Link from "next/link";

export default function HomePage() {
  return (
    <main className="landing">
      <section className="landing-hero" aria-label="Sentinel">
        <div className="landing-atmosphere" aria-hidden="true">
          <div className="landing-orb landing-orb-a" />
          <div className="landing-orb landing-orb-b" />
          <div className="landing-grid" />
          <div className="landing-pulse" />
        </div>
        <div className="landing-hero-copy">
          <p className="landing-brand">Sentinel</p>
          <h1 className="landing-headline">See the outage before your users do.</h1>
          <p className="landing-support">
            Website monitoring with failure history and AI analysis — try a live sample in one
            click.
          </p>
          <p className="landing-cta">
            <Link className="landing-cta-primary" href="/demo">
              Try the demo
            </Link>
          </p>
        </div>
        <div className="landing-visual" aria-hidden="true">
          <div className="landing-console-glow">
            <span className="landing-status-fail">HTTP 503</span>
            <span className="landing-status-label">Failed check</span>
            <span className="landing-status-ai">AI analysis ready</span>
          </div>
        </div>
      </section>
    </main>
  );
}
