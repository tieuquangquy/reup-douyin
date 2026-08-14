"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { useT } from "../../lib/i18n";
import { useLatestRequest } from "../../lib/useLatestRequest";
import { fetchPublishControlQueue } from "../../lib/api";
import { humanizeStatus } from "../../lib/statusLabels";
import type { PublishControlQueue, PublishQueueItem } from "../../types/publish-control";
import { OperatorStudioShell } from "../app-shell/OperatorStudioShell";
import { TopbarRefreshButton } from "../app-shell/TopbarRefreshButton";
import { AsyncContentBoundary } from "../shared/AsyncContentBoundary";
import { useNotice } from "../shared/NoticeCenter";
import { OpsState, formatDateTime, statusTone } from "../ops-console/OpsShared";
import { IntelligenceSpectrumSkeleton, IntelligenceTableSkeleton } from "./IntelligenceDataSkeleton";

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
    [queue],
  );
  const attention = queue?.needs_attention ?? [];
  const attentionCount = attention.length;
  const warningDraftCount = drafts.filter((draft) => draft.warnings.length > 0).length;
  const accountCount = queue?.accounts.length ?? 0;
  const nextScheduledAt = useMemo(() => {
    const times = (queue?.scheduled_drafts ?? [])
      .map((draft) => draft.planned_publish_at)
      .filter((value): value is string => Boolean(value))
      .map((value) => ({ value, ms: Date.parse(value) }))
      .filter((item) => Number.isFinite(item.ms))
      .sort((a, b) => a.ms - b.ms);
    return times[0]?.value ?? null;
  }, [queue]);

  const refreshAction = (
    <TopbarRefreshButton busy={request.refreshing} disabled={request.initialLoading} onClick={() => void load()} />
  );

  const shellProps = {
    actions: refreshAction,
    description: t("publishDraftsIndex.pageDesc"),
    title: t("publishDraftsIndex.pageTitle"),
  } as const;

  if (!queue && !request.error) {
    return (
      <OperatorStudioShell {...shellProps}>
        <main className="publish-drafts-page is-v1">
          <AsyncContentBoundary
            loadingLabel={t("publishDraftsIndex.loadingDetail")}
            skeleton={<><IntelligenceSpectrumSkeleton className="publish-drafts-spectrum" label={t("publishDraftsIndex.loadingDetail")} /><IntelligenceTableSkeleton label={t("publishDraftsIndex.loadingDetail")} rows={6} /></>}
            status="loading"
          >
            <span />
          </AsyncContentBoundary>
        </main>
      </OperatorStudioShell>
    );
  }

  if (request.error && !queue) {
    return (
      <OperatorStudioShell {...shellProps}>
        <main className="publish-drafts-page is-v1">
          <AsyncContentBoundary
            errorState={<OpsState title={t("publishDraftsIndex.couldNotLoad")} detail={request.error.message} retry={() => void load()} />}
            loadingLabel={t("publishDraftsIndex.loadingDetail")}
            skeleton={<><IntelligenceSpectrumSkeleton className="publish-drafts-spectrum" label={t("publishDraftsIndex.loadingDetail")} /><IntelligenceTableSkeleton label={t("publishDraftsIndex.loadingDetail")} rows={6} /></>}
            status="error"
          >
            <span />
          </AsyncContentBoundary>
        </main>
      </OperatorStudioShell>
    );
  }

  if (!queue) {
    return (
      <OperatorStudioShell {...shellProps}>
        <main className="publish-drafts-page is-v1">
          <OpsState title={t("publishDraftsIndex.couldNotLoad")} detail={t("publishDraftsIndex.emptyQueue")} />
        </main>
      </OperatorStudioShell>
    );
  }

  const unassignedCount = queue.unassigned_drafts.length;
  const assignedCount = queue.assigned_drafts.length;
  const scheduledCount = queue.scheduled_drafts.length;
  const totalCount = drafts.length;
  const mixTotal = Math.max(totalCount, 1);
  const statusLegend = [
    {
      key: "unassigned" as const,
      label: t("publishDraftsIndex.unassigned"),
      count: unassignedCount,
      pct: Math.round((unassignedCount / mixTotal) * 100),
      detail: t("publishDraftsIndex.unassignedDetail"),
      barClassName: "is-unassigned",
      legendClassName: unassignedCount > 0 ? "is-unassigned is-warning" : "is-unassigned",
    },
    {
      key: "assigned" as const,
      label: t("publishDraftsIndex.assigned"),
      count: assignedCount,
      pct: Math.round((assignedCount / mixTotal) * 100),
      detail: t("publishDraftsIndex.assignedDetail"),
      barClassName: "is-assigned",
      legendClassName: "is-assigned",
    },
    {
      key: "scheduled" as const,
      label: t("publishDraftsIndex.scheduled"),
      count: scheduledCount,
      pct: Math.round((scheduledCount / mixTotal) * 100),
      detail: t("publishDraftsIndex.scheduledDetail"),
      barClassName: "is-scheduled",
      legendClassName: "is-scheduled",
    },
  ];
  const dominantSlice = statusLegend.reduce((best, slice) => (slice.count > best.count ? slice : best), statusLegend[0]);
  const washClass = totalCount === 0 ? "is-wash-empty" : `is-wash-${dominantSlice.key}`;

  return (
    <OperatorStudioShell {...shellProps}>
      <AsyncContentBoundary
        loadingLabel={t("publishDraftsIndex.loadingDetail")}
        refreshing={request.refreshing}
        skeleton={<><IntelligenceSpectrumSkeleton className="publish-drafts-spectrum" label={t("publishDraftsIndex.loadingDetail")} /><IntelligenceTableSkeleton label={t("publishDraftsIndex.loadingDetail")} rows={6} /></>}
        status="success"
      >
      <main className="publish-drafts-page is-v1">
        <section aria-label={t("publishDraftsIndex.spectrumStatusMix")} className="publish-drafts-spectrum is-v7">
          <div className={`publish-drafts-spectrum__stage ${washClass}`.trim()}>
            <div className="publish-drafts-spectrum__poster">
              <div className="publish-drafts-spectrum__hero">
                <header className="publish-drafts-spectrum__head">
                  <span className="publish-drafts-spectrum__eyebrow">{t("publishDraftsIndex.spectrumStatusMix")}</span>
                  <small className="publish-drafts-spectrum__hint">{t("publishDraftsIndex.totalDraftsDetail")}</small>
                </header>
                <p className="publish-drafts-spectrum__total">
                  <b>{totalCount}</b>
                  <em>{t("publishDraftsIndex.totalDrafts")}</em>
                </p>
              </div>

              <ul className="publish-drafts-spectrum__score" aria-label={t("publishDraftsIndex.summary")}>
                {statusLegend.map((slice) => (
                  <li
                    className={`${slice.legendClassName}${slice.count > 0 ? " is-active" : ""}`.trim()}
                    key={slice.key}
                    title={`${slice.detail} · ${slice.pct}%`}
                  >
                    <span>{slice.label}</span>
                    <span aria-hidden="true" className="publish-drafts-spectrum__track">
                      <i className={slice.barClassName} style={{ width: `${totalCount === 0 ? 0 : slice.pct}%` }} />
                    </span>
                    <b>{slice.count}</b>
                    <em>{totalCount === 0 ? "0%" : `${slice.pct}%`}</em>
                  </li>
                ))}
              </ul>
            </div>

            <div
              aria-hidden="true"
              className={`publish-drafts-spectrum__rule ${totalCount === 0 ? "is-empty" : dominantSlice.barClassName}`}
            />

            <div className="publish-drafts-spectrum__metrics is-ticker" aria-label={t("publishDraftsIndex.spectrumSignals")}>
              <span className={attentionCount > 0 ? "publish-drafts-spectrum__metric is-warning" : "publish-drafts-spectrum__metric"}>
                <em>{t("publishDraftsIndex.attention")}</em>
                <b>{attentionCount}</b>
              </span>
              <span className={warningDraftCount > 0 ? "publish-drafts-spectrum__metric is-warning" : "publish-drafts-spectrum__metric"}>
                <em>{t("publishDraftsIndex.spectrumWithWarnings")}</em>
                <b>{warningDraftCount}</b>
              </span>
              <span className="publish-drafts-spectrum__metric">
                <em>{t("publishDraftsIndex.spectrumNextScheduled")}</em>
                <b>
                  {nextScheduledAt ? (
                    <time dateTime={nextScheduledAt}>{formatDateTime(nextScheduledAt)}</time>
                  ) : (
                    t("publishDraftsIndex.spectrumNone")
                  )}
                </b>
              </span>
              <span className="publish-drafts-spectrum__metric">
                <em>{t("publishDraftsIndex.spectrumAccountsInView")}</em>
                <b>{accountCount}</b>
              </span>
              <span className="publish-drafts-spectrum__metric is-freshness">
                <em>{t("publishDraftsIndex.generatedAt")}</em>
                <b>
                  <time dateTime={queue.generated_at}>{formatDateTime(queue.generated_at)}</time>
                </b>
              </span>
            </div>
          </div>
        </section>

        {attention.length > 0 ? (
          <section aria-label={t("publishDraftsIndex.attention")} className="publish-drafts-attention">
            <header>
              <strong>{t("publishDraftsIndex.attention")}</strong>
              <span>{attention.length}</span>
            </header>
            <ul>
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
          </section>
        ) : null}

        <section aria-label={t("publishDraftsIndex.indexTitle")} className="publish-drafts-panel">
          <header className="publish-drafts-panel__head">
            <strong>
              {t("publishDraftsIndex.indexTitle")}
              <em>{drafts.length}</em>
            </strong>
            <nav className="publish-drafts-panel__links" aria-label={t("publishDraftsIndex.triage")}>
              <Link className="publish-drafts-panel__link" href="/publishing/export-packages">
                <DraftsTriageIcon kind="export" />
                <span>{t("nav.exportPackages")}</span>
              </Link>
              <Link className="publish-drafts-panel__link" href="/publishing/publish-handoffs">
                <DraftsTriageIcon kind="handoff" />
                <span>{t("nav.publishHandoffs")}</span>
              </Link>
            </nav>
          </header>
          {drafts.length === 0 ? (
            <div className="publish-drafts-empty">
              <strong>{t("publishDraftsIndex.noReadyDrafts")}</strong>
              <p>{t("publishDraftsIndex.noReadyBody")}</p>
            </div>
          ) : (
            <div className="publish-drafts-ledger">
              <div className="publish-drafts-ledger__head" aria-hidden="true">
                <span>{t("publishDraftsIndex.draft")}</span>
                <span>{t("publishDraftsIndex.signal")}</span>
              </div>
              <ul className="publish-drafts-ledger__body">
                {drafts.map((draft) => (
                  <DraftLedgerRow draft={draft} key={draft.publish_draft_id} t={t} />
                ))}
              </ul>
            </div>
          )}
          <p className="publish-drafts-footnote">{t("publishDraftsIndex.indexDesc")}</p>
        </section>
      </main>
      </AsyncContentBoundary>
    </OperatorStudioShell>
  );
}

