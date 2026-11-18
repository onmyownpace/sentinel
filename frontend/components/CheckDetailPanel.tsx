"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { CheckResult } from "@/components/CheckResult";
import { ScreenshotPlaceholder } from "@/components/ScreenshotPlaceholder";
import { getCheck, type WebsiteCheck } from "@/lib/checks";
import { WebsiteApiError } from "@/lib/websites";

type CheckDetailPanelProps = {
  checkId: string;
};

export function CheckDetailPanel({ checkId }: CheckDetailPanelProps) {
  const router = useRouter();
  const [check, setCheck] = useState<WebsiteCheck | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    setError(null);
    getCheck(checkId, controller.signal)
      .then(setCheck)
      .catch((err: unknown) => {
        if (err instanceof WebsiteApiError && err.status === 401) {
          router.replace("/login");
          return;
        }
        if (err instanceof WebsiteApiError && err.status === 404) {
          setError("That check was not found.");
          return;
        }
        setError(err instanceof Error ? err.message : "Could not load this check.");
      });
    return () => controller.abort();
  }, [checkId, router]);

  if (error) {
    return (
      <div className="registry">
        <p className="banner warn">{error}</p>
        <p>
          <Link href="/dashboard">Back to dashboard</Link>
        </p>
      </div>
    );
  }

  if (!check) {
    return <p className="hint">Loading check…</p>;
  }

  return (
    <div className="registry check-detail">
      <p className="crumb">
        <Link href="/dashboard">Dashboard</Link>
        {" · "}
        <Link href={`/websites/${check.website_id}`}>Site health</Link>
        {" · "}
        Check
      </p>

      <section className="card" aria-label="Check detail">
        <h2>Check detail</h2>
        <p className="meta">
          Id <code>{check.id}</code>
        </p>
        <CheckResult check={check} showDetailLink={false} />
      </section>

      <section className="card" aria-label="Screenshot">
        <ScreenshotPlaceholder checkId={check.id} hasScreenshot={check.has_screenshot} />
      </section>
    </div>
  );
}
