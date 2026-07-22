"use client";

import Link from "next/link";
import { useEffect, useMemo, useState, type ReactNode } from "react";
import { fetchPublishAttemptList } from "../../lib/api";
import { useT } from "../../lib/i18n";
import { useLatestRequest } from "../../lib/useLatestRequest";
import type { PublishAttempt } from "../../types/publish-draft";
import { OpsConsoleShell } from "../app-shell/OpsConsoleShell";
import { TopbarRefreshButton } from "../app-shell/TopbarRefreshButton";
import { AsyncContentBoundary } from "../shared/AsyncContentBoundary";
import { useNotice } from "../shared/NoticeCenter";
import { OpsState, formatDateTime, statusTone, type OpsTone } from "./OpsShared";

type StatusFilter = "ALL" | "SUCCEEDED" | "FAILED" | "NEEDS_RECONCILIATION";

const ATTEMPTS_PAGE_SIZE = 20;

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

function isHotAttempt(attempt: PublishAttempt): boolean {
  return attempt.status === "FAILED" || attempt.status === "NEEDS_RECONCILIATION";
}

function AttemptsKpi({
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
    <article className={`ops-attempts-kpi tone-${tone}`} title={detail}>
      <em>{label}</em>
      <strong>{value}</strong>
      <span>{detail}</span>
    </article>
  );
}

function AttemptsPanel({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="ops-attempts-panel">
      <div className="ops-attempts-panel__head">
        <h2>{title}</h2>
      </div>
      <div className="ops-attempts-panel__body">{children}</div>
    </section>
  );
}

function AttemptsChip({ label, tone }: { label: string; tone: OpsTone }) {
  return <span className={`ops-attempts-chip tone-${tone}`}>{formatChipLabel(label)}</span>;
}

