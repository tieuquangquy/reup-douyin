"use client";

import Link from "next/link";
import { useEffect, useState, type ReactNode } from "react";
import { fetchOpsHomeSummary } from "../../lib/api";
import { useT } from "../../lib/i18n";
import { useLatestRequest, type LatestRequestMode } from "../../lib/useLatestRequest";
import type {
  OpsHomeActionItem,
  OpsHomeDependencySignal,
  OpsHomeFailureSignature,
  OpsHomeJobHealthRow,
  OpsHomeSummaryResponse,
  OpsHomeTrendDay,
} from "../../types/operations";
import { OpsConsoleShell } from "../app-shell/OpsConsoleShell";
import { TopbarRefreshButton } from "../app-shell/TopbarRefreshButton";
import { AsyncContentBoundary } from "../shared/AsyncContentBoundary";
import { WorkItemActionIcon } from "../shared/WorkItemActionIcon";
import { OpsState, formatDateTime } from "./OpsShared";

function formatLabel(value: string): string {
  return value
    .split(/[_-]+/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1).toLowerCase())
    .join(" ");
}

function formatDayLabel(day: string): string {
  const date = new Date(day + "T12:00:00");
  if (Number.isNaN(date.getTime())) return day.slice(-5);
  return date.toLocaleDateString(undefined, { weekday: "short", day: "numeric" });
}