function draftAssignmentEdge(assignmentStatus: string, hot: boolean): string {
  if (hot) return "is-hot";
  const value = assignmentStatus.toUpperCase();
  if (value.includes("UNASSIGNED")) return "is-unassigned";
  if (value.includes("SCHEDUL")) return "is-scheduled";
  return "is-assigned";
}

function DraftsTriageIcon({ kind }: { kind: "export" | "handoff" }) {
  if (kind === "export") {
    return (
      <svg aria-hidden="true" className="publish-drafts-panel__link-icon" fill="none" viewBox="0 0 20 20">
        <path
          d="M4.2 6.4 10 3.5l5.8 2.9v6.3L10 16.5 4.2 12.7V6.4Z"
          stroke="currentColor"
          strokeLinejoin="round"
          strokeWidth="1.55"
        />
        <path d="M10 3.5v13" stroke="currentColor" strokeLinecap="round" strokeWidth="1.55" />
        <path d="m4.2 6.4 5.8 2.9 5.8-2.9" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.55" />
      </svg>
    );
  }
  return (
    <svg aria-hidden="true" className="publish-drafts-panel__link-icon" fill="none" viewBox="0 0 20 20">
      <path
        d="M5.2 5.2h6.2a1.4 1.4 0 0 1 1.4 1.4v7.8a1.4 1.4 0 0 1-1.4 1.4H5.2a1.4 1.4 0 0 1-1.4-1.4V6.6a1.4 1.4 0 0 1 1.4-1.4Z"
        stroke="currentColor"
        strokeWidth="1.55"
      />
      <path d="M7.1 8.4h3.8M7.1 11h2.6" stroke="currentColor" strokeLinecap="round" strokeWidth="1.55" />
      <path
        d="M12.2 7.2h1.7a1.9 1.9 0 0 1 1.9 1.9v1.1l1.4-.9v3.4l-1.4-.9v1.1a1.9 1.9 0 0 1-1.9 1.9h-1.7"
        stroke="currentColor"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="1.55"
      />
    </svg>
  );
}

