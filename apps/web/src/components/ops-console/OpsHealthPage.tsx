"use client";

import Link from "next/link";
import { useEffect, useState, type ReactNode } from "react";
import { fetchOperationalMetrics, fetchPublishHealthDashboard } from "../../lib/api";
import { useT } from "../../lib/i18n";
import { useLatestRequest } from "../../lib/useLatestRequest";
import type { PublishDayStats, PublishHealthDashboard } from "../../types/analytics";
import type {
  OperationalMetrics,
  OpsAssetReuseSummary,
  OpsFetchHealthAccountSummary,
} from "../../types/operations";
import { OpsConsoleShell } from "../app-shell/OpsConsoleShell";
import { TopbarRefreshButton } from "../app-shell/TopbarRefreshButton";
import { AsyncContentBoundary } from "../shared/AsyncContentBoundary";
import { useNotice } from "../shared/NoticeCenter";
import { OpsState, formatDateTime, sumRecord, type OpsTone } from "./OpsShared";

function formatStatusChipLabel(status: string): string {
  return status
    .split(/[_-]+/)
    .filter(Boolean)
    .map((part) => part.charAt(0) + part.slice(1).toLowerCase())
    .join(" ");
}

function countEntries(record: Record<string, number> | null | undefined): Array<{ key: string; count: number }> {
  if (!record) return [];
  return Object.entries(record)
    .map(([key, count]) => ({ key, count: Number(count) || 0 }))
    .sort((a, b) => b.count - a.count || a.key.localeCompare(b.key));
}

function formatSeconds(value: number): string {
  if (!Number.isFinite(value) || value <= 0) return "—";
  if (value < 60) return `${Math.round(value)}s`;
  const minutes = value / 60;
  if (minutes < 60) return `${minutes.toFixed(1)}m`;
  return `${(minutes / 60).toFixed(1)}h`;
}

function formatDayLabel(day: string): string {
  const date = new Date(`${day}T12:00:00`);
  if (Number.isNaN(date.getTime())) return day.slice(-5);
  return date.toLocaleDateString(undefined, { weekday: "short", day: "numeric" });
}

function shortId(value: string | null | undefined): string {
  if (!value) return "—";
  return value.length > 10 ? `${value.slice(0, 8)}…` : value;
}

function riskTone(severity: string): OpsTone {
  const key = severity.toUpperCase();
  if (["CRITICAL", "HIGH", "BLOCKING"].includes(key)) return "danger";
  if (["MEDIUM", "WARN", "WARNING", "MODERATE"].includes(key)) return "warn";
  if (["LOW", "INFO"].includes(key)) return "muted";
  return "warn";
}

function buildJobMatrix(
  record: Record<string, Record<string, number>> | null | undefined,
  limit = 6,
): { rows: Array<{ jobType: string; statuses: Record<string, number>; total: number }>; columns: string[] } {
  if (!record) return { rows: [], columns: [] };
  const rows = Object.entries(record)
    .map(([jobType, statuses]) => {
      const total = Object.values(statuses).reduce((sum, n) => sum + (Number(n) || 0), 0);
      return { jobType, statuses, total };
    })
    .filter((row) => row.total > 0)
    .sort((a, b) => b.total - a.total || a.jobType.localeCompare(b.jobType))
    .slice(0, limit);

  const preferred = ["RUNNING", "QUEUED", "RETRYABLE", "FAILED", "COMPLETED", "WAITING_FOR_REVIEW"];
  const seen = new Set<string>();
  for (const row of rows) {
    for (const key of Object.keys(row.statuses)) {
      if ((Number(row.statuses[key]) || 0) > 0) seen.add(key);
    }
  }
  const columns = [
    ...preferred.filter((status) => seen.has(status)),
    ...[...seen].filter((status) => !preferred.includes(status)).sort(),
  ].slice(0, 6);

  return { rows, columns };
}

