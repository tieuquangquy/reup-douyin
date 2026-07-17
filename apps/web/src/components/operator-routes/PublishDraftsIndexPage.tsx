"use client";

import { useEffect, useMemo, useState } from "react";
import { useT } from "../../lib/i18n";
import { fetchPublishControlQueue } from "../../lib/api";
import { humanizeStatus } from "../../lib/statusLabels";
import type { PublishControlQueue, PublishQueueItem } from "../../types/publish-control";
import { OperatorStudioShell } from "../app-shell/OperatorStudioShell";
import { PageShell } from "../app-shell/PageShell";
import { StatusBadge } from "../app-shell/StatusBadge";

export function PublishDraftsIndexPage() {
  const t = useT();
  const [queue, setQueue] = useState<PublishControlQueue | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      setQueue(await fetchPublishControlQueue());
    } catch (err) {
      setError(err instanceof Error ? err.message : t("publishDraftsIndex.loadError"));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, [load]);

  const drafts = useMemo(
    () => [...(queue?.unassigned_drafts ?? []), ...(queue?.assigned_drafts ?? []), ...(queue?.scheduled_drafts ?? [])],
    [queue]
  );

  return (
    <OperatorStudioShell
      actions={<button type="button" onClick={() => void load()}>{t("publishDraftsIndex.refresh")}</button>}
      description={t("publishDraftsIndex.pageDesc")}
      title={t("publishDraftsIndex.pageTitle")}
    >
      {loading && !queue ? <div className="state-panel skeleton">{t("publishDraftsIndex.loading")}</div> : null}
      {error && !queue ? (
        <div className="state-panel">
          <h1>{t("publishDraftsIndex.couldNotLoad")}</h1>
          <p>{error}</p>
          <button type="button" onClick={() => void load()}>{t("publishDraftsIndex.retry")}</button>
        </div>
      ) : null}
      {queue ? (
        <PageShell
          actions={
            <>
              <a href="/ops/publish-health">{t("nav.publishHealth")}</a>
              <a href="/ops/publish-control">{t("publishDraftsIndex.openControl")}</a>
            </>
          }
          description={t("publishDraftsIndex.indexDesc")}
          title={t("publishDraftsIndex.indexTitle")}
        >
          {error ? <div className="inline-error">{error}</div> : null}
          <div className="operator-quick-grid">
            {drafts.length === 0 ? (
              <div className="operator-empty-state">
                <h3>{t("publishDraftsIndex.noReadyDrafts")}</h3>
                <p>{t("publishDraftsIndex.noReadyBody")}</p>
              </div>
            ) : null}
            {drafts.map((draft) => (
              <DraftCard draft={draft} key={draft.publish_draft_id} />
            ))}
          </div>
        </PageShell>
      ) : null}
    </OperatorStudioShell>
  );
}

function DraftCard({ draft }: { draft: PublishQueueItem }) {
  const t = useT();
  return (
    <a className="operator-quick-card" href={`/publishing/drafts/${draft.publish_draft_id}`}>
      <span>
        <strong>{draft.title || `${t("publishDraftsIndex.operatorDraft")} ${draft.publish_draft_id.slice(0, 8)}`}</strong>
        <small>{humanizeStatus(draft.status)} / {draft.target_platform} / {draft.recommended_account_name ?? t("publishDraftsIndex.noAccountRecommendation")}</small>
      </span>
      <StatusBadge label={draft.assignment_status} tone={draft.warnings.length > 0 ? "warn" : "good"} />
    </a>
  );
}
