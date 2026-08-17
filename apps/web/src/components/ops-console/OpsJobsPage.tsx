"use client";

import Link from "next/link";
import { Fragment, useEffect, useMemo, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { cancelJob, deleteJob, fetchJobs, fetchOperationalMetrics, resumeJob, retryJob } from "../../lib/api";
import { useT } from "../../lib/i18n";
import { useAsyncAction } from "../../lib/useAsyncAction";
import { useLatestRequest, type LatestRequestMode } from "../../lib/useLatestRequest";
import {
  OPERATOR_LIST_PAGE_SIZE_PRESETS,
  OPS_JOBS_PAGE_SIZE_STORAGE_KEY,
  readOperatorListPageSize,
  writeOperatorListPageSize,
} from "../../lib/operatorListPageSize";
import type { Job, JobStatus } from "../../types/jobs";
import type { OperationalMetrics } from "../../types/operations";
import { OpsConsoleShell } from "../app-shell/OpsConsoleShell";
import { TopbarRefreshButton } from "../app-shell/TopbarRefreshButton";
import { OpsState, statusTone, type OpsTone } from "./OpsShared";
import { AsyncButton } from "../shared/AsyncButton";
import { AsyncContentBoundary } from "../shared/AsyncContentBoundary";
import { OperatorListPagination } from "../shared/OperatorListPagination";
import { useNotice } from "../shared/NoticeCenter";

const JOBS_PAGE_SIZE_DEFAULT = 50;

function parsePositivePage(raw: string | null): number {
  const value = Number(raw);
  return Number.isInteger(value) && value > 0 ? value : 1;
}

function parsePageSize(raw: string | null): number | null {
  const value = Number(raw);
  return (OPERATOR_LIST_PAGE_SIZE_PRESETS as readonly number[]).includes(value) ? value : null;
}

type StatusFilter = "all" | "stale" | JobStatus;

function parseStatusFilter(raw: string): StatusFilter | null {
  const value = raw.trim();
  if (!value) return null;
  if (value.toLowerCase() === "stale") return "stale";
  const upper = value.toUpperCase();
  const allowed: JobStatus[] = [
    "QUEUED",
    "RUNNING",
    "WAITING_FOR_REVIEW",
    "RETRYABLE",
    "FAILED",
    "CANCELLED",
    "COMPLETED",
  ];
  return allowed.includes(upper as JobStatus) ? (upper as JobStatus) : null;
}

function formatJobTypeLabel(jobType: string): string {
  return jobType
    .split(/[_-]+/)
    .filter(Boolean)
    .map((part) => part.charAt(0) + part.slice(1).toLowerCase())
    .join(" ");
}

function formatJobWorkLabel(job: Job): string {
  if (job.workflow_action === "suggest_residual_translation") return "Residual Translation";
  if (job.workflow_action === "build_residual_proposal") return "Residual Proposal";
  if (job.workflow_action === "approve_residual_proposal") return "Residual Approval";
  if (job.workflow_action === "auto_residual_remediation") return "Residual Remediation";
  return formatJobTypeLabel(job.job_type);
}

function formatJobStepLabel(job: Job): string {
  if (
    job.workflow_action === "suggest_residual_translation"
    && job.current_step_key === "render_preview"
  ) {
    return "Translate residual OCR";
  }
  return job.current_step_key
    ? formatJobTypeLabel(job.current_step_key)
    : "";
}

export type OcrCheckpointOutcome = {
  reviewRequired: number;
  totalObjects: number;
};

function nonNegativeInteger(value: unknown): number {
  const parsed = typeof value === "number" ? value : typeof value === "string" ? Number(value) : 0;
  return Number.isFinite(parsed) ? Math.max(0, Math.round(parsed)) : 0;
}

/** A completed worker can legitimately hand off to a separate operator checkpoint. */
export function resolveOcrCheckpointOutcome(job: Job): OcrCheckpointOutcome | null {
  if (job.job_type !== "ANALYZE_OCR" || job.status !== "COMPLETED") return null;
  const output = job.steps.find((step) => step.step_key === "persist_outputs")?.output_json;
  if (!output || output.workflow_stage !== "WAITING_OCR_REVIEW") return null;
  const reviewRequired = nonNegativeInteger(output.review_required);
  if (reviewRequired <= 0) return null;
  return {
    reviewRequired,
    totalObjects: Math.max(
      reviewRequired,
      nonNegativeInteger(output.phase2_content_object_count)
    )
  };
}

function formatTableDateTime(value: string | null | undefined): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  const dd = String(date.getDate()).padStart(2, "0");
  const mm = String(date.getMonth() + 1).padStart(2, "0");
  const yy = String(date.getFullYear()).slice(-2);
  const hh = String(date.getHours()).padStart(2, "0");
  const min = String(date.getMinutes()).padStart(2, "0");
  return `${dd}/${mm}/${yy} ${hh}:${min}`;
}

/** Compact duration from finished_at − started_at; "—" when either side is missing. */
function formatJobDuration(startedAt: string | null | undefined, finishedAt: string | null | undefined): string {
  if (!startedAt || !finishedAt) return "—";
  const startMs = new Date(startedAt).getTime();
  const endMs = new Date(finishedAt).getTime();
  if (Number.isNaN(startMs) || Number.isNaN(endMs) || endMs < startMs) return "—";
  const totalSeconds = Math.floor((endMs - startMs) / 1000);
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;
  if (hours > 0) return `${hours}h ${minutes}m`;
  if (minutes > 0) return `${minutes}m ${seconds}s`;
  return `${seconds}s`;
}

function formatJobElapsed(startedAt: string | null | undefined): string {
  if (!startedAt) return "—";
  return formatJobDuration(startedAt, new Date().toISOString());
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

function formatMetricTime(value: string | null | undefined): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return `${String(date.getHours()).padStart(2, "0")}:${String(date.getMinutes()).padStart(2, "0")}`;
}

function metricStatusCount(metrics: OperationalMetrics | null, status: JobStatus): number {
  if (!metrics) return 0;
  return Object.values(metrics.job_counts_by_type_status).reduce(
    (total, statuses) => total + (Number(statuses[status]) || 0),
    0
  );
}

