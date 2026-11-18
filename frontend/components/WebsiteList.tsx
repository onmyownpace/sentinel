"use client";

import Link from "next/link";

import type { Website } from "@/lib/websites";
import { IncidentDraftPanel } from "@/components/IncidentDraftPanel";
import { JourneyPanel } from "@/components/JourneyPanel";
import { PatternHintsPanel } from "@/components/PatternHintsPanel";
import { ScenarioPanel } from "@/components/ScenarioPanel";
import { WebsiteChecks } from "@/components/WebsiteChecks";
import { WebsiteMonitoringConfig } from "@/components/WebsiteMonitoringConfig";
import { WebsiteStatsPanel } from "@/components/WebsiteStats";

type WebsiteListProps = {
  websites: Website[];
  pendingDeleteId: string | null;
  deletingId: string | null;
  onAskDelete: (id: string) => void;
  onConfirmDelete: (id: string) => void;
  onCancelDelete: () => void;
  onWebsiteUpdated: (website: Website) => void;
};

export function WebsiteList({
  websites,
  pendingDeleteId,
  deletingId,
  onAskDelete,
  onConfirmDelete,
  onCancelDelete,
  onWebsiteUpdated,
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
            <div>
              <h3>{website.name}</h3>
              <p className="meta">
                <a href={website.base_url} target="_blank" rel="noreferrer">
                  {website.base_url}
                </a>
              </p>
              <p className="meta">Added {formatTimestamp(website.created_at)}</p>
              <p className="meta">
                Monitoring: {website.monitoring_enabled ? "enrolled" : "off"}
                {" · "}
                <Link href={`/websites/${website.id}`}>Open health & config</Link>
              </p>
            </div>
            {confirming ? (
              <div className="confirm" role="group" aria-label={`Confirm deletion of ${website.name}`}>
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
            <WebsiteMonitoringConfig
              website={website}
              disabled={confirming || deleting}
              onUpdated={onWebsiteUpdated}
            />
            <WebsiteStatsPanel websiteId={website.id} />
            <PatternHintsPanel websiteId={website.id} disabled={confirming || deleting} />
            <IncidentDraftPanel websiteId={website.id} disabled={confirming || deleting} />
            <JourneyPanel websiteId={website.id} disabled={confirming || deleting} />
            <ScenarioPanel websiteId={website.id} disabled={confirming || deleting} />
            <WebsiteChecks websiteId={website.id} disabled={confirming || deleting} />
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
