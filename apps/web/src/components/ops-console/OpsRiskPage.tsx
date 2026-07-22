"use client";

import Link from "next/link";
import { useEffect, useMemo, useState, type ReactNode } from "react";
import { fetchRiskFlags } from "../../lib/api";
import { useT } from "../../lib/i18n";
import { useLatestRequest } from "../../lib/useLatestRequest";
import type { RiskFlag, RiskFlagStatus, RiskSeverity } from "../../types/risk";
import { OpsConsoleShell } from "../app-shell/OpsConsoleShell";
import { TopbarRefreshButton } from "../app-shell/TopbarRefreshButton";
import { AsyncContentBoundary } from "../shared/AsyncContentBoundary";
import { useNotice } from "../shared/NoticeCenter";
import { OpsState, formatDateTime, statusTone, type OpsTone } from "./OpsShared";

type StatusFilter = "ALL" | RiskFlagStatus;

const RISK_PAGE_SIZE = 20;

const SEVERITY_RANK: Record<RiskSeverity, number> = {
  BLOCKING: 0,
  CRITICAL: 1,
  HIGH: 2,
  MEDIUM: 3,
  LOW: 4,
};

const STATUS_RANK: Record<RiskFlagStatus, number> = {
  OPEN: 0,
  ACKNOWLEDGED: 1,
  WAIVED: 2,
  REJECTED: 3,
  RESOLVED: 4,
};

function isHotSeverity(severity: string): boolean {
  return severity === "BLOCKING" || severity === "CRITICAL";
}

function shortId(value: string | null | undefined): string {
  if (!value) return "—";
  return value.length > 8 ? value.slice(0, 8) : value;
}

function sortFlags(a: RiskFlag, b: RiskFlag): number {
  const statusDelta = (STATUS_RANK[a.status] ?? 99) - (STATUS_RANK[b.status] ?? 99);
  if (statusDelta !== 0) return statusDelta;
  const severityDelta = (SEVERITY_RANK[a.severity] ?? 99) - (SEVERITY_RANK[b.severity] ?? 99);
  if (severityDelta !== 0) return severityDelta;
  const aTime = a.detected_at ? Date.parse(a.detected_at) : 0;
  const bTime = b.detected_at ? Date.parse(b.detected_at) : 0;
  return bTime - aTime;
}

function RiskKpi({
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
    <article className={`ops-risk-kpi tone-${tone}`} title={detail}>
      <em>{label}</em>
      <strong>{value}</strong>
      <span>{detail}</span>
    </article>
  );
}

function RiskPanel({
  title,
  action,
  children,
}: {
  title: string;
  action?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className="ops-risk-panel">
      <div className="ops-risk-panel__head">
        <h2>{title}</h2>
        {action}
      </div>
      <div className="ops-risk-panel__body">{children}</div>
    </section>
  );
}

function riskChipTone(kind: "severity" | "status", value: string): OpsTone {
  const key = value.toUpperCase();
  if (kind === "severity") {
    if (key === "BLOCKING" || key === "CRITICAL") return "danger";
    if (key === "HIGH") return "warn";
    if (key === "MEDIUM") return "warn";
    if (key === "LOW") return "muted";
    return statusTone(value);
  }
  if (key === "OPEN" || key === "ACKNOWLEDGED") return "warn";
  if (key === "WAIVED" || key === "REJECTED") return key === "REJECTED" ? "danger" : "warn";
  if (key === "RESOLVED") return "good";
  return statusTone(value);
}

function formatChipLabel(value: string): string {
  return value
    .split(/[_-]+/)
    .filter(Boolean)
    .map((part) => part.charAt(0) + part.slice(1).toLowerCase())
    .join(" ");
}

function RiskChip({ label, tone }: { label: string; tone: OpsTone }) {
  return <span className={`ops-risk-chip tone-${tone}`}>{formatChipLabel(label)}</span>;
}

