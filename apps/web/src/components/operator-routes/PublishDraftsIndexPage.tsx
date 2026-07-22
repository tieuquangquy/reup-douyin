"use client";

import Link from "next/link";
import { useEffect, useMemo, useState, type ReactNode } from "react";
import { useT } from "../../lib/i18n";
import { useLatestRequest } from "../../lib/useLatestRequest";
import { fetchPublishControlQueue } from "../../lib/api";
import { humanizeStatus } from "../../lib/statusLabels";
import type { PublishControlQueue, PublishQueueItem } from "../../types/publish-control";
import { OperatorStudioShell } from "../app-shell/OperatorStudioShell";
import { TopbarRefreshButton } from "../app-shell/TopbarRefreshButton";
import { AsyncContentBoundary } from "../shared/AsyncContentBoundary";
import { useNotice } from "../shared/NoticeCenter";
import { OpsState, formatDateTime, statusTone, type OpsTone } from "../ops-console/OpsShared";

function DraftsKpi({ label, value, detail, tone = "muted" }: { label: string; value: string; detail: string; tone?: OpsTone }) {
  return (
    <article className={`ops-drafts-kpi tone-${tone}`} title={detail}>
      <em>{label}</em>
      <strong>{value}</strong>
      <span>{detail}</span>
    </article>
  );
}

function DraftsPanel({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="ops-drafts-panel">
      <div className="ops-drafts-panel__head">
        <h2>{title}</h2>
      </div>
      <div className="ops-drafts-panel__body">{children}</div>
    </section>
  );
}

