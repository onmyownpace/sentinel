"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { WebsiteForm } from "@/components/WebsiteForm";
import { WebsiteList } from "@/components/WebsiteList";
import { deleteWebsite, listWebsites, WebsiteApiError, type Website } from "@/lib/websites";

export function WebsiteRegistry() {
  const [websites, setWebsites] = useState<Website[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [pendingDeleteId, setPendingDeleteId] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const requestId = useRef(0);

  const load = useCallback(async (signal?: AbortSignal) => {
    const current = ++requestId.current;
    setLoading(true);
    try {
      const next = await listWebsites(signal);
      if (current !== requestId.current) {
        return;
      }
      setWebsites(next);
      setLoadError(null);
    } catch (error) {
      if (signal?.aborted || current !== requestId.current) {
        return;
      }
      setLoadError(error instanceof Error ? error.message : "The website list could not be loaded.");
    } finally {
      if (!signal?.aborted && current === requestId.current) {
        setLoading(false);
      }
    }
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    void load(controller.signal);
    return () => controller.abort();
  }, [load]);

  function onCreated(website: Website) {
    requestId.current += 1;
    setWebsites((current) => [website, ...current.filter((item) => item.id !== website.id)]);
    setLoading(false);
    setLoadError(null);
    setActionError(null);
    setNotice(`${website.name} was added.`);
  }

  async function onConfirmDelete(id: string) {
    setDeletingId(id);
    setActionError(null);
    try {
      await deleteWebsite(id);
      requestId.current += 1;
      setWebsites((current) => current.filter((website) => website.id !== id));
      setNotice("Website deleted.");
      setPendingDeleteId(null);
    } catch (error) {
      const message = error instanceof WebsiteApiError ? error.message : "The website could not be deleted.";
      setActionError(message);
      if (error instanceof WebsiteApiError && error.status === 404) {
        setWebsites((current) => current.filter((website) => website.id !== id));
        setPendingDeleteId(null);
      }
    } finally {
      setDeletingId(null);
    }
  }

  return (
    <div className="registry">
      <WebsiteForm onCreated={onCreated} />
      <section className="card" aria-label="Registered websites" aria-busy={loading}>
        <h2>Registered websites{!loading && !loadError ? ` (${websites.length})` : ""}</h2>
        {notice ? (
          <p className="banner ok" role="status">
            {notice}
          </p>
        ) : null}
        {actionError ? (
          <p className="banner bad" role="alert">
            {actionError}
          </p>
        ) : null}
        {loading ? <p className="hint tight">Loading websites…</p> : null}
        {loadError ? (
          <div>
            <p className="banner bad" role="alert">
              {loadError}
            </p>
            <div className="actions">
              <button type="button" onClick={() => void load()}>
                Try again
              </button>
            </div>
          </div>
        ) : null}
        {!loading && !loadError ? (
          <WebsiteList
            websites={websites}
            pendingDeleteId={pendingDeleteId}
            deletingId={deletingId}
            onAskDelete={(id) => {
              setNotice(null);
              setActionError(null);
              setPendingDeleteId(id);
            }}
            onConfirmDelete={(id) => void onConfirmDelete(id)}
            onCancelDelete={() => setPendingDeleteId(null)}
          />
        ) : null}
      </section>
    </div>
  );
}
