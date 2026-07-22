"use client";

import Link from "next/link";
import { useEffect, useState, type ReactNode } from "react";
import { fetchOperationalMetrics, fetchPublishControlQueue, fetchPublishHealthDashboard } from "../../lib/api";
import { useT } from "../../lib/i18n";
import { useLatestRequest, type LatestRequestMode } from "../../lib/useLatestRequest";
import type { PublishDayStats, PublishHealthDashboard } from "../../types/analytics";
import type { OperationalMetrics, OpsFailureCategory } from "../../types/operations";
import type { AccountHealthSummary, PublishControlQueue } from "../../types/publish-control";
import { OpsConsoleShell } from "../app-shell/OpsConsoleShell";
import { TopbarRefreshButton } from "../app-shell/TopbarRefreshButton";
import { AsyncContentBoundary } from "../shared/AsyncContentBoundary";
import { OpsState, formatDateTime, sumRecord, type OpsTone } from "./OpsShared";

type OpsHomeState = {
  metrics: OperationalMetrics;
  publishHealth: PublishHealthDashboard;
  queue: PublishControlQueue;
};

function formatDayLabel(day: string): string {
  const date = new Date(`${day}T12:00:00`);
  if (Number.isNaN(date.getTime())) return day.slice(-5);
  return date.toLocaleDateString(undefined, { weekday: "short", day: "numeric" });
}

function formatStatusLabel(status: string): string {
  return status
    .split(/[_-]+/)
    .filter(Boolean)
    .map((part) => part.charAt(0) + part.slice(1).toLowerCase())
    .join(" ");
}

function formatSeconds(value: number): string {
  if (!Number.isFinite(value) || value <= 0) return "—";
  if (value < 60) return `${Math.round(value)}s`;
  const minutes = value / 60;
  if (minutes < 60) return `${minutes.toFixed(1)}m`;
  return `${(minutes / 60).toFixed(1)}h`;
}

function countEntries(record: Record<string, number> | null | undefined): Array<{ key: string; count: number }> {
  if (!record) return [];
  return Object.entries(record)
    .map(([key, count]) => ({ key, count: Number(count) || 0 }))
    .sort((a, b) => b.count - a.count || a.key.localeCompare(b.key));
}

function riskTone(severity: string): OpsTone {
  const key = severity.toUpperCase();
  if (["CRITICAL", "HIGH", "BLOCKING"].includes(key)) return "danger";
  if (["MEDIUM", "WARN", "WARNING", "MODERATE"].includes(key)) return "warn";
  if (["LOW", "INFO"].includes(key)) return "muted";
  return "warn";
}

function accountNeedsCare(account: AccountHealthSummary): boolean {
  return account.health_status !== "HEALTHY" || account.is_on_hold;
}

function buildJobsSnapshot(
  record: Record<string, Record<string, number>>,
  limit = 5,
): Array<{ jobType: string; running: number; retryable: number; failed: number; total: number }> {
  return Object.entries(record)
    .map(([jobType, statuses]) => {
      const running = Number(statuses.RUNNING) || 0;
      const retryable = Number(statuses.RETRYABLE) || 0;
      const failed = Number(statuses.FAILED) || 0;
      const total = Object.values(statuses).reduce((sum, n) => sum + (Number(n) || 0), 0);
      return { jobType, running, retryable, failed, total };
    })
    .filter((row) => row.total > 0)
    .sort((a, b) => b.running + b.retryable + b.failed - (a.running + a.retryable + a.failed) || b.total - a.total)
    .slice(0, limit);
}

function HomeKpi({
  label,
  value,
  detail,
  tone = "muted",
  href,
}: {
  label: string;
  value: string;
  detail: string;
  tone?: OpsTone;
  href: string;
}) {
  return (
    <Link className={`ops-home-kpi tone-${tone}`} href={href} title={detail}>
      <em>{label}</em>
      <strong>{value}</strong>
      <span>{detail}</span>
    </Link>
  );
}