export function OpsPublishAttemptsPage() {
  const t = useT();
  const [attempts, setAttempts] = useState<PublishAttempt[]>([]);
  const [loadedAt, setLoadedAt] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("ALL");
  const [page, setPage] = useState(1);
  const request = useLatestRequest();
  const { notify } = useNotice();

  async function load() {
    const mode = loadedAt ? "refresh" : "initial";
    try {
      await request.run(() => fetchPublishAttemptList(undefined, 100), (nextAttempts) => {
        setAttempts(nextAttempts);
        setLoadedAt(new Date().toISOString());
      }, mode);
      if (mode === "refresh") notify({ id: "ops-attempts-refresh", message: "Publish attempts refreshed.", tone: "success" });
    } catch (err) {
      if (mode === "refresh") notify({ id: "ops-attempts-refresh", message: err instanceof Error ? err.message : t("opsPublishAttempts.unavailableTitle"), tone: "error" });
    }
  }

  useEffect(() => {
    void load();
  }, [t]);

  const counts = useMemo(() => {
    return attempts.reduce<Record<string, number>>((acc, attempt) => {
      acc[attempt.status] = (acc[attempt.status] ?? 0) + 1;
      return acc;
    }, {});
  }, [attempts]);

  const attentionAttempts = useMemo(() => attempts.filter(isHotAttempt), [attempts]);

  const visibleAttempts = useMemo(() => {
    if (statusFilter === "ALL") return attempts;
    return attempts.filter((item) => item.status === statusFilter);
  }, [attempts, statusFilter]);

  const totalPages = Math.max(1, Math.ceil(visibleAttempts.length / ATTEMPTS_PAGE_SIZE));
  const safePage = Math.min(page, totalPages);
  const pageStart = (safePage - 1) * ATTEMPTS_PAGE_SIZE;
  const pagedAttempts = visibleAttempts.slice(pageStart, pageStart + ATTEMPTS_PAGE_SIZE);
  const pageFrom = visibleAttempts.length === 0 ? 0 : pageStart + 1;
  const pageTo = Math.min(pageStart + ATTEMPTS_PAGE_SIZE, visibleAttempts.length);

  function applyStatusFilter(next: StatusFilter) {
    setStatusFilter(next);
    setPage(1);
  }

  const filterOptions: Array<{ key: StatusFilter; label: string; count: number }> = [
    { key: "ALL", label: t("opsPublishAttempts.filterAll"), count: attempts.length },
    { key: "SUCCEEDED", label: t("opsPublishAttempts.succeeded"), count: counts.SUCCEEDED ?? 0 },
    { key: "FAILED", label: t("opsPublishAttempts.failed"), count: counts.FAILED ?? 0 },
    {
      key: "NEEDS_RECONCILIATION",
      label: t("opsPublishAttempts.needsReconcile"),
      count: counts.NEEDS_RECONCILIATION ?? 0,
    },
  ];

  const refreshAction = (
    <TopbarRefreshButton busy={request.refreshing} disabled={request.initialLoading} onClick={() => void load()} />
  );

  if (!loadedAt && !request.error) {
    return (
      <OpsConsoleShell actions={refreshAction} description={t("opsPublishAttempts.description")} title={t("opsPublishAttempts.title")}>
        <AsyncContentBoundary skeletonVariant="list" status="loading"><span /></AsyncContentBoundary>
      </OpsConsoleShell>
    );
  }

  if (request.error && !loadedAt) {
    return (
      <OpsConsoleShell actions={refreshAction} description={t("opsPublishAttempts.description")} title={t("opsPublishAttempts.title")}>
        <AsyncContentBoundary errorState={<OpsState title={t("opsPublishAttempts.unavailableTitle")} detail={request.error.message} retry={() => void load()} />} skeletonVariant="list" status="error"><span /></AsyncContentBoundary>
      </OpsConsoleShell>
    );
  }

  return (
    <OpsConsoleShell actions={refreshAction} description={t("opsPublishAttempts.description")} title={t("opsPublishAttempts.title")}>
      <AsyncContentBoundary refreshing={request.refreshing} skeletonVariant="list" status="success">
      <main className="ops-page ops-attempts-page">

        <p className="ops-attempts-freshness">
          {t("opsPublishAttempts.loadedAt")}{" "}
          <time dateTime={loadedAt ?? undefined}>{formatDateTime(loadedAt)}</time>
        </p>

        <section className="ops-attempts-kpis" aria-label={t("opsPublishAttempts.title")}>
          <AttemptsKpi
            label={t("opsPublishAttempts.attempts")}
            value={String(attempts.length)}
            detail={t("opsPublishAttempts.latest100")}
            tone="muted"
          />
          <AttemptsKpi
            label={t("opsPublishAttempts.succeeded")}
            value={String(counts.SUCCEEDED ?? 0)}
            detail={t("opsPublishAttempts.internalSuccess")}
            tone="good"
          />
          <AttemptsKpi
            label={t("opsPublishAttempts.failed")}
            value={String(counts.FAILED ?? 0)}
            detail={t("opsPublishAttempts.internalFailure")}
            tone={(counts.FAILED ?? 0) > 0 ? "danger" : "good"}
          />
          <AttemptsKpi
            label={t("opsPublishAttempts.needsReconcile")}
            value={String(counts.NEEDS_RECONCILIATION ?? 0)}
            detail={t("opsPublishAttempts.uncertainExternal")}
            tone={(counts.NEEDS_RECONCILIATION ?? 0) > 0 ? "warn" : "good"}
          />
        </section>

        <div className="ops-attempts-toolbar">
          <nav className="ops-attempts-filters" aria-label={t("opsPublishAttempts.filterLabel")}>
            {filterOptions.map((option) => (
              <button
                key={option.key}
                type="button"
                className={`ops-attempts-filter${statusFilter === option.key ? " is-active" : ""}`}
                onClick={() => applyStatusFilter(option.key)}
              >
                {option.label} <strong>{option.count}</strong>
              </button>
            ))}
          </nav>
          <nav className="ops-attempts-actions" aria-label={t("opsPublishAttempts.triage")}>
            <Link href="/ops/reconciliation">{t("opsPublishAttempts.openReconciliation")}</Link>
            <Link href="/ops/publish-health">{t("opsPublishAttempts.openPublishHealth")}</Link>
          </nav>
        </div>

        <section className={`ops-attempts-main${attentionAttempts.length > 0 ? " has-attention" : ""}`}>
          <AttemptsPanel title={t("opsPublishAttempts.latestAttempts")}>
            {visibleAttempts.length === 0 ? (
              <p className="ops-attempts-empty">{t("opsPublishAttempts.noPublishAttemptsYet")}</p>
            ) : (
              <>
                <ul className="ops-attempts-sheet">
                  <li className="ops-attempts-row is-head" aria-hidden="true">
                    <span>{t("opsPublishAttempts.attempt")}</span>
                    <span>{t("opsPublishAttempts.draft")}</span>
                    <span>{t("opsPublishAttempts.status")}</span>
                    <span>{t("opsPublishAttempts.external")}</span>
                    <span>{t("opsPublishAttempts.account")}</span>
                    <span>{t("opsPublishAttempts.permalink")}</span>
                    <span>{t("opsPublishAttempts.error")}</span>
                    <span>{t("opsPublishAttempts.checked")}</span>
                  </li>
                  {pagedAttempts.map((attempt) => (
                    <li className={`ops-attempts-row${isHotAttempt(attempt) ? " is-hot" : ""}`} key={attempt.id}>
                      <span title={attempt.id}>
                        #{attempt.attempt_number} {shortId(attempt.id)}
                      </span>
                      <Link href={`/publishing/drafts/${attempt.publish_draft_id}`} title={attempt.publish_draft_id}>
                        {shortId(attempt.publish_draft_id)}
                      </Link>
                      <span className="ops-attempts-row__badges">
                        <AttemptsChip label={attempt.status} tone={statusTone(attempt.status)} />
                      </span>
                      <AttemptsChip
                        label={attempt.external_status ?? "UNKNOWN"}
                        tone={statusTone(attempt.external_status ?? "UNKNOWN")}
                      />
                      <span title={attempt.platform_account_id}>{shortId(attempt.platform_account_id)}</span>
                      {attempt.external_permalink ? (
                        <a href={attempt.external_permalink} target="_blank" rel="noreferrer">
                          {t("opsPublishAttempts.open")}
                        </a>
                      ) : (
                        <span>—</span>
                      )}
                      <span className="ops-attempts-row__error" title={attempt.error_code ?? attempt.error_message ?? undefined}>
                        {attempt.error_code ?? attempt.error_message ?? "—"}
                      </span>
                      <time dateTime={(attempt.last_status_checked_at ?? attempt.updated_at) ?? undefined}>
                        {formatDateTime(attempt.last_status_checked_at ?? attempt.updated_at)}
                      </time>
                    </li>
                  ))}
                </ul>
                {visibleAttempts.length > ATTEMPTS_PAGE_SIZE ? (
                  <div className="ops-attempts-pager" role="navigation" aria-label={t("opsPublishAttempts.latestAttempts")}>
                    <p className="ops-attempts-pager__meta">
                      {t("opsPublishAttempts.pageRange")
                        .replace("{from}", String(pageFrom))
                        .replace("{to}", String(pageTo))
                        .replace("{total}", String(visibleAttempts.length))}
                    </p>
                    <div className="ops-attempts-pager__actions">
                      <button type="button" disabled={safePage <= 1} onClick={() => setPage(safePage - 1)}>
                        {t("opsPublishAttempts.pagePrev")}
                      </button>
                      <button
                        type="button"
                        disabled={safePage >= totalPages}
                        onClick={() => setPage(safePage + 1)}
                      >
                        {t("opsPublishAttempts.pageNext")}
                      </button>
                    </div>
                  </div>
                ) : null}
              </>
            )}
            <p className="ops-attempts-footnote">{t("opsPublishAttempts.latest100Footnote")}</p>
          </AttemptsPanel>

          {attentionAttempts.length > 0 ? (
            <AttemptsPanel title={t("opsPublishAttempts.attention")}>
              <ul className="ops-attempts-attention">
                {attentionAttempts.map((attempt) => (
                  <li key={attempt.id}>
                    <div>
                      <strong>
                        #{attempt.attempt_number} {shortId(attempt.id)}
                      </strong>
                      <em>{formatChipLabel(attempt.status)}</em>
                    </div>
                    <Link href={`/publishing/drafts/${attempt.publish_draft_id}`}>{t("opsPublishAttempts.openDraft")}</Link>
                  </li>
                ))}
              </ul>
            </AttemptsPanel>
          ) : null}
        </section>
      </main>
      </AsyncContentBoundary>
    </OpsConsoleShell>
  );
}