function topFetchAccounts(accounts: OpsFetchHealthAccountSummary[] | undefined, limit = 3): OpsFetchHealthAccountSummary[] {
  if (!accounts?.length) return [];
  return [...accounts]
    .sort(
      (a, b) =>
        b.blocked_runs + b.failed_runs - (a.blocked_runs + a.failed_runs) ||
        b.runs_total - a.runs_total ||
        (a.douyin_account_connection_id ?? "").localeCompare(b.douyin_account_connection_id ?? ""),
    )
    .slice(0, limit);
}

function HealthKpiCard({
  label,
  value,
  tone = "muted",
  badge,
  title,
  href,
}: {
  label: string;
  value: string;
  tone?: OpsTone;
  badge: string;
  title?: string;
  href?: string;
}) {
  const body = (
    <>
      <div className="ops-health-card__top">
        <em className="ops-health-card__label">{label}</em>
        <span className={`ops-health-card__badge tone-${tone}`}>{badge}</span>
      </div>
      <strong className="ops-health-card__value">{value}</strong>
    </>
  );
  if (href) {
    return (
      <Link className={`ops-health-card is-link tone-${tone}`} href={href} title={title}>
        {body}
      </Link>
    );
  }
  return (
    <article className={`ops-health-card tone-${tone}`} title={title}>
      {body}
    </article>
  );
}

function HealthPanel({
  title,
  children,
  action,
}: {
  title: string;
  children: ReactNode;
  action?: ReactNode;
}) {
  return (
    <section className="ops-health-panel">
      <div className="ops-health-panel__head">
        <h2>{title}</h2>
        {action}
      </div>
      <div className="ops-health-panel__body">{children}</div>
    </section>
  );
}

function StatusChips({
  record,
  emptyLabel,
  limit,
}: {
  record: Record<string, number> | null | undefined;
  emptyLabel: string;
  limit?: number;
}) {
  const entries = countEntries(record).slice(0, limit ?? 8);
  const raw = record ? JSON.stringify(record) : undefined;
  if (entries.length === 0) {
    return (
      <span className="ops-health-chips is-empty" title={raw}>
        {emptyLabel}
      </span>
    );
  }
  return (
    <span className="ops-health-chips" title={raw}>
      {entries.map((item) => (
        <span className="ops-health-chip" key={item.key}>
          <em>{formatStatusChipLabel(item.key)}</em>
          <strong>{item.count}</strong>
        </span>
      ))}
    </span>
  );
}

function Stat({ label, value }: { label: string; value: string | number }) {
  return (
    <span className="ops-health-stat">
      <em>{label}</em>
      <strong>{value}</strong>
    </span>
  );
}

function MeterList({
  entries,
  toneFor,
  formatValue,
  maxMode = "relative",
}: {
  entries: Array<{ key: string; count: number }>;
  toneFor?: (key: string) => OpsTone;
  formatValue?: (value: number) => string;
  maxMode?: "relative" | "percent";
}) {
  const peak = Math.max(...entries.map((item) => item.count), maxMode === "percent" ? 100 : 1);
  return (
    <div className="ops-health-meters">
      {entries.map((item) => {
        const width = Math.max(0, Math.min(100, (item.count / peak) * 100));
        const tone = toneFor?.(item.key) ?? "warn";
        return (
          <div className="ops-health-meter" key={item.key}>
            <div className="ops-health-meter__label">
              <em>{formatStatusChipLabel(item.key)}</em>
              <strong>{formatValue ? formatValue(item.count) : item.count}</strong>
            </div>
            <div className="ops-health-meter__track" aria-hidden="true">
              <span className={`ops-health-meter__fill tone-${tone}`} style={{ width: `${width}%` }} />
            </div>
          </div>
        );
      })}
    </div>
  );
}