function formatAge(value?: string | null, relativeTo?: string): string {
  if (!value) return "No backlog";
  const timestamp = new Date(value).getTime();
  const reference = relativeTo ? new Date(relativeTo).getTime() : timestamp;
  if (Number.isNaN(timestamp) || Number.isNaN(reference)) return "Unknown";
  const seconds = Math.max(0, Math.floor((reference - timestamp) / 1000));
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ${minutes % 60}m`;
  return `${Math.floor(hours / 24)}d ${hours % 24}h`;
}

function formatSeconds(value: number): string {
  if (!value) return "-";
  if (value < 60) return `${Math.round(value)}s`;
  return `${Math.floor(value / 60)}m ${Math.round(value % 60)}s`;
}

function statusLabel(status: OpsHomeSummaryResponse["overall"]["status"]): string {
  if (status === "blocked") return "Blocked";
  if (status === "needs_attention") return "Needs attention";
  if (status === "healthy") return "Healthy";
  return "Quiet";
}

function VisualPanel({ title, subtitle, action, className = "", children }: { title: string; subtitle?: string; action?: ReactNode; className?: string; children: ReactNode }) {
  return (
    <section className={("ops-home-v6-panel " + className).trim()}>
      <header className="ops-home-v6-panel__head">
        <div><h2>{title}</h2>{subtitle ? <p>{subtitle}</p> : null}</div>
        {action}
      </header>
      <div className="ops-home-v6-panel__body">{children}</div>
    </section>
  );
}

function OverviewHeader({ summary }: { summary: OpsHomeSummaryResponse }) {
  const notObserved = summary.dependencies.filter((item) => item.state === "not_observed").length;
  const verdict = summary.admission_verdict;
  return (
    <section className={`ops-home-v6-overview is-${summary.overall.status}`}>
      <div className="ops-home-v7-overview__main">
        <span className="ops-home-v7-beacon" aria-hidden="true"><i /><b /><em /></span>
        <div className="ops-home-v6-overview__copy">
          <span className="ops-home-v6-status"><i />{statusLabel(summary.overall.status)}</span>
          <h2>{summary.overall.headline}</h2>
          <p>{summary.overall.detail}</p>
        </div>
      </div>
      <div className="ops-home-v6-overview__meta">
        <div className={`ops-home-v9-admission is-${verdict.status}`}>
          <span><i />Admission control</span>
          <strong>{verdict.label}</strong>
          <small>{verdict.detail}</small>
          {verdict.reasons.length > 0 ? <em>{verdict.reasons.slice(0, 2).join(" · ")}</em> : null}
        </div>
        <span>{notObserved} dependencies not observed</span>
        <time dateTime={summary.freshness.generated_at}>Checked {formatDateTime(summary.freshness.generated_at)}</time>
      </div>
    </section>
  );
}

function HiddenRiskStrip({ risks }: { risks: OpsHomeSummaryResponse["hidden_risks"] }) {
  if (risks.length === 0) return null;
  const clearCount = risks.filter((risk) => risk.state === "clear").length;
  const attentionCount = risks.filter((risk) => risk.state !== "clear").length;
  const stateLabel = (state: (typeof risks)[number]["state"]) => state === "clear" ? "Clear" : state === "watch" ? "Watch" : state === "critical" ? "Critical" : "Not observed";
  const valueCaption = (key: string, hasMeasure: boolean) => {
    if (key === "observability_coverage") return hasMeasure ? "active work observed" : "no active sample";
    if (key === "potentially_stuck") return "running jobs";
    if (key === "retry_amplification") return "claims per job";
    return "contract gaps";
  };
  return (
    <section className="ops-home-v9-risk-strip" aria-label="Hidden operational risks">
      <header className="ops-home-v9-risk-strip__head">
        <div className="ops-home-v9-risk-strip__copy">
          <span><i />Signal integrity audit</span>
          <h2>Hidden operational risks</h2>
          <p>Four cross-checks behind the headline numbers — lock evidence, retry cost, and record integrity.</p>
        </div>
        <div className="ops-home-v9-risk-strip__summary">
          <span className="is-clear"><i /><b>{clearCount}</b> clear</span>
          <span className={attentionCount > 0 ? "is-attention" : "is-muted"}><i /><b>{attentionCount}</b> attention</span>
          <Link href="/ops/health">Health ledger <WorkItemActionIcon className="ops-home-v9-risk__enter" kind="enter" /></Link>
        </div>
      </header>
      <div className="ops-home-v9-risk-grid">
        {risks.map((risk, index) => {
          const hasMeasure = typeof risk.value === "number";
          const numeric = hasMeasure ? risk.value ?? 0 : 0;
          const fill = risk.key === "observability_coverage" ? numeric : risk.key === "retry_amplification" ? Math.min(100, Math.max(0, (numeric - 1) * 100)) : Math.min(100, numeric * 20);
          const visibleSegments = risk.segments.filter((segment) => segment.value > 0).slice(0, 3);
          const segmentTotal = visibleSegments.reduce((sum, segment) => sum + segment.value, 0);
          const isIdle = risk.key === "observability_coverage" && !hasMeasure;
          return (
            <Link className={`ops-home-v9-risk is-${risk.state}${isIdle ? " is-idle" : ""}`} href={risk.href} key={risk.key}>
              <header className="ops-home-v9-risk__head">
                <span className="ops-home-v9-risk__glyph" aria-hidden="true"><b>{String(index + 1).padStart(2, "0")}</b><i /></span>
                <span className="ops-home-v9-risk__identity"><small>Signal {String(index + 1).padStart(2, "0")}</small><strong>{risk.label}</strong></span>
                <span className="ops-home-v9-risk__state"><i />{stateLabel(risk.state)}</span>
              </header>
              <div className="ops-home-v9-risk__value"><strong>{risk.display_value}</strong><span>{valueCaption(risk.key, hasMeasure)}</span></div>
              <div className={`ops-home-v9-risk__visual${visibleSegments.length > 1 ? " has-segments" : ""}`} aria-hidden="true">
                {visibleSegments.length > 1 ? visibleSegments.map((segment) => <i key={segment.key} style={{ width: `${(segment.value / segmentTotal) * 100}%` }} />) : <i style={{ width: `${fill}%` }} />}
              </div>
              <p>{risk.detail}</p>
              <footer className="ops-home-v9-risk__evidence">
                <span>{visibleSegments.length > 0 ? visibleSegments.map((segment) => <small key={segment.key}>{segment.label} <b>{segment.value}</b></small>) : <small>No exceptions detected</small>}</span>
                <WorkItemActionIcon className="ops-home-v9-risk__enter" kind="enter" />
              </footer>
            </Link>
          );
        })}
      </div>
    </section>
  );
}

function OperationalRibbon({ summary }: { summary: OpsHomeSummaryResponse }) {
  const order = ["fetch", "jobs", "outputs", "accounts", "publishing"];
  const items = [...summary.operational_status].sort((a, b) => order.indexOf(a.key) - order.indexOf(b.key));
  return (
    <nav className="ops-home-v7-ribbon" aria-label="Operational domains">
      {items.map((item, index) => (
        <Link className={`is-${item.status}`} href={item.href} key={item.key} title={item.detail}>
          <span><i />{String(index + 1).padStart(2, "0")}</span><strong>{item.label}</strong><small>{formatLabel(item.status)}</small>
        </Link>
      ))}
    </nav>
  );
}

function DecisionMetrics({ summary }: { summary: OpsHomeSummaryResponse }) {
  const queue = summary.queue_health;
  const firstCritical = summary.action_items.find((item) => item.severity === "critical");
  const metrics = [
    {
      label: "Critical incidents",
      value: String(summary.overall.critical_count),
      detail: `${summary.overall.warning_count} warning signals`,
      tone: summary.overall.critical_count > 0 ? "critical" : "ready",
      href: firstCritical?.href ?? "/ops/health",
    },
    {
      label: "Oldest queued",
      value: formatAge(queue.oldest_queued_at, summary.freshness.generated_at),
      detail: `${queue.queued} jobs waiting`,
      tone: queue.queued > 0 ? "warning" : "ready",
      href: "/ops/jobs?status=QUEUED",
    },
    {
      label: "Busy worker signals",
      value: String(queue.busy_worker_count),
      detail: queue.running_without_lock > 0 ? `${queue.running_without_lock} running without lock` : `${queue.running_with_lock} locked running`,
      tone: queue.running_without_lock > 0 ? "critical" : queue.busy_worker_count > 0 ? "ready" : "muted",
      href: "/ops/jobs?status=RUNNING",
    },
  ];
  return (
    <section className="ops-home-v6-decisions" aria-label="Operations decision metrics">
      {metrics.map((metric) => (
        <Link className={`is-${metric.tone}`} href={metric.href} key={metric.label}>
          <span>{metric.label}</span><strong>{metric.value}</strong><small>{metric.detail}</small>
        </Link>
      ))}
    </section>
  );
}

function IncidentQueue({ items, checkedAt }: { items: OpsHomeActionItem[]; checkedAt: string }) {
  if (items.length === 0) return <div className="ops-home-v6-empty"><strong>All observed signals are clear</strong><span>No operator action is open.</span></div>;
  const visible = items.slice(0, 4);
  return (
    <div className="ops-home-v6-incidents">
      {visible.map((item) => (
        <Link className={`is-${item.severity}`} href={item.href} key={item.id}>
          <span className="ops-home-v6-incident__severity">{item.severity}</span>
          <span className="ops-home-v6-incident__copy">
            <em>{item.area}{item.oldest_at ? ` - open ${formatAge(item.oldest_at, checkedAt)}` : ""}</em>
            <strong>{item.title}</strong>
            <small>{item.detail}</small>
            <span>Next: {item.recommended_action}</span>
          </span>
          <b>{item.count}</b>
          <WorkItemActionIcon kind="enter" />
        </Link>
      ))}
      {items.length > visible.length ? <p className="ops-home-v6-more">+{items.length - visible.length} more signals in specialist views</p> : null}
    </div>
  );
}

const workloadSegments = [
  { key: "running", label: "Running" },
  { key: "queued", label: "Queued" },
  { key: "review", label: "Review" },
  { key: "retryable", label: "Retryable" },
  { key: "failed", label: "Failed" },
] as const;

function PipelineWorkloadChart({ rows }: { rows: OpsHomeJobHealthRow[] }) {
  if (rows.length === 0) return <div className="ops-home-v6-empty"><strong>No job history</strong><span>The durable queue is quiet.</span></div>;
  const chartRows = rows.slice(0, 8).map((row) => ({
    row,
    total: row.running + row.queued + row.waiting_review + row.retryable + row.failed,
  }));
  const activeMaximum = Math.max(...chartRows.map((item) => item.total), 0);
  const completedTotal = chartRows.reduce((sum, item) => sum + item.row.completed, 0);
  if (activeMaximum === 0) return <div className="ops-home-v7-workload-clear"><span aria-hidden="true"><i /></span><strong>Queue is clear</strong><p>No queued, running, review, retryable, or failed jobs right now.</p><small>{completedTotal} jobs completed in observed history.</small></div>;
  const activeRows = chartRows.filter((item) => item.total > 0);
  const maximum = activeMaximum;
  return (
    <div className="ops-home-v6-workload-chart" role="group" aria-label="Stacked horizontal bar chart of actionable workload by job type">
      <div className="ops-home-v6-legend">
        {workloadSegments.map((segment) => <span className={`is-${segment.key}`} key={segment.key}><i />{segment.label}</span>)}
      </div>
      <div className="ops-home-v6-axis"><span>0</span><span>{Math.ceil(maximum / 2)}</span><span>{maximum} jobs</span></div>
      {activeRows.map(({ row, total }) => {
        const values = { running: row.running, queued: row.queued, review: row.waiting_review, retryable: row.retryable, failed: row.failed };
        return (
          <Link className="ops-home-v6-workload-row" href={row.href} key={row.job_type}>
            <span className="ops-home-v6-workload-row__label"><strong>{formatLabel(row.job_type)}</strong><small>{total} actionable</small></span>
            <span className="ops-home-v6-workload-row__plot">
              <span className="ops-home-v6-gridline is-mid" /><span className="ops-home-v6-gridline is-end" />
              {workloadSegments.map((segment) => values[segment.key] > 0 ? <i className={`is-${segment.key}`} key={segment.key} style={{ width: `${(values[segment.key] / maximum) * 100}%` }} title={`${segment.label}: ${values[segment.key]}`} /> : null)}
            </span>
            <span className="ops-home-v6-workload-row__quality"><small>{row.failure_rate_percent.toFixed(0)}% failed</small><small>avg {formatSeconds(row.average_step_seconds)}</small><small>max {formatSeconds(row.max_step_seconds)}</small></span>
          </Link>
        );
      })}
    </div>
  );
}

function PublishOutcomeChart({ days }: { days: OpsHomeTrendDay[] }) {
  const attempts = days.reduce((sum, day) => sum + day.attempts, 0);
  const succeeded = days.reduce((sum, day) => sum + day.succeeded, 0);
  const failed = days.reduce((sum, day) => sum + day.failed, 0);
  const reconciliation = days.reduce((sum, day) => sum + day.needs_reconciliation, 0);
  if (attempts === 0) return <div className="ops-home-v6-empty"><strong>No publish activity</strong><span>The seven-day window is neutral.</span></div>;
  const maximum = Math.max(...days.map((day) => day.attempts), 1);
  return (
    <div className="ops-home-v6-publish-chart">
      <div className="ops-home-v6-chart-summary"><span><b>{attempts}</b> attempts</span><span className="is-success"><b>{succeeded}</b> succeeded</span><span className="is-failed"><b>{failed}</b> failed</span><span className="is-unresolved"><b>{reconciliation}</b> reconcile</span></div>
      <div className="ops-home-v6-columns" role="img" aria-label="Seven-day stacked column chart of publish outcomes">
        {days.map((day) => {
          const unresolved = Math.max(0, day.attempts - day.succeeded - day.failed);
          const height = Math.max(5, (day.attempts / maximum) * 100);
          return (
            <span className="ops-home-v6-column" key={day.day} title={`${day.day}: ${day.attempts} attempts`}>
              <i style={{ height: `${height}%` }}><b className="is-unresolved" style={{ flexGrow: unresolved }} /><b className="is-failed" style={{ flexGrow: day.failed }} /><b className="is-success" style={{ flexGrow: day.succeeded }} /></i>
              <em>{formatDayLabel(day.day)}</em>
            </span>
          );
        })}
      </div>
    </div>
  );
}

function FailurePareto({ rows }: { rows: OpsHomeFailureSignature[] }) {
  if (rows.length === 0) return <div className="ops-home-v6-empty"><strong>No recurring failure</strong><span>No failure signature is recorded.</span></div>;
  const visible = rows.slice(0, 6);
  const peak = Math.max(...visible.map((row) => row.count), 1);
  return <div className="ops-home-v6-pareto">{visible.map((row, index) => <Link href={row.href} key={`${row.source}-${row.error_code}`}><b className="ops-home-v7-rank">{String(index + 1).padStart(2, "0")}</b><span><em>{row.source}</em><strong>{row.label}</strong></span><i><b style={{ width: `${Math.max(4, (row.count / peak) * 100)}%` }} /></i><strong>{row.count}</strong></Link>)}</div>;
}

function FetchHealthChart({ summary }: { summary: OpsHomeSummaryResponse["fetch_health"] }) {
  if (summary.window_runs === 0) return <div className="ops-home-v6-empty"><strong>No fetch activity</strong><span>The recent fetch window is neutral.</span></div>;
  const resolvedAccounts = summary.by_account.filter((row) => row.account_id);
  const hasAccountAttribution = resolvedAccounts.length > 0;
  return (
    <div className="ops-home-v6-fetch-chart">
      <div className="ops-home-v6-chart-summary"><span><b>{summary.window_runs}</b> runs</span><span className="is-failed"><b>{summary.failed_runs}</b> failed</span><span className="is-unresolved"><b>{summary.parse_warning_runs}</b> warnings</span><span><b>{summary.blocked_ratio_percent.toFixed(0)}%</b> blocked</span></div>
      {hasAccountAttribution ? (
        <div className="ops-home-v6-fetch-rows" role="img" aria-label="Blocked fetch rate ranked by Douyin account">
          {summary.by_account.slice(0, 5).map((row, index) => {
            const rate = Math.max(0, Math.min(100, row.blocked_rate_percent));
            return <span key={row.account_id ?? `unknown-${index}`}><em><b>{row.account_id ? `Account ${row.account_id.slice(0, 8)}` : "Unattributed"}</b><small>{row.runs_total} runs</small></em><i><b style={{ width: `${rate}%` }} /></i><strong>{rate.toFixed(0)}%</strong><small>{row.failed_runs} failed - {row.parse_warning_runs} warnings</small></span>;
          })}
        </div>
      ) : (
        <div className="ops-home-v7-attribution-missing">
          <span><i /></span>
          <div><strong>Account attribution unavailable</strong><p>{summary.window_runs} fetch runs were recorded without a Douyin account association.</p></div>
          <div className="ops-home-v7-attribution-rate"><i><b style={{ width: `${Math.max(0, Math.min(100, summary.blocked_ratio_percent))}%` }} /></i><strong>{summary.blocked_ratio_percent.toFixed(0)}% blocked</strong></div>
        </div>
      )}
      <div className="ops-home-v6-reasons">{summary.top_blocked_reasons.slice(0, 3).map((item) => <span key={item.reason}>{formatLabel(item.reason)} <b>{item.count}</b></span>)}</div>
    </div>
  );
}

function DependencyReadiness({ summary }: { summary: OpsHomeSummaryResponse }) {
  const capacity = summary.storage_capacity;
  const accountExceptions = summary.account_health.filter((item) => item.is_on_hold || item.health_status !== "HEALTHY").length;
  const healthyAccounts = summary.account_health.length - accountExceptions;
  const accountSignal: OpsHomeDependencySignal = {
    key: "publishing_accounts",
    label: "Publishing accounts",
    state: accountExceptions > 0 ? "warning" : "ready",
    signal: `${healthyAccounts}/${summary.account_health.length} healthy - ${accountExceptions} exceptions`,
    impact: "Publish eligibility",
    observed_at: summary.freshness.control_queue_generated_at,
    href: "/publishing/accounts",
  };
  const signals = [...summary.dependencies, accountSignal];
  const groups = [
    { key: "control", index: "01", label: "Control plane", detail: "Requests and durable state", signalKeys: ["api", "database"] },
    { key: "execution", index: "02", label: "Execution", detail: "Queue wake-up and workers", signalKeys: ["worker", "redis"] },
    { key: "media", index: "03", label: "Media runtime", detail: "Artifacts and processing tools", signalKeys: ["storage", "ffmpeg"] },
    { key: "external", index: "04", label: "External & publishing", detail: "Providers and account eligibility", signalKeys: ["providers", "publishing_accounts"] },
  ];
  const readyCount = signals.filter((item) => item.state === "ready").length;
  const warningCount = signals.filter((item) => item.state === "warning" || item.state === "critical").length;
  const notObservedCount = signals.filter((item) => item.state === "not_observed").length;
  return (
    <div className="ops-home-v8-dependency-stack">
      <div className="ops-home-v8-dependency-summary" aria-label="Dependency state summary">
        <span className="is-ready"><i />{readyCount} Ready</span><span className="is-warning"><i />{warningCount} Attention</span><span className="is-muted"><i />{notObservedCount} Not observed</span>
      </div>
      <div className="ops-home-v8-dependency-layers">
        {groups.map((group) => {
          const groupSignals = signals.filter((item) => group.signalKeys.includes(item.key));
          return (
            <section className="ops-home-v8-dependency-layer" key={group.key}>
              <header><span>{group.index}</span><div><strong>{group.label}</strong><small>{group.detail}</small></div></header>
              <div className="ops-home-v8-dependency-nodes">
                {groupSignals.map((item) => (
                  <Link className={`is-${item.state}`} href={item.href ?? "/ops/health"} key={item.key}>
                    <i className="ops-home-v8-dependency-dot" />
                    <span><strong>{item.label}</strong><small>{item.signal} - {item.impact}</small>{item.key === "storage" && capacity.used_percent != null ? <span className="ops-home-v8-storage-meter"><i><b style={{ width: `${Math.min(100, capacity.used_percent)}%` }} /></i><em>{capacity.used_percent.toFixed(0)}% used</em></span> : null}</span>
                    <em>{formatLabel(item.state)}</em>
                  </Link>
                ))}
              </div>
            </section>
          );
        })}
      </div>
    </div>
  );
}

function FreshnessLedger({ summary }: { summary: OpsHomeSummaryResponse }) {
  const sources = [
    ["Jobs & pipeline", summary.freshness.metrics_generated_at],
    ["Publish outcomes", summary.freshness.publish_health_generated_at],
    ["Routing & accounts", summary.freshness.control_queue_generated_at],
  ];
  return <section className="ops-home-v6-freshness" aria-label="Read model check times"><strong>Read models checked</strong>{sources.map(([label, value]) => <span key={label}><em>{label}</em><time dateTime={value}>{formatDateTime(value)}</time></span>)}</section>;
}

export function OpsHomePage() {
  const t = useT();
  const [summary, setSummary] = useState<OpsHomeSummaryResponse | null>(null);
  const request = useLatestRequest();

  async function load(mode: LatestRequestMode = summary ? "refresh" : "initial") {
    await request.run(fetchOpsHomeSummary, setSummary, mode).catch(() => undefined);
  }

  useEffect(() => { void load("initial"); }, [t]);

  const refreshAction = <TopbarRefreshButton busy={request.refreshing} disabled={request.initialLoading} onClick={() => void load("refresh")} />;
  if (!summary) {
    const status = request.initialLoading ? "loading" : request.error ? "error" : "empty";
    return (
      <OpsConsoleShell actions={refreshAction} description={t("ops.description")} title={t("ops.title")}>
        <AsyncContentBoundary status={status} refreshing={request.refreshing} skeletonVariant="dashboard" loadingLabel={t("ops.loadingDetail")} errorState={<OpsState title={t("ops.unavailableTitle")} detail={request.error?.message ?? t("ops.unavailableTitle")} retry={() => void load("initial")} />}>{null}</AsyncContentBoundary>
      </OpsConsoleShell>
    );
  }

  return (
    <OpsConsoleShell actions={refreshAction} description={t("ops.description")} title={t("ops.title")}>
      <AsyncContentBoundary status="success" refreshing={request.refreshing}>
        <main className="ops-page ops-home-v6 ops-home-v7 ops-home-v9">
          {request.error ? <div className="inline-error">{request.error.message}</div> : null}
          <section className="ops-home-v7-command-stage">
            <OverviewHeader summary={summary} />
            <DecisionMetrics summary={summary} />
            <OperationalRibbon summary={summary} />
          </section>

          <HiddenRiskStrip risks={summary.hidden_risks} />

          <section className="ops-home-v6-primary-grid">
            <VisualPanel className="is-workload" title="Pipeline workload" subtitle="Actionable states by job type" action={<Link href="/ops/jobs">All jobs</Link>}><PipelineWorkloadChart rows={summary.job_health} /></VisualPanel>
            <VisualPanel className="is-incidents" title="Incident queue" subtitle="Context and recommended next action" action={<Link href="/ops/jobs">Open monitor</Link>}><IncidentQueue checkedAt={summary.freshness.generated_at} items={summary.action_items} /></VisualPanel>
          </section>

          <section className="ops-home-v6-analytics-grid">
            <VisualPanel className="is-publish" title="Publish outcomes - 7 days" subtitle="Daily volume and result mix" action={<Link href="/ops/publish-health">Details</Link>}><PublishOutcomeChart days={summary.publish_trend} /></VisualPanel>
            <VisualPanel className="is-failure" title="Failure Pareto" subtitle="Recurring causes ranked by impact"><FailurePareto rows={summary.failure_signatures} /></VisualPanel>
          </section>

          <section className="ops-home-v6-analytics-grid">
            <VisualPanel className="is-fetch" title="Douyin fetch health" subtitle="Blocked rate ranked by account" action={<Link href="/ops/health">Health</Link>}><FetchHealthChart summary={summary.fetch_health} /></VisualPanel>
            <VisualPanel className="is-dependencies" title="Dependency readiness" subtitle="Missing telemetry is never treated as healthy" action={<Link href="/ops/health">System health</Link>}><DependencyReadiness summary={summary} /></VisualPanel>
          </section>

          <FreshnessLedger summary={summary} />
        </main>
      </AsyncContentBoundary>
    </OpsConsoleShell>
  );
}
