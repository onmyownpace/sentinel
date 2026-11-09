import type { WebsiteCheck } from "@/lib/checks";

type CheckResultProps = {
  check: WebsiteCheck;
};

export function CheckResult({ check }: CheckResultProps) {
  const outcomeClass = check.outcome === "success" ? "ok" : "bad";
  const outcomeLabel = check.outcome === "success" ? "Success" : "Failed";

  return (
    <div className="check-result">
      <p className={outcomeClass}>
        {outcomeLabel}
        {check.http_status !== null ? ` · HTTP ${check.http_status}` : ""}
        {` · ${check.duration_ms} ms`}
      </p>
      {check.page_title ? <p className="meta">Title: {check.page_title}</p> : null}
      {check.final_url ? (
        <p className="meta">
          Final URL:{" "}
          <a href={check.final_url} target="_blank" rel="noreferrer">
            {check.final_url}
          </a>
        </p>
      ) : null}
      {check.error_message ? <p className="meta">{check.error_message}</p> : null}
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