type JobActionIconKind = "retry" | "resume" | "cancel" | "delete";

function JobActionIcon({ kind }: { kind: JobActionIconKind }) {
  if (kind === "retry" || kind === "resume") {
    return (
      <svg className="ops-jobs-table__icon" viewBox="0 0 24 24" aria-hidden="true">
        <path
          d="M19.5 12a7.5 7.5 0 1 1-2.2-5.3"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.8"
          strokeLinecap="round"
        />
        <path
          d="M19.5 5v5h-5"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.8"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
    );
  }
  if (kind === "cancel") {
    return (
      <svg className="ops-jobs-table__icon" viewBox="0 0 24 24" aria-hidden="true">
        <circle cx="12" cy="12" r="8" fill="none" stroke="currentColor" strokeWidth="1.8" />
        <path d="m8.8 8.8 6.4 6.4m0-6.4-6.4 6.4" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
      </svg>
    );
  }
  return (
    <svg className="ops-jobs-table__icon" viewBox="0 0 24 24" aria-hidden="true">
      <path
        d="M5 7h14M9 7V5.8A1.8 1.8 0 0 1 10.8 4h2.4A1.8 1.8 0 0 1 15 5.8V7m-7.5 0 0.7 11.2A1.8 1.8 0 0 0 10 20h4a1.8 1.8 0 0 0 1.8-1.8L16.5 7"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function formatStatusLabel(status: string): string {
  return status
    .split(/[_-]+/)
    .filter(Boolean)
    .map((part) => part.charAt(0) + part.slice(1).toLowerCase())
    .join(" ");
}

function jobStatusChipClass(status: string, tone: OpsTone): string {
  const key = status.toLowerCase().replace(/_/g, "-");
  const classes = ["ops-jobs-table__status", `is-${key}`];
  if (tone === "warn" && status === "COMPLETED") classes.push("is-warn");
  return classes.join(" ");
}

function jobTypePillTone(jobType: string): "mint" | "slate" | "amber" | "sky" | "rose" {
  let hash = 0;
  for (let i = 0; i < jobType.length; i += 1) {
    hash = (hash + jobType.charCodeAt(i) * (i + 1)) % 5;
  }
  return (["mint", "slate", "amber", "sky", "rose"] as const)[hash];
}

function isStaleRunning(job: Job, staleJobIds: ReadonlySet<string>): boolean {
  return job.status === "RUNNING" && staleJobIds.has(job.id);
}

function videoSourceLabel(job: Job): { label: string; href: string | null } {
  if (job.source_video_id) {
    return {
      label: `Source ${job.source_video_id.slice(0, 8)}`,
      href: `/source-videos/${job.source_video_id}`,
    };
  }
  if (job.reference_type && job.reference_id) {
    return {
      label: `${formatJobTypeLabel(job.reference_type)} ${job.reference_id.slice(0, 8)}`,
      href: null,
    };
  }
  if (job.render_output_id) {
    return {
      label: `Output ${job.render_output_id.slice(0, 8)}`,
      href: null,
    };
  }
  return { label: "—", href: null };
}

type JobFlowIconKind =
  | "queued"
  | "running"
  | "review"
  | "completed"
  | "workers"
  | "locked"
  | "unclaimed"
  | "oldest";

function JobFlowIcon({ kind }: { kind: JobFlowIconKind }) {
  if (kind === "queued") {
    return <svg className="ops-jobs-v2-icon" viewBox="0 0 24 24" aria-hidden="true"><path d="M5 7h14M5 12h14M5 17h9" /></svg>;
  }
  if (kind === "running") {
    return <svg className="ops-jobs-v2-icon" viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="8.5" /><path d="m10 8.8 5 3.2-5 3.2Z" /></svg>;
  }
  if (kind === "review") {
    return <svg className="ops-jobs-v2-icon" viewBox="0 0 24 24" aria-hidden="true"><path d="M3.5 12s3.2-5.3 8.5-5.3 8.5 5.3 8.5 5.3-3.2 5.3-8.5 5.3S3.5 12 3.5 12Z" /><circle cx="12" cy="12" r="2.3" /></svg>;
  }
  if (kind === "completed") {
    return <svg className="ops-jobs-v2-icon" viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="8.5" /><path d="m8.2 12.2 2.5 2.5 5.4-5.6" /></svg>;
  }
  if (kind === "workers") {
    return <svg className="ops-jobs-v2-icon" viewBox="0 0 24 24" aria-hidden="true"><circle cx="9" cy="8.5" r="3" /><circle cx="16.5" cy="10" r="2.2" /><path d="M3.8 19c.5-3.2 2.2-5 5.2-5s4.7 1.8 5.2 5M14 14.8c3.3-.7 5.4.8 5.9 3.7" /></svg>;
  }
  if (kind === "locked") {
    return <svg className="ops-jobs-v2-icon" viewBox="0 0 24 24" aria-hidden="true"><rect x="5.5" y="10" width="13" height="10" rx="2" /><path d="M8.5 10V7.5a3.5 3.5 0 0 1 7 0V10" /></svg>;
  }
  if (kind === "unclaimed") {
    return <svg className="ops-jobs-v2-icon" viewBox="0 0 24 24" aria-hidden="true"><rect x="5.5" y="10" width="13" height="10" rx="2" /><path d="M15.5 10V7.5a3.5 3.5 0 0 0-6.8-1.2" /></svg>;
  }
  return <svg className="ops-jobs-v2-icon" viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="8.5" /><path d="M12 7.5V12l3 2" /></svg>;
}

function JobStateFlow({
  counts,
  staleCount,
  currentFilter,
  onFilter,
  meta,
  generatedAt,
  labels,
}: {
  counts: Record<JobStatus, number>;
  staleCount: number;
  currentFilter: StatusFilter;
  onFilter: (status: StatusFilter) => void;
  meta: { workers: number; locked: number; unclaimed: number; oldest: string };
  generatedAt: string | null;
  labels: Record<string, string>;
}) {
  const exceptionCount = counts.FAILED + counts.RETRYABLE + staleCount;
  const attention = exceptionCount + meta.unclaimed;
  const total = Object.values(counts).reduce((sum, count) => sum + count, 0);
  const active = counts.QUEUED + counts.RUNNING + counts.WAITING_FOR_REVIEW;
  const completionRate = total > 0 ? Math.round((counts.COMPLETED / total) * 100) : 0;
  const summary = exceptionCount > 0
    ? labels.exceptionSummary.replace("{count}", String(exceptionCount))
    : meta.unclaimed > 0
      ? labels.unclaimedSummary.replace("{count}", String(meta.unclaimed))
      : active > 0
        ? labels.activeSummary.replace("{active}", String(active)).replace("{running}", String(counts.RUNNING))
        : labels.clearSummary.replace("{completed}", String(counts.COMPLETED));
  const main: Array<{ key: JobStatus; label: string; icon: JobFlowIconKind }> = [
    { key: "QUEUED", label: labels.queued, icon: "queued" },
    { key: "RUNNING", label: labels.running, icon: "running" },
    { key: "WAITING_FOR_REVIEW", label: labels.review, icon: "review" },
    { key: "COMPLETED", label: labels.completed, icon: "completed" },
  ];
  const exceptions: Array<{ key: StatusFilter; label: string; value: number }> = [
    { key: "RETRYABLE", label: labels.retryable, value: counts.RETRYABLE },
    { key: "FAILED", label: labels.failed, value: counts.FAILED },
    { key: "stale", label: labels.stale, value: staleCount },
    { key: "CANCELLED", label: labels.cancelled, value: counts.CANCELLED },
  ];
  return (
    <section className={`ops-jobs-v2-command${attention > 0 ? " is-attention" : " is-clear"}`}>
      <header>
        <div className="ops-jobs-v2-command__headline">
          <span>{labels.eyebrow}</span>
          <h2>{labels.title}</h2>
          <p>{summary}</p>
        </div>
        <div className="ops-jobs-v2-command__status">
          <strong><i />{attention > 0 ? labels.attention : labels.clear}</strong>
          <time dateTime={generatedAt ?? undefined}>{labels.updatedAt.replace("{time}", formatMetricTime(generatedAt))}</time>
        </div>
      </header>
      <div className="ops-jobs-v2-flow">
        <div className="ops-jobs-v2-flow__overview" aria-label={`${labels.completionRate}: ${completionRate}%`}>
          <div
            className="ops-jobs-v2-flow__gauge"
            style={{ background: `conic-gradient(#46d6a1 0 ${completionRate}%, rgba(255, 255, 255, 0.09) ${completionRate}% 100%)` }}
          >
            <div><strong>{completionRate}%</strong><span>{labels.completionRate}</span></div>
          </div>
          <footer>
            <span><small>{labels.totalJobs}</small><strong>{total}</strong></span>
            <span><small>{labels.activeNow}</small><strong>{active}</strong></span>
          </footer>
        </div>
        <div className="ops-jobs-v2-flow__main">
          {main.map((item) => (
            <button type="button" className={`is-${item.key.toLowerCase().replace(/_/g, "-")}`} aria-pressed={currentFilter === item.key} key={item.key} onClick={() => onFilter(item.key)}>
              <i><JobFlowIcon kind={item.icon} /></i><strong>{counts[item.key]}</strong><span>{item.label}</span>
              <small>{Math.round(total > 0 ? (counts[item.key] / total) * 100 : 0)}% {labels.ofTotal}</small>
              <em aria-hidden="true"><b style={{ width: `${total > 0 ? (counts[item.key] / total) * 100 : 0}%` }} /></em>
            </button>
          ))}
        </div>
        <div className="ops-jobs-v2-flow__exceptions">
          {exceptions.map((item) => (
            <button type="button" className={`is-${String(item.key).toLowerCase()}`} aria-pressed={currentFilter === item.key} key={item.key} onClick={() => onFilter(item.key)}>
              <strong>{item.value}</strong><span>{item.label}</span>
            </button>
          ))}
        </div>
      </div>
      <footer>
        <span><JobFlowIcon kind="workers" /><em>{labels.workers}</em><b>{meta.workers}</b></span>
        <span><JobFlowIcon kind="locked" /><em>{labels.locked}</em><b>{meta.locked}</b></span>
        <span className={meta.unclaimed > 0 ? "is-danger" : ""}><JobFlowIcon kind="unclaimed" /><em>{labels.unclaimed}</em><b>{meta.unclaimed}</b></span>
        <span><JobFlowIcon kind="oldest" /><em>{labels.oldest}</em><b>{meta.oldest}</b></span>
      </footer>
    </section>
  );
}

function JobWorkloadChart({
  record,
  selectedType,
  onSelectType,
  emptyLabel,
  labels,
}: {
  record: Record<string, Record<string, number>>;
  selectedType: string;
  onSelectType: (jobType: string) => void;
  emptyLabel: string;
  labels: Record<string, string>;
}) {
  const statusOrder: JobStatus[] = [
    "QUEUED",
    "RUNNING",
    "WAITING_FOR_REVIEW",
    "RETRYABLE",
    "FAILED",
    "CANCELLED",
    "COMPLETED",
  ];
  const rows = Object.entries(record)
    .map(([jobType, statuses]) => ({ jobType, statuses, total: statusOrder.reduce((sum, status) => sum + (Number(statuses[status]) || 0), 0) }))
    .filter((row) => row.total > 0)
    .sort((left, right) => right.total - left.total || left.jobType.localeCompare(right.jobType))
    .slice(0, 8);
  if (rows.length === 0) return <p className="ops-jobs-v2-empty">{emptyLabel}</p>;
  const peak = Math.max(...rows.map((row) => row.total), 1);
  return (
    <div className="ops-jobs-v2-workload" role="group" aria-label={rows.map((row) => `${formatJobTypeLabel(row.jobType)} ${row.total}`).join(", ")}>
      {rows.map((row) => (
        <button type="button" aria-pressed={selectedType === row.jobType} key={row.jobType} onClick={() => onSelectType(row.jobType)}>
          <span title={row.jobType}>{formatJobTypeLabel(row.jobType)}</span>
          <i><b style={{ width: `${(row.total / peak) * 100}%` }}>{statusOrder.map((status) => {
            const value = Number(row.statuses[status]) || 0;
            return value > 0 ? <em className={`is-${status.toLowerCase().replace(/_/g, "-")}`} key={status} style={{ flexGrow: value, flexBasis: 0 }} /> : null;
          })}</b></i>
          <strong>{row.total}</strong>
        </button>
      ))}
      <footer>
        {statusOrder.map((status) => (
          <span key={status}>
            <i className={`is-${status.toLowerCase().replace(/_/g, "-")}`} />
            {labels[status]}
          </span>
        ))}
      </footer>
    </div>
  );
}

function JobExceptionPareto({
  entries,
  counts,
  labels,
}: {
  entries: Array<{ error_code: string; count: number }>;
  counts: { failed: number; retryable: number; stale: number };
  labels: Record<string, string>;
}) {
  const visible = entries.slice(0, 5);
  const peak = Math.max(...visible.map((entry) => entry.count), 1);
  return (
    <div className="ops-jobs-v2-exceptions">
      <div className="ops-jobs-v2-exceptions__summary">
        <span className="is-failed">{labels.failed}<b>{counts.failed}</b></span>
        <span className="is-retryable">{labels.retryable}<b>{counts.retryable}</b></span>
        <span className="is-stale">{labels.stale}<b>{counts.stale}</b></span>
      </div>
      {visible.length > 0 ? <div className="ops-jobs-v2-pareto">{visible.map((entry) => (
        <div key={entry.error_code}><code>{entry.error_code}</code><i><b style={{ width: `${(entry.count / peak) * 100}%` }} /></i><strong>{entry.count}</strong></div>
      ))}</div> : <p className="ops-jobs-v2-empty is-clear">{labels.noFailures}</p>}
    </div>
  );
}

function JobStepTrace({ job, labels }: { job: Job; labels: Record<string, string> }) {
  const steps = [...job.steps].sort((left, right) => left.step_order - right.step_order);
  return (
    <div className="ops-jobs-v2-trace">
      <header><strong>{labels.trace}</strong><span>{formatJobWorkLabel(job)} · #{job.id.slice(0, 8)}</span></header>
      {steps.length > 0 ? <div>{steps.map((step, index) => (
        <section className={`is-${step.status.toLowerCase().replace(/_/g, "-")}`} key={step.id}>
          <i>{String(index + 1).padStart(2, "0")}</i>
          <span><strong>{step.step_name}</strong><small>{formatStatusLabel(step.status)} · {step.progress_percent}% · {labels.attempt} {step.attempts}</small></span>
          {step.error_code ? <code title={step.error_message ?? step.error_code}>{step.error_code}</code> : null}
        </section>
      ))}</div> : <p>{labels.noSteps}</p>}
    </div>
  );
}

export function OpsJobsPage() {
  const t = useT();
  const pathname = usePathname();
  const router = useRouter();
  const searchParams = useSearchParams();
  const focusJobId = (searchParams.get("job_id") ?? "").trim() || null;
  const statusFromUrl = parseStatusFilter(searchParams.get("status") ?? "");
  const [pageSize, setPageSize] = useState(() =>
    parsePageSize(searchParams.get("per_page"))
      ?? readOperatorListPageSize(OPS_JOBS_PAGE_SIZE_STORAGE_KEY, OPERATOR_LIST_PAGE_SIZE_PRESETS, JOBS_PAGE_SIZE_DEFAULT)
  );
  const [currentPage, setCurrentPage] = useState(() => parsePositivePage(searchParams.get("page")));
  const [jobs, setJobs] = useState<Job[]>([]);
  const [totalCount, setTotalCount] = useState(0);
  const [metrics, setMetrics] = useState<OperationalMetrics | null>(null);
  const [inlineError, setInlineError] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState<StatusFilter>(() => statusFromUrl ?? "all");
  const [jobTypeFilter, setJobTypeFilter] = useState("all");
  const [searchQuery, setSearchQuery] = useState("");
  const [queryForApi, setQueryForApi] = useState("");
  const [copiedJobId, setCopiedJobId] = useState<string | null>(null);
  const [expandedJobId, setExpandedJobId] = useState<string | null>(null);
  const action = useAsyncAction();
  const request = useLatestRequest();
  const { notify } = useNotice();

  async function load(mode: LatestRequestMode = jobs.length || metrics ? "refresh" : "initial") {
    setInlineError(null);
    const requestedStatus = statusFilter === "all" ? undefined : statusFilter === "stale" ? "RUNNING" : statusFilter;
    const requestedType = jobTypeFilter === "all" ? undefined : jobTypeFilter;
    await request.run(
      async () => Promise.all([
        fetchJobs(requestedStatus, {
          limit: pageSize,
          offset: (currentPage - 1) * pageSize,
          jobType: requestedType,
          query: queryForApi || undefined,
        }),
        fetchOperationalMetrics(),
      ]),
      ([jobPayload, metricsPayload]) => {
        setJobs(jobPayload.jobs);
        setTotalCount(jobPayload.total_count);
        setMetrics(metricsPayload);
      },
      mode
    ).catch(() => undefined);
  }

  function handlePageSizeChange(nextPageSize: number) {
    if (nextPageSize === pageSize) return;
    writeOperatorListPageSize(OPS_JOBS_PAGE_SIZE_STORAGE_KEY, nextPageSize, OPERATOR_LIST_PAGE_SIZE_PRESETS);
    setPageSize(nextPageSize);
    setCurrentPage(1);
  }

  function handlePageChange(nextPage: number) {
    if (nextPage === currentPage || nextPage < 1) return;
    setExpandedJobId(null);
    setCurrentPage(nextPage);
    window.requestAnimationFrame(() => {
      document.querySelector(".ops-jobs-sheet")?.scrollIntoView({ behavior: "smooth", block: "start" });
    });
  }

  function toggleStatusFilter(next: StatusFilter) {
    setCurrentPage(1);
    setStatusFilter((current) => (current === next ? "all" : next));
  }

  function clearFilters() {
    setCurrentPage(1);
    setStatusFilter("all");
    setJobTypeFilter("all");
    setSearchQuery("");
  }

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setCurrentPage(1);
      setQueryForApi(searchQuery.trim());
    }, 250);
    return () => window.clearTimeout(timer);
  }, [searchQuery]);

  useEffect(() => {
    void load(jobs.length || metrics ? "refresh" : "initial");
  }, [t, statusFilter, jobTypeFilter, queryForApi, currentPage, pageSize]);

  useEffect(() => {
    const currentQuery = searchParams.toString();
    const params = new URLSearchParams(currentQuery);
    if (currentPage > 1) params.set("page", String(currentPage));
    else params.delete("page");
    params.set("per_page", String(pageSize));
    const nextQuery = params.toString();
    if (nextQuery !== currentQuery) router.replace(`${pathname}?${nextQuery}`, { scroll: false });
  }, [currentPage, pageSize, pathname, router, searchParams]);

  useEffect(() => {
    if (totalCount <= 0) return;
    const lastPage = Math.max(1, Math.ceil(totalCount / pageSize));
    if (currentPage > lastPage) setCurrentPage(lastPage);
  }, [currentPage, pageSize, totalCount]);

  useEffect(() => {
    if (!statusFromUrl) return;
    setStatusFilter(statusFromUrl);
  }, [statusFromUrl]);

  useEffect(() => {
    if (!focusJobId || request.initialLoading) return;
    const row = document.getElementById(`ops-job-row-${focusJobId}`);
    row?.scrollIntoView({ block: "center", behavior: "smooth" });
  }, [focusJobId, request.initialLoading, jobs]);

  const focusedJob = useMemo(
    () => (focusJobId ? jobs.find((job) => job.id === focusJobId) ?? null : null),
    [focusJobId, jobs]
  );

  const jobTypeOptions = useMemo(() => {
    const types = Array.from(
      new Set([
        ...Object.keys(metrics?.job_counts_by_type_status ?? {}),
        ...jobs.map((job) => job.job_type),
      ])
    ).sort();
    return types;
  }, [jobs, metrics]);

  async function handleDelete(job: Job) {
    const confirmed = window.confirm(
      t("opsJobs.deleteConfirm")
        .replace("{jobId}", job.id.slice(0, 8))
        .replace("{jobType}", job.job_type)
        .replace("{status}", job.status)
    );
    if (!confirmed) return;

    await action.run(`delete-${job.id}`, async () => {
      setInlineError(null);
      try {
        await deleteJob(job.id);
        // Remove immediately, then reload the canonical list and metrics from
        // the API.  A page refresh must never make a "deleted" job reappear.
        setJobs((current) => current.filter((item) => item.id !== job.id));
        setTotalCount((current) => Math.max(0, current - 1));
        await load("refresh");
        notify({
          message: t("opsJobs.deleteSuccess").replace("{jobId}", job.id.slice(0, 8)),
          tone: "success",
        });
      } catch (err) {
        const message = err instanceof Error ? err.message : t("opsJobs.deleteFailed");
        setInlineError(message);
        notify({ message, tone: "error" });
      }
    });
  }

  async function handleRetry(job: Job) {
    await action.run(`retry-${job.id}`, async () => {
      setInlineError(null);
      try {
        const updated = await retryJob(job.id);
        setJobs((current) => current.map((item) => (item.id === job.id ? updated : item)));
        notify({ message: `${t("opsJobs.retry")}: #${job.id.slice(0, 8)}`, tone: "success" });
      } catch (err) {
        const message = err instanceof Error ? err.message : t("opsJobs.retryFailed");
        setInlineError(message);
        notify({ message, tone: "error" });
      }
    });
  }

  async function handleCancel(job: Job) {
    const confirmed = window.confirm(t("opsJobs.cancelConfirm").replace("{jobId}", job.id.slice(0, 8)));
    if (!confirmed) return;
    await action.run(`cancel-${job.id}`, async () => {
      setInlineError(null);
      try {
        const updated = await cancelJob(job.id);
        setJobs((current) => current.map((item) => (item.id === job.id ? updated : item)));
        notify({ message: `${t("opsJobs.cancel")}: #${job.id.slice(0, 8)}`, tone: "success" });
      } catch (err) {
        const message = err instanceof Error ? err.message : t("opsJobs.cancelFailed");
        setInlineError(message);
        notify({ message, tone: "error" });
      }
    });
  }

  async function handleResume(job: Job) {
    await action.run(`resume-${job.id}`, async () => {
      setInlineError(null);
      try {
        const updated = await resumeJob(job.id);
        setJobs((current) => current.map((item) => (item.id === job.id ? updated : item)));
        notify({ message: `${t("opsJobs.resume")}: #${job.id.slice(0, 8)}`, tone: "success" });
      } catch (err) {
        const message = err instanceof Error ? err.message : t("opsJobs.resumeFailed");
        setInlineError(message);
        notify({ message, tone: "error" });
      }
    });
  }

  async function handleCopyId(jobId: string) {
    await action.run(`copy-${jobId}`, async () => {
      setInlineError(null);
      try {
        await navigator.clipboard.writeText(jobId);
        setCopiedJobId(jobId);
        notify({ message: t("opsJobs.copied"), tone: "success" });
        window.setTimeout(() => setCopiedJobId((current) => (current === jobId ? null : current)), 1200);
      } catch {
        const message = t("opsJobs.copyFailed");
        setInlineError(message);
        notify({ message, tone: "error" });
      }
    });
  }

  const staleJobIds = useMemo(
    () => new Set(metrics?.queue_backlog.stale_running_job_ids ?? []),
    [metrics]
  );
  const staleRunning = useMemo(
    () => jobs.filter((job) => isStaleRunning(job, staleJobIds)),
    [jobs, staleJobIds]
  );

  const visibleJobs = useMemo(
    () => jobs.filter((job) => (statusFilter === "stale" ? isStaleRunning(job, staleJobIds) : true)),
    [jobs, staleJobIds, statusFilter]
  );

  const failureCategories = metrics?.common_failure_categories ?? [];
  const countFor = (status: JobStatus) =>
    metrics ? metricStatusCount(metrics, status) : jobs.filter((job) => job.status === status).length;
  const stateCounts: Record<JobStatus, number> = {
    QUEUED: countFor("QUEUED"),
    RUNNING: countFor("RUNNING"),
    WAITING_FOR_REVIEW: countFor("WAITING_FOR_REVIEW"),
    RETRYABLE: countFor("RETRYABLE"),
    FAILED: countFor("FAILED"),
    CANCELLED: countFor("CANCELLED"),
    COMPLETED: countFor("COMPLETED"),
  };
  const staleCount = metrics?.queue_backlog.stale_running ?? staleRunning.length;
  const runningJobs = jobs.filter((job) => job.status === "RUNNING");
  const workerCount = metrics?.queue_backlog.active_worker_count
    ?? new Set(runningJobs.map((job) => job.locked_by).filter(Boolean)).size;
  const lockedCount = metrics?.queue_backlog.running_with_lock
    ?? runningJobs.filter((job) => Boolean(job.locked_by)).length;
  const unclaimedCount = metrics?.queue_backlog.running_without_lock
    ?? runningJobs.filter((job) => !job.locked_by).length;
  const oldestQueuedAge = formatAge(metrics?.queue_backlog.oldest_queued_at);
  const filterActive = statusFilter !== "all" || jobTypeFilter !== "all" || searchQuery.trim().length > 0;
  const shownCount = filterActive ? visibleJobs.length : jobs.length;

  const refreshAction = (
    <TopbarRefreshButton busy={request.refreshing} disabled={request.initialLoading} onClick={() => void load("refresh")} />
  );
  const hasData = jobs.length > 0 || Boolean(metrics);
  const boundaryStatus = request.initialLoading && !hasData ? "loading" : request.error && !hasData ? "error" : "success";
  const visibleError = inlineError ?? (hasData ? request.error?.message ?? null : null);

  return (
    <OpsConsoleShell actions={refreshAction} description={t("opsJobs.description")} title={t("opsJobs.title")}>
      <AsyncContentBoundary
        refreshing={request.refreshing}
        status={boundaryStatus}
        skeletonVariant="table"
        loadingLabel={t("opsJobs.loadingDetail")}
        errorState={<OpsState title={t("opsJobs.unavailableTitle")} detail={request.error?.message ?? t("opsJobs.unavailableTitle")} retry={() => void load("initial")} />}
      >
      <main className="ops-page ops-jobs-monitor is-compact">
        {visibleError ? <div className="inline-error">{visibleError}</div> : null}

        <JobStateFlow
          counts={stateCounts}
          staleCount={staleCount}
          currentFilter={statusFilter}
          onFilter={toggleStatusFilter}
          meta={{ workers: workerCount, locked: lockedCount, unclaimed: unclaimedCount, oldest: oldestQueuedAge }}
          generatedAt={metrics?.generated_at ?? null}
          labels={{
            eyebrow: t("opsJobs.executionState"),
            title: t("opsJobs.jobControlRoom"),
            attention: t("opsJobs.attentionRequired"),
            clear: t("opsJobs.queueClear"),
            queued: t("opsJobs.statusQueued"),
            running: t("opsJobs.running"),
            review: t("opsJobs.statusWaitingReview"),
            completed: t("opsJobs.statusCompleted"),
            retryable: t("opsJobs.retryable"),
            failed: t("opsJobs.failed"),
            stale: t("opsJobs.staleShort"),
            cancelled: t("opsJobs.statusCancelled"),
            completionRate: t("opsJobs.completionRate"),
            totalJobs: t("opsJobs.totalJobs"),
            activeNow: t("opsJobs.activeNow"),
            ofTotal: t("opsJobs.ofTotal"),
            clearSummary: t("opsJobs.clearSummary"),
            activeSummary: t("opsJobs.activeSummary"),
            exceptionSummary: t("opsJobs.exceptionSummary"),
            unclaimedSummary: t("opsJobs.unclaimedSummary"),
            updatedAt: t("opsJobs.updatedAt"),
            workers: t("opsJobs.workers"),
            locked: t("opsJobs.locked"),
            unclaimed: t("opsJobs.unclaimed"),
            oldest: t("opsJobs.oldestWait"),
          }}
        />

        <section className="ops-jobs-controls">
          <label className="ops-jobs-controls__search">
            <span className="visually-hidden">{t("opsJobs.searchLabel")}</span>
            <input
              type="search"
              value={searchQuery}
              placeholder={t("opsJobs.searchPlaceholder")}
              onChange={(event) => setSearchQuery(event.target.value)}
            />
          </label>

          <label className="ops-jobs-controls__status">
            <span className="visually-hidden">{t("opsJobs.status")}</span>
            <select
              value={statusFilter}
              onChange={(event) => {
                setCurrentPage(1);
                setStatusFilter(event.target.value as StatusFilter);
              }}
            >
              <option value="all">{t("opsJobs.statusAll")}</option>
              <option value="RUNNING">{t("opsJobs.running")}</option>
              <option value="WAITING_FOR_REVIEW">{t("opsJobs.statusWaitingReview")}</option>
              <option value="COMPLETED">{t("opsJobs.statusCompleted")}</option>
              <option value="FAILED">{t("opsJobs.failed")}</option>
              <option value="RETRYABLE">{t("opsJobs.retryable")}</option>
              <option value="QUEUED">{t("opsJobs.statusQueued")}</option>
              <option value="CANCELLED">{t("opsJobs.statusCancelled")}</option>
              <option value="stale">{t("opsJobs.staleShort")}</option>
            </select>
          </label>

          <label className="ops-jobs-controls__type">
            <span className="visually-hidden">{t("opsJobs.jobType")}</span>
            <select value={jobTypeFilter} onChange={(event) => {
              setCurrentPage(1);
              setJobTypeFilter(event.target.value);
            }}>
              <option value="all">{t("opsJobs.jobTypeAll")}</option>
              {jobTypeOptions.map((type) => (
                <option key={type} value={type}>
                  {formatJobTypeLabel(type)}
                </option>
              ))}
            </select>
          </label>

          <button type="button" className="ops-jobs-controls__view-all" onClick={clearFilters} disabled={!filterActive}>
            {t("opsJobs.viewAll")}
          </button>
        </section>

        <section className="ops-jobs-v2-visuals">
          <article className="ops-jobs-v2-panel">
            <header>
              <div>
                <span>{t("opsJobs.workloadEyebrow")}</span>
                <h2>{t("opsJobs.workloadByType")}</h2>
              </div>
              <p>{t("opsJobs.workloadHint")}</p>
            </header>
            <JobWorkloadChart
              record={metrics?.job_counts_by_type_status ?? {}}
              selectedType={jobTypeFilter}
              onSelectType={(jobType) => {
                setCurrentPage(1);
                setJobTypeFilter((current) => current === jobType ? "all" : jobType);
              }}
              emptyLabel={t("opsJobs.noWorkloadData")}
              labels={{
                QUEUED: t("opsJobs.statusQueued"),
                RUNNING: t("opsJobs.running"),
                WAITING_FOR_REVIEW: t("opsJobs.statusWaitingReview"),
                RETRYABLE: t("opsJobs.retryable"),
                FAILED: t("opsJobs.failed"),
                CANCELLED: t("opsJobs.statusCancelled"),
                COMPLETED: t("opsJobs.statusCompleted"),
              }}
            />
          </article>
          <article className="ops-jobs-v2-panel is-exceptions">
            <header>
              <div>
                <span>{t("opsJobs.healthEyebrow")}</span>
                <h2>{t("opsJobs.exceptionRadar")}</h2>
              </div>
              <p>{t("opsJobs.exceptionHint")}</p>
            </header>
            <JobExceptionPareto
              entries={failureCategories}
              counts={{ failed: stateCounts.FAILED, retryable: stateCounts.RETRYABLE, stale: staleCount }}
              labels={{
                failed: t("opsJobs.failed"),
                retryable: t("opsJobs.retryable"),
                stale: t("opsJobs.staleShort"),
                noFailures: t("opsJobs.noFailureCategories"),
              }}
            />
          </article>
        </section>

        {focusJobId ? (
          <div className={`ops-jobs-alert ${focusedJob ? "is-good" : "is-warn"}`} role="status">
            {focusedJob
              ? t("opsJobs.focusFound")
                  .replace("{jobId}", focusedJob.id.slice(0, 8))
                  .replace("{jobType}", focusedJob.job_type)
                  .replace("{status}", focusedJob.status)
              : t("opsJobs.focusMissing")
                  .replace("{jobId}", focusJobId.slice(0, 8))
                  .replace("{count}", String(jobs.length))}
          </div>
        ) : null}

        {jobs.length === 0 ? (
          <p className="ops-jobs-empty">{t("opsJobs.noJobsFound")}</p>
        ) : visibleJobs.length === 0 ? (
          <p className="ops-jobs-empty">{t("opsJobs.noFilterMatches")}</p>
        ) : (
          <section className="ops-jobs-sheet">
            <div className="ops-jobs-sheet__bar">
              <p className="ops-jobs-sheet__meta">
                {t("opsJobs.showingOf")
                  .replace("{shown}", String(shownCount))
                  .replace("{total}", String(totalCount))}
              </p>
            </div>
            <div className="ops-jobs-table-wrap is-sheet">
              <table className="ops-jobs-table is-sheet">
                <thead>
                  <tr>
                    <th>{t("opsJobs.jobAndSource")}</th>
                    <th>{t("opsJobs.work")}</th>
                    <th>{t("opsJobs.execution")}</th>
                    <th>{t("opsJobs.health")}</th>
                    <th>{t("opsJobs.timing")}</th>
                    <th>{t("opsJobs.actions")}</th>
                  </tr>
                </thead>
                <tbody>
                  {visibleJobs.map((job) => {
                    const ocrCheckpoint = resolveOcrCheckpointOutcome(job);
                    const tone =
                      job.status === "COMPLETED" && job.error_message ? "warn" : statusTone(job.status);
                    const typeTone = jobTypePillTone(job.job_type);
                    const source = videoSourceLabel(job);
                    const liveStep = formatJobStepLabel(job);
                    const progress = Math.max(
                      0,
                      Math.min(
                        100,
                        job.status === "COMPLETED"
                          ? 100
                          : job.status === "CANCELLED"
                            ? 0
                            : Number(job.progress_percent) || 0
                      )
                    );
                    const canRetry =
                      job.retryable &&
                      (job.status === "FAILED" || job.status === "RETRYABLE") &&
                      (job.status === "FAILED" || job.attempts < job.max_attempts);
                    const canCancel = job.status !== "COMPLETED" && job.status !== "CANCELLED";
                    const canResume = job.status === "WAITING_FOR_REVIEW";
                    return (
                      <Fragment key={job.id}>
                        <tr
                          className={`tone-${tone}${job.id === focusJobId ? " is-focused" : ""}${expandedJobId === job.id ? " is-expanded" : ""}`}
                          id={`ops-job-row-${job.id}`}
                        >
                          <td>
                            <div className="ops-jobs-table__id">
                              <button
                                type="button"
                                className="ops-jobs-table__expand"
                                aria-expanded={expandedJobId === job.id}
                                aria-controls={`ops-job-trace-${job.id}`}
                                title={t("opsJobs.stepTrace")}
                                onClick={() => setExpandedJobId((current) => current === job.id ? null : job.id)}
                              >
                                <strong title={job.id}>#{job.id.slice(0, 8)}</strong>
                                <span aria-hidden="true">⌄</span>
                              </button>
                              <AsyncButton
                                type="button"
                                className="ops-jobs-table__copy"
                                aria-label={t("opsJobs.copyId")}
                                title={copiedJobId === job.id ? t("opsJobs.copied") : t("opsJobs.copyId")}
                                pending={action.isPending(`copy-${job.id}`)}
                                pendingLabel="…"
                                onClick={() => void handleCopyId(job.id)}
                              >
                                {copiedJobId === job.id ? "✓" : "⧉"}
                              </AsyncButton>
                            </div>
                            <div className="ops-jobs-table__source-line">
                          {source.href ? (
                            <Link className="ops-jobs-table__source" href={source.href}>
                              {source.label}
                            </Link>
                          ) : (
                            <span className={`ops-jobs-table__source${source.label === "—" ? " is-empty" : ""}`}>
                              {source.label}
                            </span>
                          )}
                            </div>
                          </td>
                          <td>
                            <span className={`ops-jobs-table__type tone-${typeTone}`} title={job.job_type}>
                              {formatJobWorkLabel(job)}
                            </span>
                            <span
                              className={`ops-jobs-table__step${ocrCheckpoint ? " is-attention" : ""}`}
                              title={job.current_step_key ?? undefined}
                            >
                              {ocrCheckpoint
                                ? t("opsJobs.ocrAnalysisReviewPending")
                                    .replace("{count}", String(ocrCheckpoint.reviewRequired))
                                    .replace("{total}", String(ocrCheckpoint.totalObjects))
                                : liveStep || t("opsJobs.noCurrentStep")}
                            </span>
                          </td>
                          <td>
                            <div className="ops-jobs-table__progress" aria-label={`${progress}%`}>
                              <div className="ops-jobs-table__bar">
                                <span style={{ width: `${progress}%` }} />
                              </div>
                              <em>{progress}%</em>
                            </div>
                            <span className="ops-jobs-table__attempts">
                              {t("opsJobs.attemptShort")} {job.attempts}/{job.max_attempts}
                              <i aria-hidden="true">·</i>
                              {job.completed_steps}/{job.total_steps} {t("opsJobs.stepsShort")}
                            </span>
                          </td>
                          <td className="ops-jobs-table__status-cell">
                            <span className={jobStatusChipClass(job.status, tone)}>
                              <i className="ops-jobs-table__status-dot" aria-hidden="true" />
                              {formatStatusLabel(job.status)}
                            </span>
                            {ocrCheckpoint ? (
                              <span className="ops-jobs-table__checkpoint-badge">
                                {t("opsJobs.ocrReviewBadge")
                                  .replace("{count}", String(ocrCheckpoint.reviewRequired))
                                  .replace("{total}", String(ocrCheckpoint.totalObjects))}
                              </span>
                            ) : null}
                            {job.error_code ? (
                              <code className="ops-jobs-table__error" title={job.error_message ?? job.error_code}>
                                {job.error_code}
                              </code>
                            ) : null}
                            {job.status === "RUNNING" ? (
                              <span className={`ops-jobs-table__heartbeat${isStaleRunning(job, staleJobIds) ? " is-stale" : ""}`}>
                                {job.locked_by ? `${job.locked_by} · ${formatAge(job.locked_at)}` : t("opsJobs.noWorkerLock")}
                              </span>
                            ) : null}
                          </td>
                          <td>
                            <dl className="ops-jobs-table__timing">
                              <div>
                                <dt>{t("opsJobs.startedAt")}</dt>
                                <dd>{job.started_at ? <time dateTime={job.started_at} title={job.started_at}>{formatTableDateTime(job.started_at)}</time> : "—"}</dd>
                              </div>
                              <div>
                                <dt>{t("opsJobs.finishedAt")}</dt>
                                <dd>{job.finished_at ? <time dateTime={job.finished_at} title={job.finished_at}>{formatTableDateTime(job.finished_at)}</time> : "—"}</dd>
                              </div>
                              <div>
                                <dt>{t("opsJobs.duration")}</dt>
                                <dd>{job.status === "RUNNING" ? formatJobElapsed(job.started_at) : formatJobDuration(job.started_at, job.finished_at)}</dd>
                              </div>
                            </dl>
                          </td>
                          <td>
                            <div className="ops-jobs-table__actions">
                              {canRetry ? (
                                <AsyncButton type="button" className="ops-jobs-table__retry is-icon" aria-label={t("opsJobs.retry")} title={t("opsJobs.retry")} pending={action.isPending(`retry-${job.id}`)} pendingLabel="…" onClick={() => void handleRetry(job)}>
                                  <JobActionIcon kind="retry" />
                                </AsyncButton>
                              ) : null}
                              {canResume ? (
                                <AsyncButton type="button" className="ops-jobs-table__resume is-icon" aria-label={t("opsJobs.resume")} title={t("opsJobs.resume")} pending={action.isPending(`resume-${job.id}`)} pendingLabel="…" onClick={() => void handleResume(job)}>
                                  <JobActionIcon kind="resume" />
                                </AsyncButton>
                              ) : null}
                              {canCancel ? (
                                <AsyncButton type="button" className="ops-jobs-table__cancel is-icon" aria-label={t("opsJobs.cancel")} title={t("opsJobs.cancel")} pending={action.isPending(`cancel-${job.id}`)} pendingLabel="…" onClick={() => void handleCancel(job)}>
                                  <JobActionIcon kind="cancel" />
                                </AsyncButton>
                              ) : null}
                              <AsyncButton className="ops-jobs-delete is-icon" data-testid={`delete-job-${job.id}`} type="button" aria-label={t("common.delete")} title={t("common.delete")} pending={action.isPending(`delete-${job.id}`)} pendingLabel="…" onClick={() => void handleDelete(job)}>
                                <JobActionIcon kind="delete" />
                              </AsyncButton>
                            </div>
                          </td>
                        </tr>
                        {expandedJobId === job.id ? (
                          <tr className="ops-jobs-v2-trace-row" id={`ops-job-trace-${job.id}`}>
                            <td colSpan={6}>
                              <JobStepTrace
                                job={job}
                                labels={{
                                  trace: t("opsJobs.stepTrace"),
                                  attempt: t("opsJobs.attemptShort"),
                                  noSteps: t("opsJobs.noSteps"),
                                }}
                              />
                            </td>
                          </tr>
                        ) : null}
                      </Fragment>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </section>
        )}

        {totalCount > 0 && jobs.length > 0 ? (
          <OperatorListPagination
            busy={request.refreshing}
            currentPage={currentPage}
            labels={{
              pagination: t("opsJobs.pagination"),
              perPage: t("opsJobs.perPage"),
              previous: t("opsJobs.previousPage"),
              next: t("opsJobs.nextPage"),
              page: t("opsJobs.page"),
              noun: t("opsJobs.jobsNoun"),
            }}
            onPageChange={handlePageChange}
            onPageSizeChange={handlePageSizeChange}
            pageSize={pageSize}
            pageSizeOptions={OPERATOR_LIST_PAGE_SIZE_PRESETS}
            totalCount={totalCount}
          />
        ) : null}
      </main>
      </AsyncContentBoundary>
    </OpsConsoleShell>
  );
}