function QueueMixBar({
  queued,
  running,
  retryable,
  labels,
}: {
  queued: number;
  running: number;
  retryable: number;
  labels: { queued: string; running: string; retryable: string };
}) {
  const total = queued + running + retryable;
  if (total <= 0) {
    return <p className="ops-health-empty">—</p>;
  }
  const parts = [
    { key: "queued", value: queued, label: labels.queued, tone: "muted" as const },
    { key: "running", value: running, label: labels.running, tone: "good" as const },
    { key: "retryable", value: retryable, label: labels.retryable, tone: "warn" as const },
  ].filter((part) => part.value > 0);

  return (
    <div className="ops-health-queue-mix" aria-label={`${labels.queued} ${queued}, ${labels.running} ${running}, ${labels.retryable} ${retryable}`}>
      <div className="ops-health-queue-mix__bar" aria-hidden="true">
        {parts.map((part) => (
          <span
            key={part.key}
            className={`ops-health-queue-mix__seg tone-${part.tone}`}
            style={{ flexGrow: part.value, flexBasis: 0 }}
            title={`${part.label}: ${part.value}`}
          />
        ))}
      </div>
      <div className="ops-health-queue-mix__legend">
        {parts.map((part) => (
          <span key={part.key}>
            <i className={`tone-${part.tone}`} />
            {part.label} <strong>{part.value}</strong>
          </span>
        ))}
      </div>
    </div>
  );
}

function PublishWeekChart({
  days,
  emptyLabel,
}: {
  days: PublishDayStats[];
  emptyLabel: string;
}) {
  if (days.length === 0) {
    return <p className="ops-health-empty">{emptyLabel}</p>;
  }
  const maxAttempts = Math.max(...days.map((day) => day.attempts), 1);
  return (
    <div className="ops-health-week" role="img" aria-label={days.map((d) => `${d.day}: ${d.attempts}`).join(", ")}>
      {days.map((day) => {
        const height = Math.max(8, Math.round((day.attempts / maxAttempts) * 100));
        const successShare = day.attempts > 0 ? (day.succeeded / day.attempts) * 100 : 0;
        const failShare = day.attempts > 0 ? (day.failed / day.attempts) * 100 : 0;
        return (
          <div className="ops-health-daybar" key={day.day} title={`${day.day}: ${day.attempts} · ✓${day.succeeded} · ✕${day.failed}`}>
            <div className="ops-health-daybar__col" style={{ height: `${height}%` }}>
              {day.attempts > 0 ? (
                <>
                  <span className="ops-health-daybar__seg is-ok" style={{ flexGrow: Math.max(successShare, 0.01) }} />
                  <span className="ops-health-daybar__seg is-fail" style={{ flexGrow: Math.max(failShare, day.failed > 0 ? 0.01 : 0) }} />
                  <span
                    className="ops-health-daybar__seg is-other"
                    style={{ flexGrow: Math.max(100 - successShare - failShare, 0) }}
                  />
                </>
              ) : (
                <span className="ops-health-daybar__seg is-empty" style={{ flexGrow: 1 }} />
              )}
            </div>
            <em>{formatDayLabel(day.day)}</em>
            <strong>{day.attempts}</strong>
          </div>
        );
      })}
    </div>
  );
}

function AssetReuseList({
  assets,
  emptyLabel,
}: {
  assets: OpsAssetReuseSummary[];
  emptyLabel: string;
}) {
  if (assets.length === 0) {
    return <p className="ops-health-empty">{emptyLabel}</p>;
  }
  return (
    <ul className="ops-health-assets">
      {assets.map((asset) => (
        <li className="ops-health-asset" key={asset.asset_type}>
          <code>{asset.asset_type}</code>
          <span>
            <strong>{asset.current_count}</strong>
            <em> / {asset.historical_count}</em>
          </span>
        </li>
      ))}
    </ul>
  );
}

