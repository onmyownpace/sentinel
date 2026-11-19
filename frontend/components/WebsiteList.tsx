"use client";

import Link from "next/link";

import type { Website } from "@/lib/websites";

type WebsiteListProps = {
  websites: Website[];
  pendingDeleteId: string | null;
  deletingId: string | null;
  onAskDelete: (id: string) => void;
  onConfirmDelete: (id: string) => void;
  onCancelDelete: () => void;
  /** Kept for registry compatibility; site tools live on Site health. */
  onWebsiteUpdated?: (website: Website) => void;
};

export function WebsiteList({
  websites,
  pendingDeleteId,
  deletingId,
  onAskDelete,
  onConfirmDelete,
  onCancelDelete,
}: WebsiteListProps) {
  if (websites.length === 0) {
    return <p className="hint tight">No websites registered yet.</p>;
  }

  return (
    <ul className="website-list">
      {websites.map((website) => {
        const confirming = pendingDeleteId === website.id;
        const deleting = deletingId === website.id;
        return (
          <li key={website.id} className="website">
            <div className="website-heading">
              <div>
                <h3>
                  <Link href={`/websites/${website.id}`}>{website.name}</Link>
                </h3>
                <p className="meta">
                  <a href={website.base_url} target="_blank" rel="noreferrer">
                    {website.base_url}
                  </a>
                </p>
                <p className="meta">
                  Monitoring: {website.monitoring_enabled ? "enrolled" : "off"}
                  {" · "}
                  Added {formatTimestamp(website.created_at)}
                </p>
                <p className="meta">
                  <Link href={`/websites/${website.id}`}>Open site health</Link>
                  {" — overview, investigate, automation"}
                </p>
              </div>
              {confirming ? (
                <div
                  className="confirm"
                  role="group"
                  aria-label={`Confirm deletion of ${website.name}`}
                >
                  <p className="hint tight">Delete {website.name} and its check history?</p>
                  <div className="actions">
                    <button
                      className="danger"
                      type="button"
                      disabled={deleting}
                      onClick={() => onConfirmDelete(website.id)}
                    >
                      {deleting ? "Deleting…" : "Delete"}
                    </button>
                    <button type="button" disabled={deleting} onClick={onCancelDelete}>
                      Cancel
                    </button>
                  </div>
                </div>
              ) : (
                <button type="button" onClick={() => onAskDelete(website.id)}>
                  Delete
                </button>
              )}
            </div>
          </li>
        );
      })}
    </ul>
  );
}

function formatTimestamp(value: string): string {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }
  return parsed.toLocaleString();
}
