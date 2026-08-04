"use client";

import Link from "next/link";
import { useEffect, useMemo, useState, type ReactNode } from "react";
import { fetchPublishAttemptList, refreshPublishAttemptStatus } from "../../lib/api";
import { useT } from "../../lib/i18n";
import { useAsyncAction } from "../../lib/useAsyncAction";
import { useLatestRequest, type LatestRequestMode } from "../../lib/useLatestRequest";
import type { PublishAttempt } from "../../types/publish-draft";
import { OpsConsoleShell } from "../app-shell/OpsConsoleShell";
import { TopbarRefreshButton } from "../app-shell/TopbarRefreshButton";
import { AsyncButton } from "../shared/AsyncButton";
import { AsyncContentBoundary } from "../shared/AsyncContentBoundary";
import { useNotice } from "../shared/NoticeCenter";
import { OpsState, formatDateTime, statusTone, type OpsTone } from "./OpsShared";

type StatusFilter = "ALL" | "NEEDS" | "RECONCILING";

const RECON_PAGE_SIZE = 20;

function shortId(value: string | null | undefined): string {
  if (!value) return "—";
  return value.length > 8 ? value.slice(0, 8) : value;
}

function formatChipLabel(value: string): string {
  return value
    .split(/[_-]+/)
    .filter(Boolean)
    .map((part) => part.charAt(0) + part.slice(1).toLowerCase())
    .join(" ");
}

function isUnknownExternal(attempt: PublishAttempt): boolean {
  return !attempt.external_status || attempt.external_status === "UNKNOWN";
}

function ReconKpi({
  label,
  value,
  detail,
  tone = "muted",
}: {
  label: string;
  value: string;
  detail: string;
  tone?: OpsTone;
}) {
  return (
    <article className={`ops-recon-kpi tone-${tone}`} title={detail}>
      <em>{label}</em>
      <strong>{value}</strong>
      <span>{detail}</span>
    </article>
  );
}

function ReconPanel({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="ops-recon-panel">
      <div className="ops-recon-panel__head">
        <h2>{title}</h2>
      </div>
      <div className="ops-recon-panel__body">{children}</div>
    </section>
  );
}

function ReconChip({ label, tone }: { label: string; tone: OpsTone }) {
  return <span className={`ops-recon-chip tone-${tone}`}>{formatChipLabel(label)}</span>;
}