function HomePanel({
  title,
  action,
  children,
}: {
  title: string;
  action?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className="ops-home-panel">
      <div className="ops-home-panel__head">
        <h2>{title}</h2>
        {action}
      </div>
      <div className="ops-home-panel__body">{children}</div>
    </section>
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
    return <p className="ops-home-empty">—</p>;
  }
  const parts = [
    { key: "queued", value: queued, label: labels.queued, tone: "muted" as const },
    { key: "running", value: running, label: labels.running, tone: "good" as const },
    { key: "retryable", value: retryable, label: labels.retryable, tone: "warn" as const },
  ].filter((part) => part.value > 0);

  return (
    <div className="ops-home-queue-mix" aria-label={`${labels.queued} ${queued}, ${labels.running} ${running}, ${labels.retryable} ${retryable}`}>
      <div className="ops-home-queue-mix__bar" aria-hidden="true">
        {parts.map((part) => (
          <span
            key={part.key}
            className={`ops-home-queue-mix__seg tone-${part.tone}`}
            style={{ flexGrow: part.value, flexBasis: 0 }}
            title={`${part.label}: ${part.value}`}
          />
        ))}
      </div>
      <div className="ops-home-queue-mix__legend">
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

function PublishWeekChart({ days }: { days: PublishDayStats[] }) {
  const maxAttempts = Math.max(...days.map((day) => day.attempts), 1);
  return (
    <div className="ops-home-week" role="img" aria-label={days.map((d) => `${d.day}: ${d.attempts}`).join(", ")}>
      {days.map((day) => {
        const height = Math.max(8, Math.round((day.attempts / maxAttempts) * 100));
        const successShare = day.attempts > 0 ? (day.succeeded / day.attempts) * 100 : 0;
        const failShare = day.attempts > 0 ? (day.failed / day.attempts) * 100 : 0;
        return (
          <div className="ops-home-daybar" key={day.day} title={`${day.day}: ${day.attempts} · ✓${day.succeeded} · ✕${day.failed}`}>
            <div className="ops-home-daybar__col" style={{ height: `${height}%` }}>
              {day.attempts > 0 ? (
                <>
                  <span className="ops-home-daybar__seg is-ok" style={{ flexGrow: Math.max(successShare, 0.01) }} />
                  <span className="ops-home-daybar__seg is-fail" style={{ flexGrow: Math.max(failShare, day.failed > 0 ? 0.01 : 0) }} />
                  <span
                    className="ops-home-daybar__seg is-other"
                    style={{ flexGrow: Math.max(100 - successShare - failShare, 0) }}
                  />
                </>
              ) : (
                <span className="ops-home-daybar__seg is-empty" style={{ flexGrow: 1 }} />
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

function MeterList({ entries }: { entries: Array<{ key: string; count: number }> }) {
  const peak = Math.max(...entries.map((item) => item.count), 1);
  return (
    <div className="ops-home-meters ops-home-risk">
      {entries.map((item) => {
        const width = Math.max(0, Math.min(100, (item.count / peak) * 100));
        const tone = riskTone(item.key);
        return (
          <div className="ops-home-meter" key={item.key}>
            <div className="ops-home-meter__label">
              <em>{formatStatusLabel(item.key)}</em>
              <strong>{item.count}</strong>
            </div>
            <div className="ops-home-meter__track" aria-hidden="true">
              <span className={`ops-home-meter__fill tone-${tone}`} style={{ width: `${width}%` }} />
            </div>
          </div>
        );
      })}
    </div>
  );
}

function StatusChips({ record, limit = 5 }: { record: Record<string, number>; limit?: number }) {
  const entries = countEntries(record).slice(0, limit);
  if (entries.length === 0) return <p className="ops-home-empty">—</p>;
  return (
    <div className="ops-home-chips">
      {entries.map((item) => (
        <span className="ops-home-chip" key={item.key}>
          <em>{formatStatusLabel(item.key)}</em>
          <strong>{item.count}</strong>
        </span>
      ))}
    </div>
  );
}

function JobsSnapshot({
  rows,
  emptyLabel,
}: {
  rows: Array<{ jobType: string; running: number; retryable: number; failed: number; total: number }>;
  emptyLabel: string;
}) {
  if (rows.length === 0) return <p className="ops-home-empty">{emptyLabel}</p>;
  return (
    <ul className="ops-home-jobs">
      {rows.map((row) => (
        <li key={row.jobType}>
          <code title={row.jobType}>{formatStatusLabel(row.jobType)}</code>
          <span>
            R {row.running} · Re {row.retryable} · F {row.failed}
          </span>
        </li>
      ))}
    </ul>
  );
}

function FailureList({ items, emptyLabel }: { items: OpsFailureCategory[]; emptyLabel: string }) {
  if (items.length === 0) return <p className="ops-home-empty">{emptyLabel}</p>;
  return (
    <ul className="ops-home-failures">
      {items.map((item) => (
        <li key={item.error_code}>
          <code>{item.error_code}</code>
          <em>{item.count}</em>
        </li>
      ))}
    </ul>
  );
}

function AccountsCareList({ accounts, emptyLabel }: { accounts: AccountHealthSummary[]; emptyLabel: string }) {
  if (accounts.length === 0) return <p className="ops-home-empty">{emptyLabel}</p>;
  return (
    <ul className="ops-home-accounts">
      {accounts.map((account) => (
        <li key={account.platform_account_id}>
          <strong title={account.display_name}>{account.display_name}</strong>
          <span>
            {account.health_status}
            {account.is_on_hold ? " · HOLD" : ""}
          </span>
        </li>
      ))}
    </ul>
  );
}

export function OpsHomePage() {
  const t = useT();
  const [state, setState] = useState<OpsHomeState | null>(null);
  const request = useLatestRequest();

  async function load(mode: LatestRequestMode = state ? "refresh" : "initial") {
    await request.run(
      async () => Promise.all([
        fetchOperationalMetrics(),
        fetchPublishHealthDashboard("last_7_days"),
        fetchPublishControlQueue(),
      ]),
      ([metrics, publishHealth, queue]) => setState({ metrics, publishHealth, queue }),
      mode
    ).catch(() => undefined);
  }

  useEffect(() => {
    void load("initial");
  }, [t]);

  const refreshAction = (
    <TopbarRefreshButton busy={request.refreshing} disabled={request.initialLoading} onClick={() => void load("refresh")} />
  );

  if (!state) {
    const boundaryStatus = request.initialLoading ? "loading" : request.error ? "error" : "empty";
    return (
      <OpsConsoleShell actions={refreshAction} description={t("ops.description")} title={t("ops.title")}>
        <AsyncContentBoundary
          refreshing={request.refreshing}
          status={boundaryStatus}
          skeleton={<OpsState title={t("ops.loadingTitle")} detail={t("ops.loadingDetail")} />}
          errorState={<OpsState title={t("ops.unavailableTitle")} detail={request.error?.message ?? t("operatorHome.loadError")} retry={() => void load("initial")} />}
        >
          {null}
        </AsyncContentBoundary>
      </OpsConsoleShell>
    );
  }

  const { metrics, publishHealth, queue } = state;
  const riskOpen = sumRecord(metrics.open_risk_counts_by_severity);
  const careAccounts = queue.accounts.filter(accountNeedsCare).slice(0, 3);
  const degradedAccounts = queue.accounts.filter(accountNeedsCare).length;
  const backlogPressure = metrics.queue_backlog.running + metrics.queue_backlog.retryable;
  const fetchBlocked = metrics.douyin_fetch_health.blocked_ratio_percent;
  const riskEntries = countEntries(metrics.open_risk_counts_by_severity).slice(0, 5);
  const topFailures = (metrics.common_failure_categories ?? []).slice(0, 3);
  const jobsSnapshot = buildJobsSnapshot(metrics.job_counts_by_type_status, 5);
  const avgProcessing = metrics.average_processing_seconds_per_source_video ?? 0;
  const hasPublishActivity =
    publishHealth.overview.total_attempts > 0 || publishHealth.by_day.some((day) => day.attempts > 0);
  const failedJobs = Object.values(metrics.job_counts_by_type_status).reduce(
    (sum, counts) => sum + (Number(counts.FAILED) || 0),
    0,
  );

  return (
    <OpsConsoleShell actions={refreshAction} description={t("ops.description")} title={t("ops.title")}>
      <AsyncContentBoundary refreshing={request.refreshing} status="success">
      <main className="ops-page ops-home-page">
        {request.error ? <div className="inline-error">{request.error.message}</div> : null}

        <p className="ops-home-freshness">
          <span>{t("ops.lastGenerated")}</span>
          <time dateTime={metrics.generated_at}>{formatDateTime(metrics.generated_at)}</time>
          <span>·</span>
          <span>{t("ops.publishHealth")}</span>
          <time dateTime={publishHealth.generated_at}>{formatDateTime(publishHealth.generated_at)}</time>
          <span>·</span>
          <span>{t("ops.controlQueue")}</span>
          <time dateTime={queue.generated_at}>{formatDateTime(queue.generated_at)}</time>
        </p>

        <section className="ops-home-kpis ops-home-pulse" aria-label={t("ops.title")}>
          <HomeKpi
            label={t("ops.jobs")}
            value={String(backlogPressure)}
            detail={`${metrics.queue_backlog.running} ${t("ops.actionItems.running")} · ${metrics.retryable_jobs} ${t("ops.actionItems.retryable")}`}
            tone={metrics.retryable_jobs > 0 ? "warn" : metrics.queue_backlog.running > 0 ? "good" : "muted"}
            href="/ops/jobs"
          />
          <HomeKpi
            label={t("ops.publishSuccess")}
            value={`${publishHealth.overview.success_rate_percent.toFixed(0)}%`}
            detail={`${publishHealth.overview.succeeded_attempts}/${publishHealth.overview.total_attempts} ${t("ops.metrics.attemptsLabel")}`}
            tone={publishHealth.overview.failed_attempts > 0 ? "warn" : "good"}
            href="/ops/publish-health"
          />
          <HomeKpi
            label={t("ops.reconciliation")}
            value={String(publishHealth.overview.needs_reconciliation_attempts)}
            detail={t("ops.metrics.reconciliationDetail")}
            tone={publishHealth.overview.needs_reconciliation_attempts > 0 ? "warn" : "good"}
            href="/ops/reconciliation"
          />
          <HomeKpi
            label={t("ops.accounts")}
            value={String(degradedAccounts)}
            detail={t("ops.metrics.accountsDegradedDetail").replace("{total}", String(queue.accounts.length))}
            tone={degradedAccounts > 0 ? "warn" : "good"}
            href="/ops/accounts"
          />
          <HomeKpi
            label={t("ops.risk")}
            value={String(riskOpen)}
            detail={t("ops.metrics.riskDetail")}
            tone={riskOpen > 0 ? "warn" : "good"}
            href="/ops/risk"
          />
        </section>

        <div className="ops-home-statstrip is-workload" aria-label={t("ops.workloadContext")}>
          <span>
            <em>{t("ops.queued")}</em>
            <strong>{metrics.queue_backlog.queued}</strong>
          </span>
          <span>
            <em>{t("ops.running")}</em>
            <strong>{metrics.queue_backlog.running}</strong>
          </span>
          <span>
            <em>{t("ops.retryable")}</em>
            <strong>{metrics.queue_backlog.retryable}</strong>
          </span>
          <span>
            <em>{t("ops.avgProcessing")}</em>
            <strong>{formatSeconds(avgProcessing)}</strong>
          </span>
        </div>

        <section className="ops-home-main">
          <HomePanel
            title={hasPublishActivity ? t("ops.publishWeek") : t("ops.pipelinePulse")}
            action={
              <Link className="ops-home-panel__link" href={hasPublishActivity ? "/ops/publish-health" : "/ops/jobs"}>
                {hasPublishActivity ? t("ops.openPublishHealth") : t("ops.openJobs")}
              </Link>
            }
          >
            {hasPublishActivity ? (
              <>
                <div className="ops-home-statstrip">
                  <span>
                    <em>{t("ops.publishSuccess")}</em>
                    <strong>{publishHealth.overview.success_rate_percent.toFixed(0)}%</strong>
                  </span>
                  <span>
                    <em>{t("ops.metrics.attemptsLabel")}</em>
                    <strong>{publishHealth.overview.total_attempts}</strong>
                  </span>
                  <span>
                    <em>{t("ops.metrics.failedLabel")}</em>
                    <strong>{publishHealth.overview.failed_attempts}</strong>
                  </span>
                </div>
                <PublishWeekChart days={publishHealth.by_day} />
              </>
            ) : (
              <div className="ops-home-fallback">
                <p className="ops-home-empty is-note">{t("ops.noPublishTrend")}</p>
                <div className="ops-home-block">
                  <h3>{t("ops.jobsSnapshot")}</h3>
                  <JobsSnapshot rows={jobsSnapshot} emptyLabel={t("ops.noJobsSnapshot")} />
                </div>
                <div className="ops-home-block">
                  <h3>{t("ops.topFailures")}</h3>
                  <FailureList items={topFailures} emptyLabel={t("ops.noTopFailures")} />
                </div>
                <div className="ops-home-block">
                  <h3>{t("ops.renders")}</h3>
                  <StatusChips record={metrics.render_counts_by_status} />
                </div>
                <div className="ops-home-block">
                  <h3>{t("ops.publishDrafts")}</h3>
                  <StatusChips record={metrics.publish_draft_counts_by_status} />
                </div>
              </div>
            )}
          </HomePanel>

          <HomePanel
            title={t("ops.attention")}
            action={
              <Link className="ops-home-panel__link" href="/ops/jobs">
                {t("ops.openJobs")}
              </Link>
            }
          >
            <div className="ops-home-block">
              <h3>{t("ops.queueMix")}</h3>
              <QueueMixBar
                queued={metrics.queue_backlog.queued}
                running={metrics.queue_backlog.running}
                retryable={metrics.queue_backlog.retryable}
                labels={{
                  queued: t("ops.queued"),
                  running: t("ops.running"),
                  retryable: t("ops.retryable"),
                }}
              />
            </div>

            <ul className="ops-home-attention" aria-label={t("ops.actionQueue")}>
              <li>
                <Link href="/ops/jobs?status=RUNNING">
                  <strong>{metrics.queue_backlog.running}</strong>
                  <span>{t("ops.actionItems.running")}</span>
                </Link>
              </li>
              <li>
                <Link href="/ops/jobs?status=RETRYABLE">
                  <strong>{metrics.retryable_jobs}</strong>
                  <span>{t("ops.actionItems.retryable")}</span>
                </Link>
              </li>
              <li>
                <Link href="/ops/jobs?status=FAILED">
                  <strong>{failedJobs}</strong>
                  <span>{t("ops.actionItems.failed")}</span>
                </Link>
              </li>
              <li>
                <Link href="/ops/reconciliation">
                  <strong>{publishHealth.overview.needs_reconciliation_attempts}</strong>
                  <span>{t("ops.actionItems.needsReconciliation")}</span>
                </Link>
              </li>
              <li>
                <Link href="/ops/publish-control">
                  <strong>{queue.unassigned_drafts.length}</strong>
                  <span>{t("ops.actionItems.unassignedDrafts")}</span>
                </Link>
              </li>
              <li>
                <Link href="/ops/publish-control">
                  <strong>{queue.needs_attention.length}</strong>
                  <span>{t("ops.actionItems.needsRouting")}</span>
                </Link>
              </li>
            </ul>

            <div className="ops-home-block">
              <div className="ops-home-block__head">
                <h3>{t("ops.riskPreview")}</h3>
                <Link href="/ops/risk">{t("ops.openRisk")}</Link>
              </div>
              {riskEntries.length > 0 ? (
                <MeterList entries={riskEntries} />
              ) : (
                <p className="ops-home-empty">{t("ops.noRiskPreview")}</p>
              )}
            </div>

            <div className="ops-home-block">
              <div className="ops-home-block__head">
                <h3>{t("ops.accountsCare")}</h3>
                <Link href="/ops/accounts">{t("ops.openAccounts")}</Link>
              </div>
              <AccountsCareList accounts={careAccounts} emptyLabel={t("ops.noAccountsCare")} />
            </div>

            {hasPublishActivity ? (
              <div className="ops-home-block">
                <h3>{t("ops.topFailures")}</h3>
                <FailureList items={topFailures} emptyLabel={t("ops.noTopFailures")} />
              </div>
            ) : null}

            {hasPublishActivity ? (
              <div className="ops-home-block">
                <h3>{t("ops.jobsSnapshot")}</h3>
                <JobsSnapshot rows={jobsSnapshot} emptyLabel={t("ops.noJobsSnapshot")} />
              </div>
            ) : null}

            <p className="ops-home-fetch">
              <span>
                {t("ops.fetchHealthBlockedRatio")}: <strong>{fetchBlocked.toFixed(0)}%</strong>
              </span>
              <Link href="/ops/health">{t("ops.openHealth")}</Link>
            </p>
          </HomePanel>
        </section>
      </main>
      </AsyncContentBoundary>
    </OpsConsoleShell>
  );
}