export function OpsRiskPage() {
  const t = useT();
  const [flags, setFlags] = useState<RiskFlag[]>([]);
  const [loadedAt, setLoadedAt] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("OPEN");
  const [page, setPage] = useState(1);
  const request = useLatestRequest();
  const { notify } = useNotice();

  async function load() {
    const mode = loadedAt ? "refresh" : "initial";
    try {
      await request.run(async () => {
        const [open, acknowledged, waived, resolved, rejected] = await Promise.all([
          fetchRiskFlags("OPEN"),
          fetchRiskFlags("ACKNOWLEDGED"),
          fetchRiskFlags("WAIVED"),
          fetchRiskFlags("RESOLVED"),
          fetchRiskFlags("REJECTED"),
        ]);
        return [...open, ...acknowledged, ...waived, ...resolved, ...rejected];
      }, (nextFlags) => {
        setFlags(nextFlags);
        setLoadedAt(new Date().toISOString());
      }, mode);
      if (mode === "refresh") notify({ id: "ops-risk-refresh", message: "Risk flags refreshed.", tone: "success" });
    } catch (err) {
      if (mode === "refresh") notify({ id: "ops-risk-refresh", message: err instanceof Error ? err.message : t("opsRisk.unavailableTitle"), tone: "error" });
    }
  }

  useEffect(() => {
    void load();
  }, [t]);

  const counts = useMemo(() => {
    const byStatus: Record<string, number> = {};
    let openBlockingCritical = 0;
    for (const flag of flags) {
      byStatus[flag.status] = (byStatus[flag.status] ?? 0) + 1;
      if (flag.status === "OPEN" && isHotSeverity(flag.severity)) {
        openBlockingCritical += 1;
      }
    }
    return {
      open: byStatus.OPEN ?? 0,
      acknowledged: byStatus.ACKNOWLEDGED ?? 0,
      waived: byStatus.WAIVED ?? 0,
      resolved: byStatus.RESOLVED ?? 0,
      rejected: byStatus.REJECTED ?? 0,
      openBlockingCritical,
    };
  }, [flags]);

  const attentionFlags = useMemo(
    () =>
      flags
        .filter((flag) => flag.status === "OPEN" && isHotSeverity(flag.severity))
        .sort(sortFlags),
    [flags],
  );

  const visibleFlags = useMemo(() => {
    const filtered = statusFilter === "ALL" ? flags : flags.filter((flag) => flag.status === statusFilter);
    return [...filtered].sort(sortFlags);
  }, [flags, statusFilter]);

  const totalPages = Math.max(1, Math.ceil(visibleFlags.length / RISK_PAGE_SIZE));
  const safePage = Math.min(page, totalPages);
  const pageStart = (safePage - 1) * RISK_PAGE_SIZE;
  const pagedFlags = visibleFlags.slice(pageStart, pageStart + RISK_PAGE_SIZE);
  const pageFrom = visibleFlags.length === 0 ? 0 : pageStart + 1;
  const pageTo = Math.min(pageStart + RISK_PAGE_SIZE, visibleFlags.length);

  function applyStatusFilter(next: StatusFilter) {
    setStatusFilter(next);
    setPage(1);
  }

  const filterOptions: Array<{ key: StatusFilter; label: string; count: number }> = [
    { key: "ALL", label: t("opsRisk.filterAll"), count: flags.length },
    { key: "OPEN", label: t("opsRisk.open"), count: counts.open },
    { key: "ACKNOWLEDGED", label: t("opsRisk.acknowledged"), count: counts.acknowledged },
    { key: "WAIVED", label: t("opsRisk.waived"), count: counts.waived },
    { key: "RESOLVED", label: t("opsRisk.resolved"), count: counts.resolved },
  ];
  if (counts.rejected > 0) {
    filterOptions.push({ key: "REJECTED", label: t("opsRisk.rejected"), count: counts.rejected });
  }

  const refreshAction = (
    <TopbarRefreshButton busy={request.refreshing} disabled={request.initialLoading} onClick={() => void load()} />
  );

  if (!loadedAt && !request.error) {
    return (
      <OpsConsoleShell actions={refreshAction} description={t("opsRisk.description")} title={t("opsRisk.title")}>
        <AsyncContentBoundary skeletonVariant="list" status="loading"><span /></AsyncContentBoundary>
      </OpsConsoleShell>
    );
  }

  if (request.error && !loadedAt) {
    return (
      <OpsConsoleShell actions={refreshAction} description={t("opsRisk.description")} title={t("opsRisk.title")}>
        <AsyncContentBoundary errorState={<OpsState title={t("opsRisk.unavailableTitle")} detail={request.error.message} retry={() => void load()} />} skeletonVariant="list" status="error"><span /></AsyncContentBoundary>
      </OpsConsoleShell>
    );
  }

  return (
    <OpsConsoleShell actions={refreshAction} description={t("opsRisk.description")} title={t("opsRisk.title")}>
      <AsyncContentBoundary refreshing={request.refreshing} skeletonVariant="list" status="success">
      <main className="ops-page ops-risk-page">

        <p className="ops-risk-freshness">
          {t("opsRisk.loadedAt")}{" "}
          <time dateTime={loadedAt ?? undefined}>{formatDateTime(loadedAt)}</time>
        </p>

        <section className="ops-risk-kpis" aria-label={t("opsRisk.title")}>
          <RiskKpi
            label={t("opsRisk.open")}
            value={String(counts.open)}
            detail={t("opsRisk.needsOperatorAttention")}
            tone={counts.open > 0 ? "warn" : "good"}
          />
          <RiskKpi
            label={t("opsRisk.blockingCritical")}
            value={String(counts.openBlockingCritical)}
            detail={t("opsRisk.highestRiskSeverities")}
            tone={counts.openBlockingCritical > 0 ? "danger" : "good"}
          />
          <RiskKpi
            label={t("opsRisk.acknowledged")}
            value={String(counts.acknowledged)}
            detail={t("opsRisk.seenNotResolved")}
            tone="muted"
          />
          <RiskKpi
            label={t("opsRisk.waived")}
            value={String(counts.waived)}
            detail={t("opsRisk.operatorOverrideRecorded")}
            tone={counts.waived > 0 ? "warn" : "muted"}
          />
          <RiskKpi
            label={t("opsRisk.resolved")}
            value={String(counts.resolved)}
            detail={t("opsRisk.closedWarnings")}
            tone="good"
          />
        </section>

        <div className="ops-risk-toolbar">
          <nav className="ops-risk-filters" aria-label={t("opsRisk.filterLabel")}>
            {filterOptions.map((option) => (
              <button
                key={option.key}
                type="button"
                className={`ops-risk-filter${statusFilter === option.key ? " is-active" : ""}`}
                onClick={() => applyStatusFilter(option.key)}
              >
                {option.label} <strong>{option.count}</strong>
              </button>
            ))}
          </nav>
          <nav className="ops-risk-actions" aria-label={t("opsRisk.triage")}>
            <Link href="/ops/health">{t("opsRisk.openHealth")}</Link>
            <Link href="/ops">{t("opsRisk.openHome")}</Link>
          </nav>
        </div>

        <section className={`ops-risk-main${attentionFlags.length > 0 ? " has-attention" : ""}`}>
          <RiskPanel title={t("opsRisk.flags")}>
            {visibleFlags.length === 0 ? (
              <p className="ops-risk-empty">{t("opsRisk.noRiskFlagsFound")}</p>
            ) : (
              <>
                <ul className="ops-risk-flags">
                  <li className="ops-risk-row is-head" aria-hidden="true">
                    <span>{t("opsRisk.flag")}</span>
                    <span>{t("opsRisk.target")}</span>
                    <span>
                      {t("opsRisk.severity")} / {t("opsRisk.status")}
                    </span>
                    <span>{t("opsRisk.evidence")}</span>
                    <span>{t("opsRisk.detected")}</span>
                    <span>{t("opsRisk.action")}</span>
                  </li>
                  {pagedFlags.map((flag) => {
                    const reviewHref = flag.source_video_id
                      ? `/source-videos/${flag.source_video_id}/final-review`
                      : null;
                    return (
                      <li
                        className={`ops-risk-row${flag.status === "OPEN" && isHotSeverity(flag.severity) ? " is-hot" : ""}`}
                        key={flag.id}
                      >
                        <strong className="ops-risk-row__title" title={flag.title ?? flag.flag_type}>
                          {flag.title ?? flag.flag_type}
                        </strong>
                        <span className="ops-risk-row__target" title={`${flag.target_type} ${flag.target_id ?? ""}`}>
                          {flag.target_type} {shortId(flag.target_id)}
                        </span>
                        <span className="ops-risk-row__badges">
                          <RiskChip label={flag.severity} tone={riskChipTone("severity", flag.severity)} />
                          <RiskChip label={flag.status} tone={riskChipTone("status", flag.status)} />
                        </span>
                        <span className="ops-risk-row__evidence" title={flag.evidence_summary ?? flag.description ?? undefined}>
                          {flag.evidence_summary ?? flag.description ?? "—"}
                        </span>
                        <time dateTime={flag.detected_at ?? undefined}>{formatDateTime(flag.detected_at)}</time>
                        {reviewHref ? (
                          <Link className="ops-risk-row__link" href={reviewHref}>
                            {t("opsRisk.openFinalReview")}
                          </Link>
                        ) : (
                          <span className="ops-risk-row__link is-muted">—</span>
                        )}
                      </li>
                    );
                  })}
                </ul>
                {visibleFlags.length > RISK_PAGE_SIZE ? (
                  <div className="ops-risk-pager" role="navigation" aria-label={t("opsRisk.flags")}>
                    <p className="ops-risk-pager__meta">
                      {t("opsRisk.pageRange")
                        .replace("{from}", String(pageFrom))
                        .replace("{to}", String(pageTo))
                        .replace("{total}", String(visibleFlags.length))}
                    </p>
                    <div className="ops-risk-pager__actions">
                      <button type="button" disabled={safePage <= 1} onClick={() => setPage(safePage - 1)}>
                        {t("opsRisk.pagePrev")}
                      </button>
                      <button
                        type="button"
                        disabled={safePage >= totalPages}
                        onClick={() => setPage(safePage + 1)}
                      >
                        {t("opsRisk.pageNext")}
                      </button>
                    </div>
                  </div>
                ) : null}
              </>
            )}
            <p className="ops-risk-footnote">{t("opsRisk.decisionAtFinalReview")}</p>
          </RiskPanel>

          {attentionFlags.length > 0 ? (
            <RiskPanel title={t("opsRisk.attention")}>
              <ul className="ops-risk-attention">
                {attentionFlags.map((flag) => (
                  <li key={flag.id}>
                    <div>
                      <strong>{flag.title ?? flag.flag_type}</strong>
                      <em>
                        {flag.severity} · {shortId(flag.target_id)}
                      </em>
                    </div>
                    {flag.source_video_id ? (
                      <Link href={`/source-videos/${flag.source_video_id}/final-review`}>
                        {t("opsRisk.openFinalReview")}
                      </Link>
                    ) : null}
                  </li>
                ))}
              </ul>
            </RiskPanel>
          ) : null}
        </section>
      </main>
      </AsyncContentBoundary>
    </OpsConsoleShell>
  );
}
