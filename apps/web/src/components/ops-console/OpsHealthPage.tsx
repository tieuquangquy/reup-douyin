"use client";

import Link from "next/link";
import { useEffect, useState, type ReactNode } from "react";
import { fetchOperationalMetrics, fetchOpsHomeSummary, fetchPublishHealthDashboard } from "../../lib/api";
import { useT } from "../../lib/i18n";
import { useLatestRequest } from "../../lib/useLatestRequest";
import type { PublishDayStats, PublishHealthDashboard } from "../../types/analytics";
import type {
  OperationalMetrics,
  OpsAssetReuseSummary,
  OpsFetchHealthAccountSummary,
  OpsHomeHiddenRisk,
  OpsHomeSummaryResponse,
} from "../../types/operations";
import { OpsConsoleShell } from "../app-shell/OpsConsoleShell";
import { TopbarRefreshButton } from "../app-shell/TopbarRefreshButton";
import { AsyncContentBoundary } from "../shared/AsyncContentBoundary";
import { useNotice } from "../shared/NoticeCenter";
import { WorkItemActionIcon, type WorkItemActionIconKind } from "../shared/WorkItemActionIcon";
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

function formatAge(value: string | null | undefined): string {
  if (!value) return "—";
  const timestamp = new Date(value).getTime();
  if (Number.isNaN(timestamp)) return "—";
  const seconds = Math.max(0, Math.floor((Date.now() - timestamp) / 1000));
  if (seconds < 60) return `${seconds}s`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h`;
  return `${Math.floor(seconds / 86400)}d`;
}

function jobStatusTotal(metrics: OperationalMetrics, status: string): number {
  return Object.values(metrics.job_counts_by_type_status).reduce(
    (total, statuses) => total + (Number(statuses[status]) || 0),
    0
  );
}

type DependencyRow = {
  key: string;
  label: string;
  status: string;
  tone: OpsTone;
  signal: string;
  freshness: string;
  impact: string;
  href?: string;
};

type IncidentRow = {
  id: string;
  severity: "critical" | "warning" | "info";
  area: string;
  title: string;
  detail: string;
  count: number;
  href: string;
};

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

function hiddenRiskTone(state: OpsHomeHiddenRisk["state"] | undefined): OpsTone {
  if (state === "clear") return "good";
  if (state === "watch") return "warn";
  if (state === "critical") return "danger";
  return "muted";
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

type HealthDecisionSignal = {
  key: string;
  label: string;
  value: string;
  status: string;
  tone: OpsTone;
  detail: string;
  href: string;
  icon: WorkItemActionIconKind;
};

function HealthFlowNode({ signal, index }: { signal: HealthDecisionSignal; index: number }) {
  return (
    <Link className={`ops-health-v4-flow-node tone-${signal.tone}`} href={signal.href}>
      <span className="ops-health-v4-flow-node__icon"><WorkItemActionIcon kind={signal.icon} /></span>
      <span className="ops-health-v4-flow-node__copy"><small>0{index + 1}</small><strong>{signal.label}</strong><em>{signal.detail}</em></span>
      <span className="ops-health-v4-flow-node__reading"><b>{signal.value}</b><small>{signal.status}</small></span>
    </Link>
  );
}

function HealthDecisionCanvas({
  incident,
  critical,
  warning,
  execution,
  storage,
  storageUsed,
  integrity,
  integritySegments,
}: {
  incident: HealthDecisionSignal;
  critical: number;
  warning: number;
  execution: HealthDecisionSignal[];
  storage: HealthDecisionSignal;
  storageUsed: number | null;
  integrity: HealthDecisionSignal;
  integritySegments: Array<{ label: string; value: number }>;
}) {
  const visibleIntegrity = integritySegments.filter((item) => item.value > 0).slice(0, 3);
  return (
    <section className="ops-health-v4-decision-canvas" aria-label="Operational health decision canvas">
      <Link className={`ops-health-v4-incident-focus tone-${incident.tone}`} href={incident.href}>
        <header><span><WorkItemActionIcon kind={incident.icon} /></span><div><small>Incident focus</small><strong>{incident.label}</strong></div><em>{incident.status}</em></header>
        <div className="ops-health-v4-incident-focus__reading"><strong>{incident.value}</strong><span>active signals</span></div>
        <p>{incident.detail}</p>
        <footer><span>Critical <b>{critical}</b></span><span>Warning <b>{warning}</b></span><i /></footer>
      </Link>

      <div className="ops-health-v4-diagnostics">
        <header className="ops-health-v4-diagnostics__head"><div><span>Execution path</span><h2>Can work move through the system?</h2></div><small>Live evidence chain</small></header>
        <div className="ops-health-v4-flow">{execution.map((signal, index) => <HealthFlowNode index={index} key={signal.key} signal={signal} />)}</div>
        <div className="ops-health-v4-foundation">
          <Link className={`ops-health-v4-foundation__storage tone-${storage.tone}`} href={storage.href}>
            <span className="ops-health-v4-foundation__icon"><WorkItemActionIcon kind={storage.icon} /></span>
            <span className="ops-health-v4-foundation__copy"><small>Foundation capacity</small><strong>{storage.label}</strong><em>{storage.detail}</em></span>
            <span className="ops-health-v4-foundation__reading"><b>{storage.value}</b><small>{storage.status}</small></span>
            <span className={`ops-health-v4-capacity${storageUsed == null ? " is-unobserved" : ""}`}><i><b style={{ width: `${Math.max(0, Math.min(100, storageUsed ?? 0))}%` }} /></i><small>{storageUsed == null ? "No measurement" : `${storageUsed.toFixed(0)}% used`}</small></span>
          </Link>
          <Link className={`ops-health-v4-foundation__integrity tone-${integrity.tone}`} href={integrity.href}>
            <span className="ops-health-v4-foundation__icon"><WorkItemActionIcon kind={integrity.icon} /></span>
            <span className="ops-health-v4-foundation__copy"><small>Contract assurance</small><strong>{integrity.label}</strong><em>{integrity.detail}</em></span>
            <span className="ops-health-v4-foundation__reading"><b>{integrity.value}</b><small>{integrity.status}</small></span>
            <span className="ops-health-v4-integrity-evidence">{visibleIntegrity.length ? visibleIntegrity.map((item) => <small key={item.label}>{item.label} <b>{item.value}</b></small>) : <small>No integrity exception</small>}</span>
          </Link>
        </div>
      </div>
    </section>
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
    return <div className="ops-health-queue-clear"><i /><span><strong>Queue is clear</strong><small>No queued, running, or retryable work.</small></span></div>;
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

function PublishColumnChart({
  days,
  overview,
  emptyLabel,
  generatedAt,
  labels,
}: {
  days: PublishDayStats[];
  overview: PublishHealthDashboard["overview"] | null;
  emptyLabel: string;
  generatedAt: string | null;
  labels: {
    attempts: string;
    succeeded: string;
    failed: string;
    reconciliation: string;
    blocked: string;
    successRate: string;
    generated: string;
  };
}) {
  const dayAttempts = days.reduce((sum, day) => sum + day.attempts, 0);
  const totalAttempts = overview?.total_attempts ?? dayAttempts;
  const succeeded = overview?.succeeded_attempts ?? days.reduce((sum, day) => sum + day.succeeded, 0);
  const failed = overview?.failed_attempts ?? days.reduce((sum, day) => sum + day.failed, 0);
  const reconciliation = days.reduce((sum, day) => sum + day.needs_reconciliation, 0);
  const blocked = overview?.drafts_blocked_by_risk ?? 0;
  const successRate = overview?.success_rate_percent ?? (totalAttempts > 0 ? (succeeded / totalAttempts) * 100 : 0);
  const maxAttempts = Math.max(...days.map((day) => day.attempts), 1);
  const axisCeiling = maxAttempts <= 1 ? 2 : Math.ceil(maxAttempts * 1.2);
  const axisMidpoint = axisCeiling / 2;
  const formatAxisTick = (value: number) => Number.isInteger(value) ? String(value) : value.toFixed(1);

  return (
    <div className="ops-health-v10-columns">
      <header className="ops-health-v10-columns__head">
        <div><strong>{succeeded}/{totalAttempts}</strong><span>{labels.succeeded}</span><b>{successRate.toFixed(0)}% {labels.successRate}</b></div>
        <nav aria-label={labels.attempts}>
          <span className="is-success"><i />{labels.succeeded} <b>{succeeded}</b></span>
          <span className="is-failed"><i />{labels.failed} <b>{failed}</b></span>
          <span className="is-reconciliation"><i />{labels.reconciliation} <b>{reconciliation}</b></span>
        </nav>
      </header>

      {days.length === 0 || totalAttempts === 0 ? (
        <p className="ops-health-v10-columns__empty">{emptyLabel}</p>
      ) : (
        <div className="ops-health-v10-columns__plot" role="img" aria-label={days.map((day) => `${day.day}: ${day.attempts}`).join(", ")}>
          <aside><span>{axisCeiling}</span><span>{formatAxisTick(axisMidpoint)}</span><span>0</span></aside>
          <section>
            <div className="ops-health-v10-columns__grid" aria-hidden="true"><i /><i /><i /></div>
            <div className="ops-health-v10-columns__days">
              {days.map((day) => {
                const height = (day.attempts / axisCeiling) * 100;
                const other = Math.max(day.attempts - day.succeeded - day.failed - day.needs_reconciliation, 0);
                return (
                  <div key={day.day} title={`${day.day}: ${day.attempts} ${labels.attempts}`}>
                    <span className="ops-health-v10-columns__slot">
                      {day.attempts > 0 ? (
                        <span className="ops-health-v10-columns__bar" style={{ height: `${height}%` }}>
                          <b>{day.attempts}</b>
                          <i className="is-success" style={{ flexGrow: day.succeeded }} />
                          <i className="is-failed" style={{ flexGrow: day.failed }} />
                          <i className="is-reconciliation" style={{ flexGrow: day.needs_reconciliation }} />
                          <i className="is-other" style={{ flexGrow: other }} />
                        </span>
                      ) : <i className="ops-health-v10-columns__zero" />}
                    </span>
                    <time dateTime={day.day}>{formatDayLabel(day.day)}</time>
                  </div>
                );
              })}
            </div>
          </section>
        </div>
      )}

      <footer>
        <span>{labels.blocked} <b>{blocked}</b></span>
        <span>{labels.generated}: <time dateTime={generatedAt ?? undefined}>{generatedAt ? formatDateTime(generatedAt) : "—"}</time></span>
      </footer>
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

function PipelineVolumeChart({
  rows,
  emptyLabel,
  completedLabel,
}: {
  rows: Array<{ jobType: string; statuses: Record<string, number>; total: number }>;
  emptyLabel: string;
  completedLabel: string;
}) {
  if (rows.length === 0) return <p className="ops-health-empty">{emptyLabel}</p>;
  const maxTotal = Math.max(...rows.map((row) => row.total), 1);
  return (
    <div className="ops-health-v8-pipeline" role="img" aria-label={rows.map((row) => `${formatStatusChipLabel(row.jobType)} ${row.total}`).join(", ")}>
      {rows.map((row) => {
        const completed = Number(row.statuses.COMPLETED) || 0;
        const volumeWidth = (row.total / maxTotal) * 100;
        const completedWidth = row.total > 0 ? (completed / row.total) * 100 : 0;
        return (
          <div className="ops-health-v8-pipeline__row" key={row.jobType} title={`${formatStatusChipLabel(row.jobType)} · ${completed}/${row.total} ${completedLabel}`}>
            <span>{formatStatusChipLabel(row.jobType)}</span>
            <i><b style={{ width: `${volumeWidth}%` }}><em style={{ width: `${completedWidth}%` }} /></b></i>
            <strong>{row.total}</strong>
          </div>
        );
      })}
    </div>
  );
}

function OutputCompositionChart({
  records,
  labels,
  emptyLabel,
}: {
  records: Array<{ key: string; record: Record<string, number> }>;
  labels: Record<string, string>;
  emptyLabel: string;
}) {
  const sections = records.map((section) => ({ ...section, entries: countEntries(section.record) })).filter((section) => section.entries.length > 0);
  if (sections.length === 0) return <p className="ops-health-empty">{emptyLabel}</p>;
  return (
    <div className="ops-health-v8-outcomes">
      {sections.map((section) => {
        const total = section.entries.reduce((sum, entry) => sum + entry.count, 0);
        return (
          <div className="ops-health-v8-outcomes__section" key={section.key}>
            <header><strong>{labels[section.key]}</strong><small>{total}</small></header>
            <div className="ops-health-v8-outcomes__bar" role="img" aria-label={`${labels[section.key]} ${total}`}>
              {section.entries.map((entry) => (
                <i className={`is-${formatStatusChipLabel(entry.key).toLowerCase().replace(/\s+/g, "-")}`} key={entry.key} style={{ flexGrow: entry.count, flexBasis: 0 }} title={`${formatStatusChipLabel(entry.key)}: ${entry.count}`} />
              ))}
            </div>
            <footer>{section.entries.map((entry) => <span key={entry.key}><i className={`is-${formatStatusChipLabel(entry.key).toLowerCase().replace(/\s+/g, "-")}`} />{formatStatusChipLabel(entry.key)} <b>{entry.count}</b></span>)}</footer>
          </div>
        );
      })}
    </div>
  );
}

function AssetReusePlot({ assets, emptyLabel, labels }: { assets: OpsAssetReuseSummary[]; emptyLabel: string; labels: { current: string; historical: string } }) {
  if (assets.length === 0) return <p className="ops-health-empty">{emptyLabel}</p>;
  const maxValue = Math.max(...assets.flatMap((asset) => [asset.current_count, asset.historical_count]), 1);
  return (
    <div className="ops-health-v8-assets">
      <div className="ops-health-v8-assets__legend"><span><i className="is-current" />{labels.current}</span><span><i className="is-historical" />{labels.historical}</span></div>
      {assets.map((asset) => (
        <div className="ops-health-v8-assets__row" key={asset.asset_type} title={`${asset.asset_type}: ${asset.current_count} / ${asset.historical_count}`}>
          <code>{asset.asset_type}</code>
          <i><b style={{ width: `${(asset.current_count / maxValue) * 100}%` }} /><em style={{ left: `${(asset.historical_count / maxValue) * 100}%` }} /></i>
          <strong>{asset.current_count}<small>/{asset.historical_count}</small></strong>
        </div>
      ))}
    </div>
  );
}

function RiskSeverityRail({ entries, emptyLabel, openLabel }: { entries: Array<{ key: string; count: number }>; emptyLabel: string; openLabel: string }) {
  if (entries.length === 0) return <p className="ops-health-empty">{emptyLabel}</p>;
  const total = entries.reduce((sum, entry) => sum + entry.count, 0);
  return (
    <div className="ops-health-v8-risk-rail">
      <div className="ops-health-v8-risk-rail__headline"><strong>{total}</strong><span>{openLabel}</span></div>
      <div className="ops-health-v8-risk-rail__bar" role="img" aria-label={entries.map((entry) => `${formatStatusChipLabel(entry.key)} ${entry.count}`).join(", ")}>
        {entries.map((entry) => <i className={`tone-${riskTone(entry.key)}`} key={entry.key} style={{ flexGrow: entry.count, flexBasis: 0 }} title={`${formatStatusChipLabel(entry.key)}: ${entry.count}`} />)}
      </div>
      <footer>{entries.map((entry) => <span key={entry.key}><i className={`tone-${riskTone(entry.key)}`} />{formatStatusChipLabel(entry.key)} <b>{entry.count}</b></span>)}</footer>
    </div>
  );
}

function SignalPareto({ entries, emptyLabel }: { entries: Array<{ key: string; count: number }>; emptyLabel: string }) {
  if (entries.length === 0) return <p className="ops-health-empty">{emptyLabel}</p>;
  const peak = Math.max(...entries.map((entry) => entry.count), 1);
  return (
    <div className="ops-health-v8-pareto">
      {entries.map((entry) => (
        <div className="ops-health-v8-pareto__row" key={entry.key} title={`${entry.key}: ${entry.count}`}>
          <code>{entry.key}</code><i><b style={{ width: `${(entry.count / peak) * 100}%` }} /></i><strong>{entry.count}</strong>
        </div>
      ))}
    </div>
  );
}

function FetchSignalVisual({ fetchHealth, labels }: { fetchHealth: NonNullable<OperationalMetrics["douyin_fetch_health"]>; labels: { runs: string; blocked: string; failed: string; parse: string } }) {
  const runs = Math.max(0, fetchHealth.window_runs);
  const blockedShare = runs > 0 ? Math.min(100, (fetchHealth.blocked_runs / runs) * 100) : 0;
  const failedShare = runs > 0 ? Math.min(100 - blockedShare, (fetchHealth.failed_runs / runs) * 100) : 0;
  const failedEnd = blockedShare + failedShare;
  const ring = runs > 0
    ? `conic-gradient(#f1b33a 0 ${blockedShare}%, #e25c72 ${blockedShare}% ${failedEnd}%, #dcebef ${failedEnd}% 100%)`
    : "#e8eff1";
  return (
    <div className="ops-health-v8-fetch-visual">
      <div className="ops-health-v8-fetch-visual__ring" style={{ background: ring }} role="img" aria-label={`${runs} ${labels.runs}`}><strong>{runs}</strong><small>{labels.runs}</small></div>
      <div className="ops-health-v8-fetch-visual__legend">
        <span><i className="is-blocked" /><b>{fetchHealth.blocked_runs}</b>{labels.blocked}</span>
        <span><i className="is-failed" /><b>{fetchHealth.failed_runs}</b>{labels.failed}</span>
        <span><i className="is-parse" /><b>{fetchHealth.parse_warning_runs}</b>{labels.parse}</span>
      </div>
    </div>
  );
}

function FailureRateVisual({ entries, clearLabel }: { entries: Array<{ key: string; count: number }>; clearLabel: string }) {
  if (entries.length === 0) return null;
  const allClear = entries.every((entry) => entry.count <= 0);
  if (allClear) return <div className="ops-health-v8-assurance"><i>✓</i><strong>0%</strong><span>{clearLabel.replace("{count}", String(entries.length))}</span></div>;
  const peak = Math.max(...entries.map((entry) => entry.count), 1);
  return <div className="ops-health-v8-failure-rates">{entries.map((entry) => <div key={entry.key}><span>{formatStatusChipLabel(entry.key)}</span><i><b style={{ width: `${(entry.count / peak) * 100}%` }} /></i><strong>{entry.count.toFixed(0)}%</strong></div>)}</div>;
}

function DependencyNode({ row }: { row: DependencyRow }) {
  const body = (
    <>
      <span className={`ops-health-v2-dependency__status tone-${row.tone}`}><i />{row.status}</span>
      <strong>{row.label}</strong>
      <p>{row.signal}</p>
      <footer><span>{row.impact}</span><time>{row.freshness}</time></footer>
    </>
  );
  return row.href ? <Link className={`ops-health-v2-dependency tone-${row.tone}`} href={row.href}>{body}</Link> : <div className={`ops-health-v2-dependency tone-${row.tone}`}>{body}</div>;
}

function DependencyTopology({ rows }: { rows: DependencyRow[] }) {
  const groups = [
    { key: "control", index: "01", label: "Control plane", detail: "Request and durable state", keys: ["api", "database", "db"] },
    { key: "execution", index: "02", label: "Execution", detail: "Queue wake-up and workers", keys: ["worker", "redis"] },
    { key: "media", index: "03", label: "Media runtime", detail: "Storage and processing tools", keys: ["storage", "ffmpeg"] },
    { key: "external", index: "04", label: "External", detail: "Provider readiness", keys: ["providers"] },
  ];
  const ready = rows.filter((row) => row.tone === "good").length;
  const attention = rows.filter((row) => row.tone === "warn" || row.tone === "danger").length;
  const unknown = rows.filter((row) => row.tone === "muted").length;
  return (
    <div className="ops-health-v2-topology ops-health-v3-topology-map">
      <div className="ops-health-v2-topology__summary" aria-label="Dependency readiness summary">
        <span className="is-ready"><i /><b>{ready}</b> ready</span>
        <span className="is-attention"><i /><b>{attention}</b> attention</span>
        <span className="is-unknown"><i /><b>{unknown}</b> not observed</span>
      </div>
      <div className="ops-health-v2-topology__spine">
        {groups.map((group) => {
          const signals = rows.filter((row) => group.keys.includes(row.key));
          if (signals.length === 0) return null;
          return (
            <section className="ops-health-v2-layer" key={group.key}>
              <header><span>{group.index}</span><div><strong>{group.label}</strong><small>{group.detail}</small></div></header>
              <div>{signals.map((row) => <DependencyNode key={row.key} row={row} />)}</div>
            </section>
          );
        })}
      </div>
    </div>
  );
}

function HiddenRiskLedger({ risks }: { risks: OpsHomeHiddenRisk[] }) {
  if (risks.length === 0) return <p className="ops-health-empty">Hidden-risk evidence is unavailable.</p>;
  return (
    <div className="ops-health-v2-risk-ledger">
      {risks.map((risk, index) => {
        const numeric = typeof risk.value === "number" ? risk.value : 0;
        const fill = risk.key === "observability_coverage" ? numeric : risk.key === "retry_amplification" ? Math.min(100, Math.max(0, (numeric - 1) * 100)) : Math.min(100, numeric * 20);
        const evidence = risk.segments.filter((segment) => segment.value > 0).slice(0, 3);
        return (
          <Link className={`ops-health-v2-risk is-${risk.state}`} href={risk.href} key={risk.key}>
            <span className="ops-health-v2-risk__index">{String(index + 1).padStart(2, "0")}</span>
            <span className="ops-health-v2-risk__copy"><em>{risk.label}</em><strong>{risk.detail}</strong></span>
            <span className="ops-health-v2-risk__measure"><b>{risk.display_value}</b><i><span style={{ width: `${fill}%` }} /></i></span>
            <span className="ops-health-v2-risk__evidence">{evidence.length ? evidence.map((item) => <small key={item.key}>{item.label} <b>{item.value}</b></small>) : <small>No exception</small>}</span>
          </Link>
        );
      })}
    </div>
  );
}

export function OpsHealthPage() {
  const t = useT();
  const [metrics, setMetrics] = useState<OperationalMetrics | null>(null);
  const [publishHealth, setPublishHealth] = useState<PublishHealthDashboard | null>(null);
  const [homeSummary, setHomeSummary] = useState<OpsHomeSummaryResponse | null>(null);
  const request = useLatestRequest();
  const { notify } = useNotice();

  async function load() {
    const mode = metrics ? "refresh" : "initial";
    try {
      await request.run(async () => {
        const [metricsPayload, healthPayload, homePayload] = await Promise.all([
          fetchOperationalMetrics(),
          fetchPublishHealthDashboard("last_7_days"),
          fetchOpsHomeSummary().catch(() => null),
        ]);
        return { metricsPayload, healthPayload, homePayload };
      }, ({ metricsPayload, healthPayload, homePayload }) => {
        setMetrics(metricsPayload);
        setPublishHealth(healthPayload);
        setHomeSummary(homePayload);
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
        <AsyncContentBoundary skeletonVariant="dashboard" loadingLabel={t("opsHealth.loadingDetail")} status="loading"><span /></AsyncContentBoundary>
      </OpsConsoleShell>
    );
  }

  if (request.error && !metrics) {
    return (
      <OpsConsoleShell actions={refreshAction} description={t("opsHealth.description")} title={t("opsHealth.title")}>
        <AsyncContentBoundary errorState={<OpsState title={t("opsHealth.unavailableTitle")} detail={request.error.message} retry={() => void load()} />} skeletonVariant="dashboard" status="error"><span /></AsyncContentBoundary>
      </OpsConsoleShell>
    );
  }

  const riskOpen = metrics ? sumRecord(metrics.open_risk_counts_by_severity) : 0;
  const fetchHealth = metrics?.douyin_fetch_health;
  const failureCategories = (metrics?.common_failure_categories ?? []).slice(0, 5);
  const riskEntries = metrics ? countEntries(metrics.open_risk_counts_by_severity) : [];
  const failureRates = metrics ? countEntries(metrics.job_failure_rate_percent_by_type).slice(0, 5) : [];
  const avgProcessing = metrics?.average_processing_seconds_per_source_video ?? 0;
  const topBlocked = fetchHealth?.top_blocked_reasons.slice(0, 3) ?? [];
  const publishDays = homeSummary?.publish_trend ?? publishHealth?.by_day ?? [];
  const publishOverview = publishHealth ? publishHealth.overview : null;
  const assetRows = [...(metrics?.asset_reuse_by_type ?? [])]
    .sort((a, b) => b.current_count - a.current_count || a.asset_type.localeCompare(b.asset_type))
    .slice(0, 5);
  const fetchAccounts = topFetchAccounts(fetchHealth?.by_account, 3);
  const jobMatrix = buildJobMatrix(metrics?.job_counts_by_type_status, 6);
  const assetCurrentTotal = (metrics?.asset_reuse_by_type ?? []).reduce((sum, row) => sum + row.current_count, 0);
  const failedJobs = metrics ? jobStatusTotal(metrics, "FAILED") : 0;
  const retryableJobs = metrics?.queue_backlog.retryable ?? 0;
  const queueAttention = (metrics?.queue_backlog.queued ?? 0) + retryableJobs;
  const activeWorkload = (metrics?.queue_backlog.queued ?? 0) + (metrics?.queue_backlog.running ?? 0) + retryableJobs;
  const workerUnclaimed = metrics?.queue_backlog.running_without_lock ?? 0;
  const activeWorkers = metrics?.queue_backlog.active_worker_count ?? 0;
  const oldestQueuedAge = formatAge(metrics?.queue_backlog.oldest_queued_at);
  const admission = homeSummary?.admission_verdict;
  const observabilityRisk = homeSummary?.hidden_risks.find((risk) => risk.key === "observability_coverage");
  const integrityRisk = homeSummary?.hidden_risks.find((risk) => risk.key === "integrity_debt");
  const retryRisk = homeSummary?.hidden_risks.find((risk) => risk.key === "retry_amplification");
  const trueRetryClaims = retryRisk?.segments.find((segment) => segment.key === "retry_claims")?.value ?? 0;
  const dependencies: DependencyRow[] = homeSummary
    ? homeSummary.dependencies.map((row) => ({
        key: row.key,
        label: row.label,
        status: formatStatusChipLabel(row.state),
        tone: row.state === "ready" ? "good" : row.state === "warning" ? "warn" : row.state === "critical" ? "danger" : "muted",
        signal: row.signal,
        freshness: row.observed_at ? formatAge(row.observed_at) : t("opsHealth.notObserved"),
        impact: row.impact,
        href: row.href ?? undefined,
      }))
    : metrics
    ? [
        {
          key: "api",
          label: t("opsHealth.api"),
          status: t("opsHealth.responding"),
          tone: "good",
          signal: t("opsHealth.metricsEndpointResponded"),
          freshness: formatAge(metrics.generated_at),
          impact: t("opsHealth.impactControlPlane"),
        },
        {
          key: "db",
          label: t("opsHealth.db"),
          status: t("opsHealth.queryOk"),
          tone: "good",
          signal: t("opsHealth.metricsQueryCompleted"),
          freshness: formatAge(metrics.generated_at),
          impact: t("opsHealth.impactPersistence"),
        },
        {
          key: "worker",
          label: t("opsHealth.worker"),
          status:
            workerUnclaimed > 0
              ? t("opsHealth.needsAttention")
              : metrics.queue_backlog.running > 0
                ? t("opsHealth.active")
                : t("opsHealth.idle"),
          tone: workerUnclaimed > 0 ? "danger" : metrics.queue_backlog.running > 0 ? "good" : "muted",
          signal:
            workerUnclaimed > 0
              ? t("opsHealth.runningWithoutLock").replace("{count}", String(workerUnclaimed))
              : t("opsHealth.workerSignal")
                  .replace("{workers}", String(activeWorkers))
                  .replace("{running}", String(metrics.queue_backlog.running)),
          freshness: metrics.queue_backlog.running > 0 ? t("opsHealth.live") : t("opsHealth.idle"),
          impact: t("opsHealth.impactProcessing"),
          href: "/ops/jobs?status=RUNNING",
        },
        {
          key: "redis",
          label: t("opsHealth.redis"),
          status: t("opsHealth.notObserved"),
          tone: "muted",
          signal: t("opsHealth.noDedicatedRedisEndpoint"),
          freshness: "—",
          impact: t("opsHealth.impactQueueWakeup"),
        },
        {
          key: "storage",
          label: t("opsHealth.storage"),
          status: t("opsHealth.indexObserved"),
          tone: "muted",
          signal: t("opsHealth.assetIndexSignal").replace("{count}", String(assetCurrentTotal)),
          freshness: formatAge(metrics.generated_at),
          impact: t("opsHealth.impactMedia"),
          href: "/ops/assets",
        },
      ]
    : [];
  const unobservedDependencies = dependencies.filter((row) => row.tone === "muted");
  const fallbackIncidents: IncidentRow[] = metrics
    ? [
        workerUnclaimed > 0
          ? {
              id: "worker-unclaimed",
              severity: "critical" as const,
              area: t("opsHealth.worker"),
              title: t("opsHealth.runningWithoutWorkerTitle"),
              detail: t("opsHealth.runningWithoutLock").replace("{count}", String(workerUnclaimed)),
              count: workerUnclaimed,
              href: "/ops/jobs?status=RUNNING",
            }
          : null,
        failedJobs > 0
          ? {
              id: "failed-jobs",
              severity: "critical" as const,
              area: t("opsHealth.jobsArea"),
              title: t("opsHealth.failedJobsTitle"),
              detail: t("opsHealth.failedJobsDetail"),
              count: failedJobs,
              href: "/ops/jobs?status=FAILED",
            }
          : null,
        retryableJobs > 0
          ? {
              id: "retryable-jobs",
              severity: "warning" as const,
              area: t("opsHealth.jobsArea"),
              title: t("opsHealth.retryableJobsTitle"),
              detail: t("opsHealth.retryableJobsDetail"),
              count: retryableJobs,
              href: "/ops/jobs?status=RETRYABLE",
            }
          : null,
        riskOpen > 0
          ? {
              id: "open-risk",
              severity: "warning" as const,
              area: t("opsHealth.risk"),
              title: t("opsHealth.openRiskTitle"),
              detail: t("opsHealth.openRiskDetail"),
              count: riskOpen,
              href: "/ops/risk",
            }
          : null,
        (fetchHealth?.blocked_runs ?? 0) + (fetchHealth?.failed_runs ?? 0) > 0
          ? {
              id: "fetch-degraded",
              severity: "warning" as const,
              area: "Douyin",
              title: t("opsHealth.fetchDegradedTitle"),
              detail: t("opsHealth.fetchDegradedDetail"),
              count: (fetchHealth?.blocked_runs ?? 0) + (fetchHealth?.failed_runs ?? 0),
              href: "/publishing/accounts",
            }
          : null,
      ].filter(Boolean) as IncidentRow[]
    : [];
  const incidents: IncidentRow[] = homeSummary
    ? homeSummary.action_items
        .filter((item) => item.severity !== "info")
        .map((item) => ({ id: item.id, severity: item.severity, area: item.area, title: item.title, detail: item.detail, count: item.count, href: item.href }))
    : fallbackIncidents;
  const sortedIncidents = [...incidents].sort((left, right) => {
    const severityOrder = { critical: 0, warning: 1, info: 2 };
    return severityOrder[left.severity] - severityOrder[right.severity] || right.count - left.count;
  });
  const visibleIncidents = sortedIncidents.slice(0, 5);
  const incidentPeak = Math.max(...visibleIncidents.map((incident) => incident.count), 1);
  const topImpactIncident = visibleIncidents.find((incident) => incident.count === incidentPeak);
  const visibleIncidentGroups = (["critical", "warning"] as const)
    .map((severity) => ({
      severity,
      total: incidents.filter((incident) => incident.severity === severity).length,
      items: visibleIncidents.filter((incident) => incident.severity === severity),
    }))
    .filter((group) => group.items.length > 0);
  const commandState = admission?.status === "pause" ? "critical" : admission?.status === "caution" ? "warning" : admission?.status === "safe" ? "healthy" : incidents.some((item) => item.severity === "critical") ? "critical" : incidents.length > 0 ? "warning" : "healthy";
  const commandLabel = admission?.label ?? (incidents.length > 0 ? t("opsHealth.attentionRequired") : t("opsHealth.allObservedHealthy"));
  const commandDetail = admission?.detail ?? (incidents.length > 0 ? t("opsHealth.activeIncidentCount").replace("{count}", String(incidents.length)) : t("opsHealth.noActiveIncidents"));
  const storage = homeSummary?.storage_capacity;
  const storageTone: OpsTone = storage?.state === "critical" ? "danger" : storage?.state === "warning" ? "warn" : storage?.state === "ready" ? "good" : "muted";
  const criticalSignalCount = homeSummary?.overall.critical_count ?? incidents.filter((item) => item.severity === "critical").length;
  const warningSignalCount = homeSummary?.overall.warning_count ?? incidents.filter((item) => item.severity === "warning").length;
  const incidentSignal: HealthDecisionSignal = {
    key: "incidents",
    label: t("opsHealth.activeIncidents"),
    value: String(incidents.length),
    status: incidents.length > 0 ? t("opsHealth.badgeAttention") : t("opsHealth.badgeHealthy"),
    tone: incidents.length > 0 ? "danger" : "good",
    detail: incidents.length > 0 ? t("opsHealth.activeIncidentCount").replace("{count}", String(incidents.length)) : t("opsHealth.noActiveIncidentsHelp"),
    href: incidents[0]?.href ?? "/ops/jobs",
    icon: "details",
  };
  const executionSignals: HealthDecisionSignal[] = [
    {
      key: "queue",
      label: t("opsHealth.queueAttention"),
      value: String(queueAttention),
      status: queueAttention > 0 ? t("opsHealth.badgeAttention") : t("opsHealth.badgeHealthy"),
      tone: queueAttention > 0 ? "warn" : "good",
      detail: metrics.queue_backlog.queued > 0 ? `Oldest queued ${oldestQueuedAge}` : "No queued or retryable work",
      href: "/ops/jobs",
      icon: "process",
    },
    {
      key: "observability",
      label: "Observability coverage",
      value: observabilityRisk?.display_value ?? "Not observed",
      status: observabilityRisk ? formatStatusChipLabel(observabilityRisk.state) : t("opsHealth.notObserved"),
      tone: hiddenRiskTone(observabilityRisk?.state),
      detail: observabilityRisk?.detail ?? "No canonical lock-coverage evidence.",
      href: observabilityRisk?.href ?? "/ops/jobs?status=RUNNING",
      icon: "recheck",
    },
    {
      key: "workers",
      label: t("opsHealth.activeWorkers"),
      value: String(activeWorkers),
      status: workerUnclaimed > 0 ? t("opsHealth.badgeAttention") : activeWorkers > 0 ? t("opsHealth.badgeHealthy") : t("opsHealth.badgeInfo"),
      tone: workerUnclaimed > 0 ? "danger" : activeWorkers > 0 ? "good" : "muted",
      detail: `${metrics.queue_backlog.running_with_lock} locked · ${metrics.queue_backlog.running_without_lock} without lock`,
      href: "/ops/jobs?status=RUNNING",
      icon: "play",
    },
  ];
  const storageSignal: HealthDecisionSignal = {
    key: "storage",
    label: "Storage headroom",
    value: storage?.free_gb != null ? `${storage.free_gb.toFixed(1)} GB` : "Not observed",
    status: storage ? formatStatusChipLabel(storage.state) : t("opsHealth.notObserved"),
    tone: storageTone,
    detail: storage?.detail ?? "Capacity probe has no current measurement.",
    href: "/ops/assets",
    icon: "open",
  };
  const integritySignal: HealthDecisionSignal = {
    key: "integrity",
    label: "Integrity debt",
    value: integrityRisk?.display_value ?? "Not observed",
    status: integrityRisk ? formatStatusChipLabel(integrityRisk.state) : t("opsHealth.notObserved"),
    tone: hiddenRiskTone(integrityRisk?.state),
    detail: integrityRisk?.detail ?? "No canonical integrity evidence.",
    href: integrityRisk?.href ?? "/ops/health",
    icon: "recheck",
  };

  return (
    <OpsConsoleShell actions={refreshAction} description={t("opsHealth.description")} title={t("opsHealth.title")}>
      <AsyncContentBoundary refreshing={request.refreshing} skeletonVariant="dashboard" status="success">
      <main className="ops-page ops-health-page is-dense">
        {metrics ? (
          <>
            <section className={`ops-health-command ops-health-v2-command is-${commandState}`}>
              <div className="ops-health-v2-command__beacon" aria-hidden="true"><i /><b /><span /></div>
              <div className="ops-health-v2-command__copy">
                <span className="ops-health-command__eyebrow">System admission</span>
                <h2>{commandLabel}</h2>
                <p>{commandDetail}</p>
                {admission?.reasons.length ? <small>{admission.reasons.slice(0, 3).join(" · ")}</small> : null}
              </div>
              <div className="ops-health-v2-command__meta">
                <span>{t("opsHealth.metricsGenerated")}</span>
                <time dateTime={metrics.generated_at} title={metrics.generated_at}>{formatDateTime(metrics.generated_at)}</time>
                <em>{dependencies.filter((row) => row.tone === "good").length}/{dependencies.length} dependencies ready</em>
              </div>
              <nav className="ops-health-actions ops-health-v2-actions" aria-label={t("opsHealth.triageActions")}>
                <Link href="/ops/jobs?status=RUNNING"><WorkItemActionIcon className="ops-health-v2-action__icon" kind="play" />{t("opsHealth.openRunning")}</Link>
                <Link href="/ops/jobs?status=FAILED"><WorkItemActionIcon className="ops-health-v2-action__icon" kind="details" />{t("opsHealth.openFailed")}</Link>
                <Link href="/ops/jobs?status=RETRYABLE"><WorkItemActionIcon className="ops-health-v2-action__icon" kind="retry" />{t("opsHealth.openRetryable")}</Link>
                <Link href="/ops/risk"><WorkItemActionIcon className="ops-health-v2-action__icon" kind="recheck" />{t("opsHealth.openRisk")}</Link>
                <Link href="/ops/publish-health"><WorkItemActionIcon className="ops-health-v2-action__icon" kind="open" />{t("opsHealth.openPublishHealth")}</Link>
              </nav>
            </section>

            <HealthDecisionCanvas
              critical={criticalSignalCount}
              execution={executionSignals}
              incident={incidentSignal}
              integrity={integritySignal}
              integritySegments={(integrityRisk?.segments ?? []).map((item) => ({ label: item.label, value: item.value }))}
              storage={storageSignal}
              storageUsed={storage?.used_percent ?? null}
              warning={warningSignalCount}
            />

            <section className="ops-health-primary-grid ops-health-v3-primary-grid">
              <section className="ops-health-panel ops-health-dependencies ops-health-v2-readiness ops-health-v3-system-map">
                <div className="ops-health-panel__head">
                  <div>
                    <span className="ops-health-panel__eyebrow">{t("opsHealth.observedSignals")}</span>
                    <h2>{t("opsHealth.systemDependencies")}</h2>
                  </div>
                </div>
                <DependencyTopology rows={dependencies} />
              </section>

              <section className="ops-health-panel ops-health-incidents ops-health-v3-incidents">
                <div className="ops-health-panel__head">
                  <div>
                    <span className="ops-health-panel__eyebrow">{t("opsHealth.triage")}</span>
                    <h2>{t("opsHealth.activeIncidents")}</h2>
                  </div>
                </div>
                {incidents.length > 0 ? (
                  <div className="ops-health-incident-list ops-health-v7-ledger">
                    {visibleIncidentGroups.map((group) => (
                      <section className={`ops-health-v7-ledger__group is-${group.severity}`} key={group.severity}>
                        <header>
                          <strong><i aria-hidden="true" />{t(`opsHealth.${group.severity}Signals`)}</strong>
                          <small>{t("opsHealth.incidentGroupCount").replace("{count}", String(group.total))}</small>
                        </header>
                        <div>
                          {group.items.map((incident) => (
                            <Link className="ops-health-v7-ledger__row" href={incident.href} key={incident.id}>
                              <span
                                className="ops-health-v7-ledger__number"
                                aria-label={t("opsHealth.affectedRecords").replace("{count}", String(incident.count))}
                              >
                                <strong>{incident.count}</strong>
                                <small>{t("opsHealth.incidentCount")}</small>
                              </span>
                              <span className="ops-health-v7-ledger__copy">
                                <span>
                                  <em>{incident.area}</em>
                                  {incident.id === topImpactIncident?.id ? <b>{t("opsHealth.highestImpact")}</b> : null}
                                </span>
                                <strong>{incident.title}</strong>
                                <small>{incident.detail}</small>
                              </span>
                              <span className="ops-health-v7-ledger__arrow" aria-hidden="true">↗</span>
                            </Link>
                          ))}
                        </div>
                      </section>
                    ))}
                    {incidents.length > visibleIncidents.length ? <Link className="ops-health-v3-incidents__more" href="/ops/jobs">+{incidents.length - visibleIncidents.length} more signals in specialist views</Link> : null}
                  </div>
                ) : (
                  <div className="ops-health-clear-state">
                    <span aria-hidden="true">✓</span>
                    <strong>{t("opsHealth.noActiveIncidents")}</strong>
                    <p>{t("opsHealth.noActiveIncidentsHelp")}</p>
                  </div>
                )}
              </section>
            </section>

            <section className="ops-health-panel ops-health-v2-risk-panel">
              <div className="ops-health-panel__head">
                <div>
                  <span className="ops-health-panel__eyebrow">Cross-record assurance</span>
                  <h2>Hidden risk ledger</h2>
                </div>
                <Link className="ops-health-panel__link" href="/ops">Open command center</Link>
              </div>
              <HiddenRiskLedger risks={homeSummary?.hidden_risks ?? []} />
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
                <div className="ops-health-v8-canvas ops-health-v8-workload">
                  <div className="ops-health-v8-headline-stats" aria-label={t("opsHealth.queueBacklog")}>
                    <span className={activeWorkload > 0 ? "is-attention" : "is-clear"}><small>{t("opsHealth.activeWorkload")}</small><strong>{activeWorkload}</strong><em>{activeWorkload > 0 ? t("opsHealth.queueNeedsAttention") : t("opsHealth.queueClearShort")}</em></span>
                    <span><small>{t("opsHealth.retriesShort")}</small><strong>{retryRisk ? trueRetryClaims : "—"}</strong></span>
                    <span><small>{t("opsHealth.avgProcessing")}</small><strong>{formatSeconds(avgProcessing)}</strong></span>
                  </div>

                  <section className="ops-health-v8-zone is-pipeline">
                    <header><h3>{t("opsHealth.pipelineVolume")}</h3><small>{t("opsHealth.completedVolumeHint")}</small></header>
                    <PipelineVolumeChart rows={jobMatrix.rows} emptyLabel={t("opsHealth.noJobMatrix")} completedLabel={t("opsHealth.completedShort")} />
                  </section>

                  <div className="ops-health-v8-workload__lower">
                    <section className="ops-health-v8-zone">
                      <header><h3>{t("opsHealth.outputComposition")}</h3></header>
                      <OutputCompositionChart
                        records={[
                          { key: "renders", record: metrics.render_counts_by_status },
                          { key: "drafts", record: metrics.publish_draft_counts_by_status },
                        ]}
                        labels={{ renders: t("opsHealth.renders"), drafts: t("opsHealth.publishDrafts") }}
                        emptyLabel="—"
                      />
                    </section>
                    <section className="ops-health-v8-zone">
                      <header><h3>{t("opsHealth.assetReuse")}</h3></header>
                      <AssetReusePlot assets={assetRows} emptyLabel={t("opsHealth.noAssetReuse")} labels={{ current: t("opsHealth.currentAssets"), historical: t("opsHealth.historicalAssets") }} />
                    </section>
                  </div>
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
                <div className="ops-health-v8-canvas ops-health-v8-signals">
                  <div className="ops-health-v8-signals__overview">
                    <section className="ops-health-v8-zone">
                      <header><h3>{t("opsHealth.riskBySeverity")}</h3></header>
                      <RiskSeverityRail entries={riskEntries} emptyLabel={t("opsHealth.noOpenRisk")} openLabel={t("opsHealth.openFlagsShort")} />
                    </section>
                    <section className="ops-health-v8-zone is-fetch-radar">
                      <header><h3>{t("opsHealth.fetchHealth")}</h3></header>
                      {fetchHealth ? (
                        <FetchSignalVisual fetchHealth={fetchHealth} labels={{ runs: t("opsHealth.fetchWindowRuns"), blocked: t("opsHealth.fetchBlocked"), failed: t("opsHealth.fetchFailed"), parse: t("opsHealth.fetchParseWarnings") }} />
                      ) : <p className="ops-health-empty">{t("opsHealth.fetchHealthUnavailable")}</p>}
                    </section>
                  </div>

                  {topBlocked.length > 0 ? (
                    <section className="ops-health-v8-zone">
                      <header><h3>{t("opsHealth.topBlockedReasons")}</h3></header>
                      <SignalPareto entries={topBlocked.map((item) => ({ key: item.reason, count: item.count }))} emptyLabel="—" />
                    </section>
                  ) : null}

                  {fetchAccounts.length > 1 ? (
                    <section className="ops-health-v8-zone is-account-visual">
                      <header><h3>{t("opsHealth.fetchByAccount")}</h3></header>
                      <FetchAccountList accounts={fetchAccounts} emptyLabel={t("opsHealth.noFetchAccounts")} />
                    </section>
                  ) : null}

                  {failureCategories.length > 0 ? (
                    <section className="ops-health-v8-zone">
                      <header><h3>{t("opsHealth.commonFailures")}</h3></header>
                      <SignalPareto entries={failureCategories.map((item) => ({ key: item.error_code, count: item.count }))} emptyLabel={t("opsHealth.noFailureCategories")} />
                    </section>
                  ) : null}

                  <FailureRateVisual entries={failureRates} clearLabel={t("opsHealth.failureRateClear")} />
                </div>
              </HealthPanel>
            </section>

            <HealthPanel
              title={t("opsHealth.publishingPulse")}
              action={
                <Link className="ops-health-panel__link" href="/ops/publish-health">
                  {t("opsHealth.openPublishHealth")}
                </Link>
              }
            >
              <PublishColumnChart
                days={publishDays}
                overview={publishOverview}
                emptyLabel={t("opsHealth.noPublishTrend")}
                generatedAt={publishHealth?.generated_at ?? null}
                labels={{
                  attempts: t("opsHealth.publishAttempts"),
                  succeeded: t("opsHealth.publishSucceeded"),
                  failed: t("opsHealth.publishFailed"),
                  reconciliation: t("opsHealth.publishReconciliation"),
                  blocked: t("opsHealth.draftsBlocked"),
                  successRate: t("opsHealth.publishSuccessRate"),
                  generated: t("opsHealth.publishGenerated"),
                }}
              />
            </HealthPanel>

            <div className="ops-health-v9-coverage" title={t("opsHealth.knownGaps")}>
              <strong>{t("opsHealth.coverage")}</strong>
              <div>
                {unobservedDependencies.length > 0 ? unobservedDependencies.map((row) => (
                  <span className="is-unobserved" key={row.key}><i aria-hidden="true" />{row.label}<small>{t("opsHealth.notObserved")}</small></span>
                )) : <span className="is-observed"><i aria-hidden="true">✓</i>{t("opsHealth.allDependenciesObserved")}</span>}
              </div>
            </div>
          </>
        ) : null}
      </main>
      </AsyncContentBoundary>
    </OpsConsoleShell>
  );
}