function DraftLedgerRow({ draft, t }: { draft: PublishQueueItem; t: (key: string) => string }) {
  const hot = draft.warnings.length > 0;
  const edge = draftAssignmentEdge(draft.assignment_status, hot);
  const title = draft.title || `${t("publishDraftsIndex.operatorDraft")} ${draft.publish_draft_id.slice(0, 8)}`;
  return (
    <li>
      <Link
        aria-label={`${t("publishDraftsIndex.open")}: ${title}`}
        className={`publish-drafts-ledger__row ${edge}`.trim()}
        href={`/publishing/drafts/${draft.publish_draft_id}`}
      >
        <div className="publish-drafts-ledger__identity">
          <strong className="publish-drafts-ledger__title" title={draft.publish_draft_id}>
            {title}
          </strong>
          <p className="publish-drafts-ledger__meta">
            <span title={draft.recommended_account_name ?? undefined}>
              {draft.recommended_account_name ?? t("publishDraftsIndex.noAccountRecommendation")}
            </span>
            <span aria-hidden="true">·</span>
            <span>{draft.target_platform}</span>
          </p>
        </div>
        <div className="publish-drafts-ledger__signal">
          <span className={`publish-drafts-chip tone-${statusTone(draft.status)}`}>{humanizeStatus(draft.status)}</span>
          <span className={`publish-drafts-chip tone-${hot ? "warn" : statusTone(draft.assignment_status)}`}>{draft.assignment_status}</span>
          <span aria-hidden="true" className="publish-drafts-ledger__open">
            <svg className="publish-drafts-ledger__open-icon" fill="none" viewBox="0 0 20 20">
              <path d="m7.5 4.5 5 5.5-5 5.5" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.8" />
            </svg>
          </span>
        </div>
      </Link>
    </li>
  );
}
