"use client";

import Link from "next/link";

import { FailureAnalysisPanel } from "@/components/FailureAnalysis";
import type { WebsiteCheck } from "@/lib/checks";

type CheckResultProps = {
  check: WebsiteCheck;
  disabled?: boolean;
  showDetailLink?: boolean;
};

export function CheckResult({
  check,
  disabled = false,
  showDetailLink = true,
}: CheckResultProps) {
  const outcomeClass = check.outcome === "success" ? "ok" : "bad";
  const outcomeLabel = check.outcome === "success" ? "Success" : "Failed";
  const isDemo =
    typeof check.error_message === "string" &&
    check.error_message.includes("Demo result — not a live browser check");
  const isProbe =
    typeof check.error_message === "string" &&
    check.error_message.includes("Lightweight HTTP probe");

  return (
    <div className="check-result">
      {isDemo ? (
        <p className="banner warn tight" role="status">
          <span className="demo-chip">Demo</span> Sample result — not a live browser check or
          live monitoring product
        </p>
      ) : null}
      {isProbe ? (
        <p className="banner warn tight" role="status">
          <span className="demo-chip">Lightweight</span> HTTP probe — status/latency/title only,
          not full browser automation
        </p>
      ) : null}
      <p className={outcomeClass}>
        {outcomeLabel}
        {check.http_status !== null ? ` · HTTP ${check.http_status}` : ""}
        {` · ${check.duration_ms} ms`}
      </p>
      {showDetailLink ? (
        <p className="meta">
          <Link href={`/checks/${check.id}`}>Open check detail</Link>
          {" · analysis & screenshot stub"}
        </p>
      ) : null}
      {check.page_title ? <p className="meta">Title: {check.page_title}</p> : null}
      {check.final_url ? (
        <p className="meta">
          Final URL:{" "}
          <a href={check.final_url} target="_blank" rel="noreferrer">
            {check.final_url}
          </a>
        </p>
      ) : null}
      {check.error_message && !isDemo && !(isProbe && check.outcome === "success") ? (
        <p className="meta">
          {isProbe
            ? check.error_message.replace(
                /^Lightweight HTTP probe — not a full browser check\.\s*(No Chromium, console capture, or screenshots\.\s*)?/,
                "",
              )
            : check.error_message}
        </p>
      ) : null}
      {check.console_errors.length > 0 ? (
        <div>
          <p className="meta">Console errors</p>
          <ul>
            {check.console_errors.map((error, index) => (
              <li key={`${index}:${error}`}>{error}</li>
            ))}
          </ul>
        </div>
      ) : null}
      {check.failed_requests.length > 0 ? (
        <div>
          <p className="meta">Failed requests</p>
          <ul>
            {check.failed_requests.map((request, index) => (
              <li key={`${index}:${request.url}:${request.error}`}>
                {request.url} — {request.error}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
      <p className="meta">Checked {formatTimestamp(check.created_at)}</p>
      {check.outcome === "failed" ? (
        <FailureAnalysisPanel checkId={check.id} disabled={disabled} />
      ) : null}
    </div>
  );
}

function formatTimestamp(value: string): string {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }
  return parsed.toLocaleString();
}