function FetchAccountList({
  accounts,
  emptyLabel,
}: {
  accounts: OpsFetchHealthAccountSummary[];
  emptyLabel: string;
}) {
  if (accounts.length === 0) {
    return <p className="ops-health-empty">{emptyLabel}</p>;
  }
  return (
    <ul className="ops-health-accounts">
      {accounts.map((account) => {
        const id = account.douyin_account_connection_id ?? "unknown";
        return (
          <li className="ops-health-account" key={id}>
            <code title={account.douyin_account_connection_id ?? undefined}>{shortId(account.douyin_account_connection_id)}</code>
            <span>
              {account.runs_total} · blocked {account.blocked_runs} · fail {account.failed_runs}
            </span>
          </li>
        );
      })}
    </ul>
  );
}

function JobMatrixTable({
  rows,
  columns,
  emptyLabel,
  typeLabel,
  totalLabel,
}: {
  rows: Array<{ jobType: string; statuses: Record<string, number>; total: number }>;
  columns: string[];
  emptyLabel: string;
  typeLabel: string;
  totalLabel: string;
}) {
  if (rows.length === 0 || columns.length === 0) {
    return <p className="ops-health-empty">{emptyLabel}</p>;
  }
  return (
    <div className="ops-health-matrix-wrap">
      <table className="ops-health-matrix">
        <thead>
          <tr>
            <th>{typeLabel}</th>
            {columns.map((column) => (
              <th key={column}>{formatStatusChipLabel(column)}</th>
            ))}
            <th>{totalLabel}</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.jobType}>
              <th scope="row" title={row.jobType}>
                {formatStatusChipLabel(row.jobType)}
              </th>
              {columns.map((column) => (
                <td key={column}>{row.statuses[column] ? row.statuses[column] : "—"}</td>
              ))}
              <td>
                <strong>{row.total}</strong>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function OpsHealthPage() {
  const t = useT();
  const [metrics, setMetrics] = useState<OperationalMetrics | null>(null);
  const [publishHealth, setPublishHealth] = useState<PublishHealthDashboard | null>(null);
  const request = useLatestRequest();
  const { notify } = useNotice();

  async function load() {
    const mode = metrics ? "refresh" : "initial";
    try {
      await request.run(async () => {
        const [metricsPayload, healthPayload] = await Promise.all([
          fetchOperationalMetrics(),
          fetchPublishHealthDashboard("last_7_days"),
        ]);
        return { metricsPayload, healthPayload };
      }, ({ metricsPayload, healthPayload }) => {
        setMetrics(metricsPayload);
        setPublishHealth(healthPayload);
      }, mode);
      if (mode === "refresh") notify({ id: "ops-health-refresh", message: "Ops health refreshed.", tone: "success" });
    } catch (err) {
      if (mode === "refresh") notify({ id: "ops-health-refresh", message: err instanceof Error ? err.message : t("opsHealth.unavailableTitle"), tone: "error" });
    }
  }

  useEffect(() => {
    void load();
  }, [t]);

  const refreshAction = (
    <TopbarRefreshButton busy={request.refreshing} disabled={request.initialLoading} onClick={() => void load()} />
  );

  if (!metrics && !request.error) {
    return (
      <OpsConsoleShell actions={refreshAction} description={t("opsHealth.description")} title={t("opsHealth.title")}>
        <AsyncContentBoundary skeletonVariant="gallery" status="loading"><span /></AsyncContentBoundary>
      </OpsConsoleShell>
    );
  }

  if (request.error && !metrics) {
    return (
      <OpsConsoleShell actions={refreshAction} description={t("opsHealth.description")} title={t("opsHealth.title")}>
        <AsyncContentBoundary errorState={<OpsState title={t("opsHealth.unavailableTitle")} detail={request.error.message} retry={() => void load()} />} skeletonVariant="gallery" status="error"><span /></AsyncContentBoundary>
      </OpsConsoleShell>
    );
  }

  const riskOpen = metrics ? sumRecord(metrics.open_risk_counts_by_severity) : 0;
  const workerActive = metrics ? metrics.queue_backlog.running > 0 : false;
  const fetchHealth = metrics?.douyin_fetch_health;
  const failureCategories = (metrics?.common_failure_categories ?? []).slice(0, 5);
  const riskEntries = metrics ? countEntries(metrics.open_risk_counts_by_severity) : [];
  const failureRates = metrics ? countEntries(metrics.job_failure_rate_percent_by_type).slice(0, 5) : [];
  const avgProcessing = metrics?.average_processing_seconds_per_source_video ?? 0;
  const topBlocked = fetchHealth?.top_blocked_reasons.slice(0, 3) ?? [];
  const publishDays = publishHealth?.by_day ?? [];
  const publishOverview = publishHealth ? publishHealth.overview : null;
  const assetRows = [...(metrics?.asset_reuse_by_type ?? [])]
    .sort((a, b) => b.current_count - a.current_count || a.asset_type.localeCompare(b.asset_type))
    .slice(0, 5);
  const fetchAccounts = topFetchAccounts(fetchHealth?.by_account, 3);
  const jobMatrix = buildJobMatrix(metrics?.job_counts_by_type_status, 6);
  const assetCurrentTotal = (metrics?.asset_reuse_by_type ?? []).reduce((sum, row) => sum + row.current_count, 0);

  return (
    <OpsConsoleShell actions={refreshAction} description={t("opsHealth.description")} title={t("opsHealth.title")}>
      <AsyncContentBoundary refreshing={request.refreshing} skeletonVariant="gallery" status="success">
      <main className="ops-page ops-health-page is-dense">
        {metrics ? (
          <>
            <p className="ops-health-freshness is-inline">
              <span>{t("opsHealth.metricsGenerated")}</span>
              <time dateTime={metrics.generated_at} title={metrics.generated_at}>
                {formatDateTime(metrics.generated_at)}
              </time>
            </p>

            <nav className="ops-health-actions" aria-label={t("opsHealth.triageActions")}>
              <Link href="/ops/jobs?status=RUNNING">{t("opsHealth.openRunning")}</Link>
              <Link href="/ops/jobs?status=FAILED">{t("opsHealth.openFailed")}</Link>
              <Link href="/ops/jobs?status=RETRYABLE">{t("opsHealth.openRetryable")}</Link>
              <Link href="/ops/risk">{t("opsHealth.openRisk")}</Link>
              <Link href="/ops/publish-health">{t("opsHealth.openPublishHealth")}</Link>
            </nav>

            <section className="ops-health-kpis" aria-label={t("opsHealth.title")}>
              <HealthKpiCard
                label={t("opsHealth.api")}
                value={t("opsHealth.reachable")}
                title={t("opsHealth.loadedOpsMetrics")}
                tone="good"
                badge={t("opsHealth.badgeHealthy")}
              />
              <HealthKpiCard
                label={t("opsHealth.db")}
                value={t("opsHealth.reachable")}
                title={t("opsHealth.metricsQueryCompleted")}
                tone="good"
                badge={t("opsHealth.badgeHealthy")}
              />
              <HealthKpiCard
                label={t("opsHealth.worker")}
                value={workerActive ? t("opsHealth.active") : t("opsHealth.noActiveJobs")}
                title={`${metrics.queue_backlog.running} ${t("opsHealth.runningJobs")}`}
                tone={workerActive ? "good" : "muted"}
                badge={workerActive ? t("opsHealth.badgeHealthy") : t("opsHealth.badgeInfo")}
                href="/ops/jobs?status=RUNNING"
              />
              <HealthKpiCard
                label={t("opsHealth.redis")}
                value={t("opsHealth.notExposed")}
                title={t("opsHealth.noDedicatedRedisEndpoint")}
                tone="muted"
                badge={t("opsHealth.badgeInfo")}
              />
              <HealthKpiCard
                label={t("opsHealth.storage")}
                value={String(assetCurrentTotal || metrics.asset_reuse_by_type.length)}
                title={t("opsHealth.assetRecordsVisible")}
                tone="good"
                badge={t("opsHealth.badgeHealthy")}
                href="/ops/assets"
              />
              <HealthKpiCard
                label={t("opsHealth.risk")}
                value={String(riskOpen)}
                title={t("opsHealth.openWarnings")}
                tone={riskOpen > 0 ? "warn" : "good"}
                badge={riskOpen > 0 ? t("opsHealth.badgeAttention") : t("opsHealth.badgeHealthy")}
                href="/ops/risk"
              />
            </section>

            <section className="ops-health-panels is-dense">
              <HealthPanel
                title={t("opsHealth.workload")}
                action={
                  <Link className="ops-health-panel__link" href="/ops/jobs">
                    {t("opsHealth.openJobs")}
                  </Link>
                }
              >
                <div className="ops-health-statstrip" aria-label={t("opsHealth.queueBacklog")}>
                  <Stat label={t("opsHealth.queued")} value={metrics.queue_backlog.queued} />
                  <Stat label={t("opsHealth.running")} value={metrics.queue_backlog.running} />
                  <Stat label={t("opsHealth.retryable")} value={metrics.queue_backlog.retryable} />
                  <Stat label={t("opsHealth.retriesShort")} value={metrics.total_retry_attempts} />
                  <Stat label={t("opsHealth.avgProcessing")} value={formatSeconds(avgProcessing)} />
                </div>
                <div className="ops-health-block">
                  <h3>{t("opsHealth.queueMix")}</h3>
                  <QueueMixBar
                    queued={metrics.queue_backlog.queued}
                    running={metrics.queue_backlog.running}
                    retryable={metrics.queue_backlog.retryable}
                    labels={{
                      queued: t("opsHealth.queued"),
                      running: t("opsHealth.running"),
                      retryable: t("opsHealth.retryable"),
                    }}
                  />
                </div>
                <div className="ops-health-block">
                  <h3>{t("opsHealth.jobMatrix")}</h3>
                  <JobMatrixTable
                    rows={jobMatrix.rows}
                    columns={jobMatrix.columns}
                    emptyLabel={t("opsHealth.noJobMatrix")}
                    typeLabel={t("opsHealth.matrixType")}
                    totalLabel={t("opsHealth.matrixTotal")}
                  />
                </div>
                <div className="ops-health-block">
                  <h3>{t("opsHealth.renders")}</h3>
                  <StatusChips record={metrics.render_counts_by_status} emptyLabel="—" limit={6} />
                </div>
                <div className="ops-health-block">
                  <h3>{t("opsHealth.publishDrafts")}</h3>
                  <StatusChips record={metrics.publish_draft_counts_by_status} emptyLabel="—" limit={6} />
                </div>
                <div className="ops-health-block">
                  <h3>{t("opsHealth.assetReuse")}</h3>
                  <AssetReuseList assets={assetRows} emptyLabel={t("opsHealth.noAssetReuse")} />
                </div>
              </HealthPanel>

              <HealthPanel
                title={t("opsHealth.signals")}
                action={
                  <Link className="ops-health-panel__link" href="/ops/risk">
                    {t("opsHealth.openRisk")}
                  </Link>
                }
              >
                <div className="ops-health-block">
                  <h3>{t("opsHealth.riskBySeverity")}</h3>
                  {riskEntries.length > 0 ? (
                    <MeterList entries={riskEntries} toneFor={riskTone} />
                  ) : (
                    <p className="ops-health-empty">{t("opsHealth.noOpenRisk")}</p>
                  )}
                </div>

                <div className="ops-health-block ops-health-fetch">
                  <h3>{t("opsHealth.fetchHealth")}</h3>
                  {fetchHealth ? (
                    <>
                      <div className="ops-health-statstrip is-fetch">
                        <Stat label={t("opsHealth.fetchWindowRuns")} value={fetchHealth.window_runs} />
                        <Stat
                          label={t("opsHealth.fetchBlocked")}
                          value={`${fetchHealth.blocked_runs} (${fetchHealth.blocked_ratio_percent.toFixed(0)}%)`}
                        />
                        <Stat label={t("opsHealth.fetchFailed")} value={fetchHealth.failed_runs} />
                        <Stat label={t("opsHealth.fetchParseWarnings")} value={fetchHealth.parse_warning_runs} />
                      </div>
                      {topBlocked.length > 0 ? (
                        <ul className="ops-health-failures is-compact">
                          {topBlocked.map((item) => (
                            <li key={item.reason}>
                              <code>{item.reason}</code>
                              <em>{item.count}</em>
                            </li>
                          ))}
                        </ul>
                      ) : null}
                      <div className="ops-health-block">
                        <h3>{t("opsHealth.fetchByAccount")}</h3>
                        <FetchAccountList accounts={fetchAccounts} emptyLabel={t("opsHealth.noFetchAccounts")} />
                      </div>
                    </>
                  ) : (
                    <p className="ops-health-empty">{t("opsHealth.fetchHealthUnavailable")}</p>
                  )}
                </div>

                <div className="ops-health-block">
                  <h3>{t("opsHealth.commonFailures")}</h3>
                  {failureCategories.length > 0 ? (
                    <ul className="ops-health-failures is-compact">
                      {failureCategories.map((item) => (
                        <li key={item.error_code}>
                          <code>{item.error_code}</code>
                          <em>{item.count}</em>
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p className="ops-health-empty">{t("opsHealth.noFailureCategories")}</p>
                  )}
                </div>

                {failureRates.length > 0 ? (
                  <div className="ops-health-block">
                    <h3>{t("opsHealth.failureRatesShort")}</h3>
                    <MeterList
                      entries={failureRates}
                      maxMode="percent"
                      formatValue={(value) => `${value.toFixed(0)}%`}
                      toneFor={() => "warn"}
                    />
                  </div>
                ) : null}
              </HealthPanel>
            </section>

            <HealthPanel
              title={t("opsHealth.publishWeek")}
              action={
                <Link className="ops-health-panel__link" href="/ops/publish-health">
                  {t("opsHealth.openPublishHealth")}
                </Link>
              }
            >
              {publishOverview ? (
                <div className="ops-health-statstrip" aria-label={t("opsHealth.publishWeek")}>
                  <Stat
                    label={t("opsHealth.publishSuccessRate")}
                    value={`${publishOverview.success_rate_percent.toFixed(0)}%`}
                  />
                  <Stat label={t("opsHealth.publishAttempts")} value={publishOverview.total_attempts} />
                  <Stat label={t("opsHealth.publishSucceeded")} value={publishOverview.succeeded_attempts} />
                  <Stat label={t("opsHealth.publishFailed")} value={publishOverview.failed_attempts} />
                  <Stat label={t("opsHealth.draftsBlocked")} value={publishOverview.drafts_blocked_by_risk} />
                </div>
              ) : null}
              <PublishWeekChart days={publishDays} emptyLabel={t("opsHealth.noPublishTrend")} />
              <p className="ops-health-meta">
                {t("opsHealth.publishGenerated")}:{" "}
                {publishHealth ? formatDateTime(publishHealth.generated_at) : "—"}
              </p>
            </HealthPanel>

            <p className="ops-health-gaps is-inline" title={t("opsHealth.knownGaps")}>
              <strong>{t("opsHealth.knownGaps")}:</strong>{" "}
              {t("opsHealth.gapRedis")} · {t("opsHealth.gapWorker")} · {t("opsHealth.gapStorage")}
            </p>
          </>
        ) : null}
      </main>
      </AsyncContentBoundary>
    </OpsConsoleShell>
  );
}