export function PublishDraftsIndexPage() {
  const t = useT();
  const [queue, setQueue] = useState<PublishControlQueue | null>(null);
  const request = useLatestRequest();
  const { notify } = useNotice();

  async function load() {
    const mode = queue ? "refresh" : "initial";
    try {
      await request.run(() => fetchPublishControlQueue(), setQueue, mode);
      if (mode === "refresh") notify({ id: "publish-drafts-refresh", message: "Publish drafts refreshed.", tone: "success" });
    } catch (err) {
      if (mode === "refresh") notify({ id: "publish-drafts-refresh", message: err instanceof Error ? err.message : t("publishDraftsIndex.loadError"), tone: "error" });
    }
  }

  useEffect(() => {
    void load();
  }, [t]);

  const drafts = useMemo(
    () => [...(queue?.unassigned_drafts ?? []), ...(queue?.assigned_drafts ?? []), ...(queue?.scheduled_drafts ?? [])],
    [queue]
  );
  const attention = queue?.needs_attention ?? [];
  const hasAttention = attention.length > 0;

  const refreshAction = (
    <TopbarRefreshButton busy={request.refreshing} disabled={request.initialLoading} onClick={() => void load()} />
  );

  if (!queue && !request.error) {
    return (
      <OperatorStudioShell actions={refreshAction} description={t("publishDraftsIndex.pageDesc")} title={t("publishDraftsIndex.pageTitle")}>
        <AsyncContentBoundary skeletonVariant="list" status="loading"><span /></AsyncContentBoundary>
      </OperatorStudioShell>
    );
  }

  if (request.error && !queue) {
    return (
      <OperatorStudioShell actions={refreshAction} description={t("publishDraftsIndex.pageDesc")} title={t("publishDraftsIndex.pageTitle")}>
        <AsyncContentBoundary errorState={<OpsState title={t("publishDraftsIndex.couldNotLoad")} detail={request.error.message} retry={() => void load()} />} skeletonVariant="list" status="error"><span /></AsyncContentBoundary>
      </OperatorStudioShell>
    );
  }

  if (!queue) {
    return (
      <OperatorStudioShell actions={refreshAction} description={t("publishDraftsIndex.pageDesc")} title={t("publishDraftsIndex.pageTitle")}>
        <OpsState title={t("publishDraftsIndex.couldNotLoad")} detail={t("publishDraftsIndex.emptyQueue")} />
      </OperatorStudioShell>
    );
  }

  return (
    <OperatorStudioShell actions={refreshAction} description={t("publishDraftsIndex.pageDesc")} title={t("publishDraftsIndex.pageTitle")}>
      <AsyncContentBoundary refreshing={request.refreshing} skeletonVariant="list" status="success">
      <main className="ops-page ops-drafts-page">

        <div className="ops-drafts-freshness">
          <p>
            {t("publishDraftsIndex.generatedAt")}{" "}
            <time dateTime={queue.generated_at}>{formatDateTime(queue.generated_at)}</time>
          </p>
        </div>

        <section className="ops-drafts-kpis" aria-label={t("publishDraftsIndex.summary")}>
          <DraftsKpi label={t("publishDraftsIndex.totalDrafts")} value={String(drafts.length)} detail={t("publishDraftsIndex.totalDraftsDetail")} tone="good" />
          <DraftsKpi
            label={t("publishDraftsIndex.unassigned")}
            value={String(queue.unassigned_drafts.length)}
            detail={t("publishDraftsIndex.unassignedDetail")}
            tone={queue.unassigned_drafts.length > 0 ? "warn" : "muted"}
          />
          <DraftsKpi label={t("publishDraftsIndex.assigned")} value={String(queue.assigned_drafts.length)} detail={t("publishDraftsIndex.assignedDetail")} tone="good" />
          <DraftsKpi label={t("publishDraftsIndex.scheduled")} value={String(queue.scheduled_drafts.length)} detail={t("publishDraftsIndex.scheduledDetail")} tone="muted" />
        </section>

        <div className="ops-drafts-toolbar">
          <nav className="ops-drafts-actions" aria-label={t("publishDraftsIndex.triage")}>
            <Link href="/publishing/export-packages">{t("nav.exportPackages")}</Link>
            <Link href="/publishing/publish-handoffs">{t("nav.publishHandoffs")}</Link>
          </nav>
        </div>

        <section className={`ops-drafts-main${hasAttention ? " has-attention" : ""}`}>
          <DraftsPanel title={t("publishDraftsIndex.indexTitle")}>
            {drafts.length === 0 ? (
              <div className="ops-drafts-empty">
                <strong>{t("publishDraftsIndex.noReadyDrafts")}</strong>
                <p>{t("publishDraftsIndex.noReadyBody")}</p>
              </div>
            ) : (
              <ul className="ops-drafts-sheet">
                <li className="ops-drafts-row is-head" aria-hidden="true">
                  <span>{t("publishDraftsIndex.draft")}</span>
                  <span>{t("publishDraftsIndex.status")}</span>
                  <span>{t("publishDraftsIndex.platform")}</span>
                  <span>{t("publishDraftsIndex.assignment")}</span>
                  <span>{t("publishDraftsIndex.account")}</span>
                  <span>{t("publishDraftsIndex.action")}</span>
                </li>
                {drafts.map((draft) => (
                  <DraftRow draft={draft} key={draft.publish_draft_id} t={t} />
                ))}
              </ul>
            )}
            <p className="ops-drafts-footnote">{t("publishDraftsIndex.indexDesc")}</p>
          </DraftsPanel>

          {hasAttention ? (
            <DraftsPanel title={t("publishDraftsIndex.attention")}>
              <ul className="ops-drafts-attention">
                {attention.map((draft) => (
                  <li key={draft.publish_draft_id}>
                    <div>
                      <strong>{draft.title || `${t("publishDraftsIndex.operatorDraft")} ${draft.publish_draft_id.slice(0, 8)}`}</strong>
                      <em>
                        {humanizeStatus(draft.status)} · {draft.assignment_status}
                        {draft.warnings.length > 0 ? ` · ${draft.warnings[0]}` : ""}
                      </em>
                    </div>
                    <Link href={`/publishing/drafts/${draft.publish_draft_id}`}>{t("publishDraftsIndex.open")}</Link>
                  </li>
                ))}
              </ul>
            </DraftsPanel>
          ) : null}
        </section>
      </main>
      </AsyncContentBoundary>
    </OperatorStudioShell>
  );
}

function DraftRow({ draft, t }: { draft: PublishQueueItem; t: (key: string) => string }) {
  const hot = draft.warnings.length > 0;
  return (
    <li className={`ops-drafts-row${hot ? " is-hot" : ""}`}>
      <strong className="ops-drafts-row__title" title={draft.publish_draft_id}>
        {draft.title || `${t("publishDraftsIndex.operatorDraft")} ${draft.publish_draft_id.slice(0, 8)}`}
      </strong>
      <span className={`ops-drafts-chip tone-${statusTone(draft.status)}`}>{humanizeStatus(draft.status)}</span>
      <span>{draft.target_platform}</span>
      <span className={`ops-drafts-chip tone-${hot ? "warn" : statusTone(draft.assignment_status)}`}>{draft.assignment_status}</span>
      <span title={draft.recommended_account_name ?? undefined}>
        {draft.recommended_account_name ?? t("publishDraftsIndex.noAccountRecommendation")}
      </span>
      <Link className="ops-drafts-row__link" href={`/publishing/drafts/${draft.publish_draft_id}`}>
        {t("publishDraftsIndex.open")}
      </Link>
    </li>
  );
}
