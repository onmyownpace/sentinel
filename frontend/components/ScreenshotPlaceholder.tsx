"use client";

import { useEffect, useState } from "react";

import { fetchCheckScreenshot } from "@/lib/checks";
import { WebsiteApiError } from "@/lib/websites";

type ScreenshotPanelProps = {
  checkId: string;
  hasScreenshot: boolean;
};

/**
 * Shows a stored check screenshot when BROW-1 captured one.
 * Falls back to an honest empty state when `has_screenshot` is false.
 */
export function ScreenshotPlaceholder({ checkId, hasScreenshot }: ScreenshotPanelProps) {
  const [objectUrl, setObjectUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(hasScreenshot);

  useEffect(() => {
    if (!hasScreenshot) {
      setObjectUrl(null);
      setError(null);
      setLoading(false);
      return;
    }
    const controller = new AbortController();
    let revoked: string | null = null;
    setLoading(true);
    setError(null);
    fetchCheckScreenshot(checkId, controller.signal)
      .then((blob) => {
        const url = URL.createObjectURL(blob);
        revoked = url;
        setObjectUrl(url);
      })
      .catch((err: unknown) => {
        if (err instanceof DOMException && err.name === "AbortError") {
          return;
        }
        setObjectUrl(null);
        setError(
          err instanceof WebsiteApiError ? err.message : "The screenshot could not be loaded.",
        );
      })
      .finally(() => setLoading(false));
    return () => {
      controller.abort();
      if (revoked) {
        URL.revokeObjectURL(revoked);
      }
    };
  }, [checkId, hasScreenshot]);

  return (
    <section className="screenshot-panel" aria-label="Screenshot">
      <h3>Screenshot</h3>
      {!hasScreenshot ? (
        <p className="hint tight">
          No screenshot was stored for check <code>{checkId}</code>. Capture is optional and
          bounded; a missing file usually means the runner skipped or rejected the PNG.
        </p>
      ) : null}
      {hasScreenshot && loading ? <p className="hint tight">Loading screenshot…</p> : null}
      {error ? (
        <p className="field-error" role="alert">
          {error}
        </p>
      ) : null}
      {objectUrl ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img className="check-screenshot" src={objectUrl} alt={`Screenshot for check ${checkId}`} />
      ) : null}
    </section>
  );
}
