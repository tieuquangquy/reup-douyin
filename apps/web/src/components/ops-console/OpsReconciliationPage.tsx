"use client";

import Link from "next/link";
import { useEffect, useMemo, useState, type ReactNode } from "react";
import { fetchPublishAttemptList, refreshPublishAttemptStatus } from "../../lib/api";
import { useT } from "../../lib/i18n";
import type { PublishAttempt } from "../../types/publish-draft";
import { OpsConsoleShell } from "../app-shell/OpsConsoleShell";
import { TopbarRefreshButton } from "../app-shell/TopbarRefreshButton";
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
  const [loading, setLoading] = useState(true);
  const [savingId, setSavingId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [loadedAt, setLoadedAt] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("NEEDS");
  const [page, setPage] = useState(1);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const [needed, reconciling] = await Promise.all([
        fetchPublishAttemptList("NEEDS_RECONCILIATION", 100),
        fetchPublishAttemptList("RECONCILING", 100),
      ]);
      setAttempts([...needed, ...reconciling]);
      setLoadedAt(new Date().toISOString());
    } catch (err) {
      setError(err instanceof Error ? err.message : t("opsReconciliation.unavailableTitle"));
    } finally {
      setLoading(false);
    }
  }

  async function refresh(attempt: PublishAttempt) {
    setSavingId(attempt.id);
    setError(null);
    setMessage(null);
    try {
      await refreshPublishAttemptStatus(attempt.id);
      setMessage(t("opsReconciliation.publishStatusRefreshed"));
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : t("opsReconciliation.failedToRefresh"));
    } finally {
      setSavingId(null);
    }
  }

  useEffect(() => {
    void load();
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
    <TopbarRefreshButton busy={loading && attempts.length > 0} disabled={loading && attempts.length === 0} onClick={() => void load()} />
  );

  if (loading && attempts.length === 0) {
    return (
      <OpsConsoleShell actions={refreshAction} description={t("opsReconciliation.description")} title={t("opsReconciliation.title")}>
        <OpsState title={t("opsReconciliation.loadingTitle")} detail={t("opsReconciliation.loadingDetail")} />
      </OpsConsoleShell>
    );
  }

  if (error && attempts.length === 0) {
    return (
      <OpsConsoleShell actions={refreshAction} description={t("opsReconciliation.description")} title={t("opsReconciliation.title")}>
        <OpsState title={t("opsReconciliation.unavailableTitle")} detail={error} retry={() => void load()} />
      </OpsConsoleShell>
    );
  }

  return (
    <OpsConsoleShell actions={refreshAction} description={t("opsReconciliation.description")} title={t("opsReconciliation.title")}>
      <main className="ops-page ops-recon-page">
        {error ? <div className="inline-error">{error}</div> : null}
        {message ? <div className="ops-recon-notice">{message}</div> : null}

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
                      <button
                        type="button"
                        className="ops-recon-row__action"
                        disabled={savingId === attempt.id}
                        onClick={() => void refresh(attempt)}
                      >
                        {savingId === attempt.id ? t("opsReconciliation.refreshing") : t("opsReconciliation.refreshStatus")}
                      </button>
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
                  <li key={attempt.id}>
                    <div>
                      <strong>{shortId(attempt.id)}</strong>
                      <em>
                        {formatChipLabel(attempt.status)} · {t("opsReconciliation.externalUnknown")}
                      </em>
                    </div>
                    <button
                      type="button"
                      className="ops-recon-row__action"
                      disabled={savingId === attempt.id}
                      onClick={() => void refresh(attempt)}
                    >
                      {savingId === attempt.id ? t("opsReconciliation.refreshing") : t("opsReconciliation.refreshStatus")}
                    </button>
                  </li>
                ))}
              </ul>
            </ReconPanel>
          ) : null}
        </section>
      </main>
    </OpsConsoleShell>
  );
}