export function OpsReconciliationPage() {
  const t = useT();
  const [attempts, setAttempts] = useState<PublishAttempt[]>([]);
  const [actionError, setActionError] = useState<string | null>(null);
  const [loadedAt, setLoadedAt] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("NEEDS");
  const [page, setPage] = useState(1);
  const action = useAsyncAction();
  const request = useLatestRequest();
  const { notify } = useNotice();
  const savingIds = action.pendingKeys;

  async function load(mode: LatestRequestMode = attempts.length ? "refresh" : "initial") {
    await request.run(
      async () => Promise.all([
        fetchPublishAttemptList("NEEDS_RECONCILIATION", 100),
        fetchPublishAttemptList("RECONCILING", 100),
      ]),
      ([needed, reconciling]) => {
        setAttempts([...needed, ...reconciling]);
        setLoadedAt(new Date().toISOString());
      },
      mode
    ).catch(() => undefined);
  }

  async function refresh(attempt: PublishAttempt) {
    await action.run(`refresh-${attempt.id}`, async () => {
      setActionError(null);
      try {
        await refreshPublishAttemptStatus(attempt.id);
        notify({ message: t("opsReconciliation.publishStatusRefreshed"), tone: "success" });
        await load("refresh");
      } catch (err) {
        const message = err instanceof Error ? err.message : t("opsReconciliation.failedToRefresh");
        setActionError(message);
        notify({ message, tone: "error" });
      }
    });
  }

  useEffect(() => {
    void load("initial");
  }, [t]);

  const needsCount = attempts.filter((item) => item.status === "NEEDS_RECONCILIATION").length;
  const reconcilingCount = attempts.filter((item) => item.status === "RECONCILING").length;
  const unknownCount = attempts.filter(isUnknownExternal).length;

  const attentionAttempts = useMemo(
    () => attempts.filter(isUnknownExternal),
    [attempts],
  );

  const visibleAttempts = useMemo(() => {
    if (statusFilter === "NEEDS") return attempts.filter((item) => item.status === "NEEDS_RECONCILIATION");
    if (statusFilter === "RECONCILING") return attempts.filter((item) => item.status === "RECONCILING");
    return attempts;
  }, [attempts, statusFilter]);

  const totalPages = Math.max(1, Math.ceil(visibleAttempts.length / RECON_PAGE_SIZE));
  const safePage = Math.min(page, totalPages);
  const pageStart = (safePage - 1) * RECON_PAGE_SIZE;
  const pagedAttempts = visibleAttempts.slice(pageStart, pageStart + RECON_PAGE_SIZE);
  const pageFrom = visibleAttempts.length === 0 ? 0 : pageStart + 1;
  const pageTo = Math.min(pageStart + RECON_PAGE_SIZE, visibleAttempts.length);

  function applyStatusFilter(next: StatusFilter) {
    setStatusFilter(next);
    setPage(1);
  }

  const filterOptions: Array<{ key: StatusFilter; label: string; count: number }> = [
    { key: "ALL", label: t("opsReconciliation.filterAll"), count: attempts.length },
    { key: "NEEDS", label: t("opsReconciliation.needsReconcile"), count: needsCount },
    { key: "RECONCILING", label: t("opsReconciliation.reconciling"), count: reconcilingCount },
  ];

  const refreshAction = (
    <TopbarRefreshButton busy={request.refreshing} disabled={request.initialLoading} onClick={() => void load("refresh")} />
  );
  const boundaryStatus = request.initialLoading ? "loading" : request.error && attempts.length === 0 ? "error" : "success";
  const inlineError = actionError ?? (attempts.length > 0 ? request.error?.message ?? null : null);

  return (
    <OpsConsoleShell actions={refreshAction} description={t("opsReconciliation.description")} title={t("opsReconciliation.title")}>
      <AsyncContentBoundary
        refreshing={request.refreshing}
        status={boundaryStatus}
        skeletonVariant="table"
        loadingLabel={t("opsReconciliation.loadingDetail")}
        errorState={<OpsState title={t("opsReconciliation.unavailableTitle")} detail={request.error?.message ?? t("opsReconciliation.unavailableTitle")} retry={() => void load("initial")} />}
      >
      <main className="ops-page ops-recon-page">
        {inlineError ? <div className="inline-error">{inlineError}</div> : null}

        <p className="ops-recon-freshness">
          {t("opsReconciliation.loadedAt")}{" "}
          <time dateTime={loadedAt ?? undefined}>{formatDateTime(loadedAt)}</time>
        </p>

        <section className="ops-recon-kpis" aria-label={t("opsReconciliation.title")}>
          <ReconKpi
            label={t("opsReconciliation.needsReconcile")}
            value={String(needsCount)}
            detail={t("opsReconciliation.manualRefreshAdvised")}
            tone={needsCount > 0 ? "warn" : "good"}
          />
          <ReconKpi
            label={t("opsReconciliation.reconciling")}
            value={String(reconcilingCount)}
            detail={t("opsReconciliation.inProgress")}
            tone="muted"
          />
          <ReconKpi
            label={t("opsReconciliation.externalUnknown")}
            value={String(unknownCount)}
            detail={t("opsReconciliation.platformUnclear")}
            tone={unknownCount > 0 ? "warn" : "good"}
          />
        </section>

        <div className="ops-recon-toolbar">
          <nav className="ops-recon-filters" aria-label={t("opsReconciliation.filterLabel")}>
            {filterOptions.map((option) => (
              <button
                key={option.key}
                type="button"
                className={`ops-recon-filter${statusFilter === option.key ? " is-active" : ""}`}
                onClick={() => applyStatusFilter(option.key)}
              >
                {option.label} <strong>{option.count}</strong>
              </button>
            ))}
          </nav>
          <nav className="ops-recon-actions" aria-label={t("opsReconciliation.triage")}>
            <Link href="/ops/publish-health">{t("opsReconciliation.openPublishHealth")}</Link>
            <Link href="/ops/publish-attempts">{t("opsReconciliation.openAttempts")}</Link>
          </nav>
        </div>

        <section className={`ops-recon-main${attentionAttempts.length > 0 ? " has-attention" : ""}`}>
          <ReconPanel title={t("opsReconciliation.attemptsNeedingReconciliation")}>
            {visibleAttempts.length === 0 ? (
              <p className="ops-recon-empty">{t("opsReconciliation.noReconciliationBacklog")}</p>
            ) : (
              <>
                <ul className="ops-recon-sheet">
                  <li className="ops-recon-row is-head" aria-hidden="true">
                    <span>{t("opsReconciliation.attempt")}</span>
                    <span>{t("opsReconciliation.draft")}</span>
                    <span>{t("opsReconciliation.internal")}</span>
                    <span>{t("opsReconciliation.external")}</span>
                    <span>{t("opsReconciliation.externalId")}</span>
                    <span>{t("opsReconciliation.lastChecked")}</span>
                    <span>{t("opsReconciliation.action")}</span>
                  </li>
                  {pagedAttempts.map((attempt) => (
                    <li
                      aria-busy={savingIds.has(`refresh-${attempt.id}`) || undefined}
                      className={`ops-recon-row${isUnknownExternal(attempt) ? " is-hot" : ""}`}
                      key={attempt.id}
                    >
                      <code title={attempt.id}>{shortId(attempt.id)}</code>
                      <Link href={`/publishing/drafts/${attempt.publish_draft_id}`} title={attempt.publish_draft_id}>
                        {shortId(attempt.publish_draft_id)}
                      </Link>
                      <span className="ops-recon-row__badges">
                        <ReconChip label={attempt.status} tone={statusTone(attempt.status)} />
                      </span>
                      <ReconChip
                        label={attempt.external_status ?? "UNKNOWN"}
                        tone={isUnknownExternal(attempt) ? "warn" : statusTone(attempt.external_status)}
                      />
                      <span className="ops-recon-row__id" title={attempt.external_publish_id ?? attempt.external_media_id ?? undefined}>
                        {shortId(attempt.external_publish_id ?? attempt.external_media_id)}
                      </span>
                      <time dateTime={attempt.last_status_checked_at ?? undefined}>
                        {formatDateTime(attempt.last_status_checked_at) ?? t("opsReconciliation.noTimestamp")}
                      </time>
                      <AsyncButton
                        className="ops-recon-row__action"
                        pending={action.isPending(`refresh-${attempt.id}`)}
                        pendingLabel={t("opsReconciliation.refreshing")}
                        onClick={() => void refresh(attempt)}
                      >
                        {t("opsReconciliation.refreshStatus")}
                      </AsyncButton>
                    </li>
                  ))}
                </ul>
                {visibleAttempts.length > RECON_PAGE_SIZE ? (
                  <div className="ops-recon-pager" role="navigation" aria-label={t("opsReconciliation.attemptsNeedingReconciliation")}>
                    <p className="ops-recon-pager__meta">
                      {t("opsReconciliation.pageRange")
                        .replace("{from}", String(pageFrom))
                        .replace("{to}", String(pageTo))
                        .replace("{total}", String(visibleAttempts.length))}
                    </p>
                    <div className="ops-recon-pager__actions">
                      <button type="button" disabled={safePage <= 1} onClick={() => setPage(safePage - 1)}>
                        {t("opsReconciliation.pagePrev")}
                      </button>
                      <button
                        type="button"
                        disabled={safePage >= totalPages}
                        onClick={() => setPage(safePage + 1)}
                      >
                        {t("opsReconciliation.pageNext")}
                      </button>
                    </div>
                  </div>
                ) : null}
              </>
            )}
            <p className="ops-recon-footnote">{t("opsReconciliation.notTrustedUntilRefresh")}</p>
          </ReconPanel>

          {attentionAttempts.length > 0 ? (
            <ReconPanel title={t("opsReconciliation.attention")}>
              <ul className="ops-recon-attention">
                {attentionAttempts.map((attempt) => (
                  <li aria-busy={savingIds.has(`refresh-${attempt.id}`) || undefined} key={attempt.id}>
                    <div>
                      <strong>{shortId(attempt.id)}</strong>
                      <em>
                        {formatChipLabel(attempt.status)} · {t("opsReconciliation.externalUnknown")}
                      </em>
                    </div>
                    <AsyncButton
                      className="ops-recon-row__action"
                      pending={action.isPending(`refresh-${attempt.id}`)}
                      pendingLabel={t("opsReconciliation.refreshing")}
                      onClick={() => void refresh(attempt)}
                    >
                      {t("opsReconciliation.refreshStatus")}
                    </AsyncButton>
                  </li>
                ))}
              </ul>
            </ReconPanel>
          ) : null}
        </section>
      </main>
      </AsyncContentBoundary>
    </OpsConsoleShell>
  );
}
