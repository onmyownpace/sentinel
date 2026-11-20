"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { CheckResult } from "@/components/CheckResult";
import { ScreenshotPlaceholder } from "@/components/ScreenshotPlaceholder";
import { getCheck, type WebsiteCheck } from "@/lib/checks";
import { WebsiteApiError } from "@/lib/websites";

type CheckDetailPanelProps = {
  checkId: string;
};

export function CheckDetailPanel({ checkId }: CheckDetailPanelProps) {
  const [check, setCheck] = useState<WebsiteCheck | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    setError(null);
    getCheck(checkId, controller.signal)
      .then(setCheck)
      .catch((err: unknown) => {
        if (controller.signal.aborted) {
          return;
        }
        if (err instanceof WebsiteApiError && err.status === 404) {
          setError("That check was not found.");
          return;
        }
        setError(err instanceof Error ? err.message : "Could not load this check.");
      });
    return () => controller.abort();
  }, [checkId]);

  if (error) {
    return (
      <div className="registry">
        <p className="banner warn" role="alert">
          {error}
        </p>
        <p>
          <Link href="/dashboard">Back to dashboard</Link>
        </p>
      </div>
    );
  }

  if (!check) {
    return <p className="hint">Loading check…</p>;
  }

  const failed = check.outcome !== "success";

  return (
    <div className="registry check-detail">
      <p className="crumb">
        <Link href="/dashboard">Dashboard</Link>
        {" · "}
        <Link href={`/websites/${check.website_id}`}>Site health</Link>
        {" · "}
        Check
      </p>

      <section className="card site-summary" aria-label="Stored observation">
        <div className="site-summary-heading">
          <div>
            <h2>Stored observation</h2>
            <p className="meta">
              Id <code>{check.id}</code>
            </p>
          </div>
          <div className="status-pills" aria-label="Check outcome">
            <span className={`status-pill ${failed ? "bad" : "ok"}`}>
              {failed ? "Failed" : "Success"}
            </span>
          </div>
        </div>
        {failed ? (
          <p className="next-action">
            Next: run <strong>Analyze failure</strong> below, then return to Site Health →
            Investigate for patterns or an incident draft.
          </p>
        ) : (
          <p className="next-action">
            Next: return to{" "}
            <Link href={`/websites/${check.website_id}`}>Site health</Link> for trends and
            automation.
          </p>
        )}
        <CheckResult check={check} showDetailLink={false} />
      </section>

      <section className="card" aria-label="Screenshot">
        <ScreenshotPlaceholder checkId={check.id} hasScreenshot={check.has_screenshot} />
      </section>
    </div>
  );
}
