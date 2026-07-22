"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import { deleteJob, fetchJobs, fetchOperationalMetrics, retryJob } from "../../lib/api";
import { useT } from "../../lib/i18n";
import { hasMoreOffsetItems, mergeOffsetItemsById } from "../../lib/offsetListPagination";
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
import { OffsetLoadMoreFooter } from "../shared/OffsetLoadMoreFooter";
import { AsyncButton } from "../shared/AsyncButton";
import { AsyncContentBoundary } from "../shared/AsyncContentBoundary";
import { useNotice } from "../shared/NoticeCenter";

const STALE_RUNNING_MINUTES = 60;
const JOBS_PAGE_SIZE_DEFAULT = 50;

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

type JobActionIconKind = "retry" | "delete";

function JobActionIcon({ kind }: { kind: JobActionIconKind }) {
  if (kind === "retry") {
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

function isStaleRunning(job: Job): boolean {
  if (job.status !== "RUNNING") return false;
  const started = new Date(job.started_at ?? job.updated_at);
  if (Number.isNaN(started.getTime())) return false;
  return Date.now() - started.getTime() > STALE_RUNNING_MINUTES * 60 * 1000;
}

function jobMatchesSearch(job: Job, query: string): boolean {
  const q = query.trim().toLowerCase();
  if (!q) return true;
  return (
    job.id.toLowerCase().includes(q) ||
    job.job_type.toLowerCase().includes(q) ||
    formatJobTypeLabel(job.job_type).toLowerCase().includes(q) ||
    (job.source_video_id ?? "").toLowerCase().includes(q) ||
    (job.current_step_key ?? "").toLowerCase().includes(q) ||
    (job.error_code ?? "").toLowerCase().includes(q) ||
    (job.error_message ?? "").toLowerCase().includes(q)
  );
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

type KpiKind = "running" | "failed" | "retryable" | "stale" | "backlog" | "retries";

function KpiIcon({ kind }: { kind: KpiKind }) {
  if (kind === "running") {
    return (
      <svg className="ops-jobs-kpi__icon" viewBox="0 0 24 24" aria-hidden="true">
        <circle cx="12" cy="12" r="9" fill="none" stroke="currentColor" strokeWidth="1.8" />
        <circle cx="12" cy="7" r="1.4" fill="currentColor" />
        <circle cx="16.2" cy="14.5" r="1.4" fill="currentColor" />
        <circle cx="7.8" cy="14.5" r="1.4" fill="currentColor" />
      </svg>
    );
  }
  if (kind === "failed") {
    return (
      <svg className="ops-jobs-kpi__icon" viewBox="0 0 24 24" aria-hidden="true">
        <path
          d="M12 3.5 21 20H3L12 3.5Z"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.8"
          strokeLinejoin="round"
        />
        <path d="M12 10v5" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
        <circle cx="12" cy="17.5" r="1" fill="currentColor" />
      </svg>
    );
  }
  if (kind === "retryable") {
    return (
      <svg className="ops-jobs-kpi__icon" viewBox="0 0 24 24" aria-hidden="true">
        <path
          d="M19.5 12a7.5 7.5 0 1 1-2.2-5.3"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.8"
          strokeLinecap="round"
        />
        <path d="M19.5 5v5h-5" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    );
  }
  if (kind === "backlog") {
    return (
      <svg className="ops-jobs-kpi__icon" viewBox="0 0 24 24" aria-hidden="true">
        <path d="M4 7h16M4 12h16M4 17h10" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
      </svg>
    );
  }
  if (kind === "retries") {
    return (
      <svg className="ops-jobs-kpi__icon" viewBox="0 0 24 24" aria-hidden="true">
        <path
          d="M7 8h7a4 4 0 0 1 0 8H9"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.8"
          strokeLinecap="round"
        />
        <path d="M10 5 7 8l3 3" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    );
  }
  return (
    <svg className="ops-jobs-kpi__icon" viewBox="0 0 24 24" aria-hidden="true">
      <circle cx="12" cy="12" r="8" fill="none" stroke="currentColor" strokeWidth="1.8" />
      <path d="M12 7.5V12l3 2" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function KpiTile({
  kind,
  label,
  value,
  detail,
  sharePercent,
  trend = "up",
  tone = "muted",
  active = false,
  onClick,
}: {
  kind: KpiKind;
  label: string;
  value: string;
  detail: string;
  sharePercent: number;
  trend?: "up" | "down" | "flat";
  tone?: OpsTone | "info";
  active?: boolean;
  onClick?: () => void;
}) {
  const pct = Math.max(0, Math.min(100, Math.round(sharePercent)));
  const className = `ops-jobs-kpi is-hotel tone-${tone}${active ? " is-active" : ""}${onClick ? "" : " is-static"}`;
  const body = (
    <>
      <span className="ops-jobs-kpi__top">
        <em className="ops-jobs-kpi__label">{label}</em>
        <span className="ops-jobs-kpi__glyph">
          <KpiIcon kind={kind} />
        </span>
      </span>
      <strong className="ops-jobs-kpi__value">{value}</strong>
      <span className="ops-jobs-kpi__foot">
        <span className={`ops-jobs-kpi__trend is-${trend}${active ? " is-on-mint" : ""}`}>
          <i aria-hidden="true" />
          {pct}%
        </span>
        <span className="ops-jobs-kpi__hint">{detail}</span>
      </span>
    </>
  );

  if (onClick) {
    return (
      <button type="button" className={className} title={detail} aria-pressed={active} onClick={onClick}>
        {body}
      </button>
    );
  }

  return (
    <div className={className} title={detail}>
      {body}
    </div>
  );
}

export function OpsJobsPage() {
  const t = useT();
  const searchParams = useSearchParams();
  const focusJobId = (searchParams.get("job_id") ?? "").trim() || null;
  const statusFromUrl = parseStatusFilter(searchParams.get("status") ?? "");
  const [pageSize, setPageSize] = useState(() =>
    readOperatorListPageSize(OPS_JOBS_PAGE_SIZE_STORAGE_KEY, OPERATOR_LIST_PAGE_SIZE_PRESETS, JOBS_PAGE_SIZE_DEFAULT)
  );
  const [jobs, setJobs] = useState<Job[]>([]);
  const [totalCount, setTotalCount] = useState(0);
  const [metrics, setMetrics] = useState<OperationalMetrics | null>(null);
  const [loadingMore, setLoadingMore] = useState(false);
  const [inlineError, setInlineError] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState<StatusFilter>(() => statusFromUrl ?? "all");
  const [jobTypeFilter, setJobTypeFilter] = useState("all");
  const [searchQuery, setSearchQuery] = useState("");
  const [copiedJobId, setCopiedJobId] = useState<string | null>(null);
  const action = useAsyncAction();
  const request = useLatestRequest();
  const { notify } = useNotice();

  async function load(mode: LatestRequestMode = jobs.length || metrics ? "refresh" : "initial", nextPageSize = pageSize) {
    setInlineError(null);
    await request.run(
      async () => Promise.all([
        fetchJobs(undefined, { limit: nextPageSize, offset: 0 }),
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

  async function loadMore() {
    if (loadingMore || !hasMoreOffsetItems(jobs.length, totalCount)) return;
    setLoadingMore(true);
    setInlineError(null);
    try {
      const jobPayload = await fetchJobs(undefined, { limit: pageSize, offset: jobs.length });
      setJobs((current) => mergeOffsetItemsById(current, jobPayload.jobs));
      setTotalCount(jobPayload.total_count);
    } catch (err) {
      setInlineError(err instanceof Error ? err.message : t("opsJobs.unavailableTitle"));
    } finally {
      setLoadingMore(false);
    }
  }

  function handlePageSizeChange(nextPageSize: number) {
    if (nextPageSize === pageSize) return;
    writeOperatorListPageSize(OPS_JOBS_PAGE_SIZE_STORAGE_KEY, nextPageSize, OPERATOR_LIST_PAGE_SIZE_PRESETS);
    setPageSize(nextPageSize);
    void load("refresh", nextPageSize);
  }

  function toggleStatusFilter(next: StatusFilter) {
    setStatusFilter((current) => (current === next ? "all" : next));
  }

  function clearFilters() {
    setStatusFilter("all");
    setJobTypeFilter("all");
    setSearchQuery("");
  }

  useEffect(() => {
    void load("initial");
  }, [t]);

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
    const types = Array.from(new Set(jobs.map((job) => job.job_type))).sort();
    return types;
  }, [jobs]);

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
        setJobs((current) => current.filter((item) => item.id !== job.id));
        setTotalCount((current) => Math.max(0, current - 1));
        notify({ message: `${t("common.delete")}: #${job.id.slice(0, 8)}`, tone: "success" });
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

  const staleRunning = useMemo(() => jobs.filter((job) => isStaleRunning(job)), [jobs]);
  const failed = useMemo(() => jobs.filter((job) => job.status === "FAILED"), [jobs]);
  const retryable = useMemo(() => jobs.filter((job) => job.status === "RETRYABLE"), [jobs]);
  const running = useMemo(() => jobs.filter((job) => job.status === "RUNNING"), [jobs]);

  const visibleJobs = useMemo(() => {
    return jobs.filter((job) => {
      if (!jobMatchesSearch(job, searchQuery)) return false;
      if (jobTypeFilter !== "all" && job.job_type !== jobTypeFilter) return false;
      if (statusFilter === "all") return true;
      if (statusFilter === "stale") return isStaleRunning(job);
      return job.status === statusFilter;
    });
  }, [jobs, searchQuery, statusFilter, jobTypeFilter]);

  const hasMore = hasMoreOffsetItems(jobs.length, totalCount);
  const failureCategories = metrics?.common_failure_categories ?? [];
  const backlog = metrics?.queue_backlog.queued ?? 0;
  const retries = metrics?.total_retry_attempts ?? 0;
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
        skeleton={<OpsState title={t("opsJobs.loadingTitle")} detail={t("opsJobs.loadingDetail")} />}
        errorState={<OpsState title={t("opsJobs.unavailableTitle")} detail={request.error?.message ?? t("opsJobs.unavailableTitle")} retry={() => void load("initial")} />}
      >
      <main className="ops-page ops-jobs-monitor is-compact">
        {visibleError ? <div className="inline-error">{visibleError}</div> : null}

        <section className="ops-jobs-kpis is-hotel" role="group" aria-label={t("opsJobs.filterByStatus")}>
          <KpiTile
            kind="running"
            label={t("opsJobs.running")}
            value={String(running.length)}
            detail={t("opsJobs.ofLoaded")}
            sharePercent={jobs.length > 0 ? (running.length / jobs.length) * 100 : 0}
            trend="up"
            tone={running.length > 0 ? "info" : "muted"}
            active={statusFilter === "RUNNING"}
            onClick={() => toggleStatusFilter("RUNNING")}
          />
          <KpiTile
            kind="failed"
            label={t("opsJobs.failed")}
            value={String(failed.length)}
            detail={t("opsJobs.ofLoaded")}
            sharePercent={jobs.length > 0 ? (failed.length / jobs.length) * 100 : 0}
            trend="down"
            tone={failed.length > 0 ? "danger" : "muted"}
            active={statusFilter === "FAILED"}
            onClick={() => toggleStatusFilter("FAILED")}
          />
          <KpiTile
            kind="retryable"
            label={t("opsJobs.retryable")}
            value={String(retryable.length)}
            detail={t("opsJobs.ofLoaded")}
            sharePercent={jobs.length > 0 ? (retryable.length / jobs.length) * 100 : 0}
            trend="up"
            tone={retryable.length > 0 ? "warn" : "muted"}
            active={statusFilter === "RETRYABLE"}
            onClick={() => toggleStatusFilter("RETRYABLE")}
          />
          <KpiTile
            kind="stale"
            label={t("opsJobs.staleShort")}
            value={String(staleRunning.length)}
            detail={t("opsJobs.ofLoaded")}
            sharePercent={jobs.length > 0 ? (staleRunning.length / jobs.length) * 100 : 0}
            trend="flat"
            tone="muted"
            active={statusFilter === "stale"}
            onClick={() => toggleStatusFilter("stale")}
          />
          <KpiTile
            kind="backlog"
            label={t("opsJobs.backlog")}
            value={String(backlog)}
            detail={t("opsJobs.queuedJobs")}
            sharePercent={totalCount > 0 ? Math.min(100, (backlog / totalCount) * 100) : 0}
            trend={backlog > 0 ? "down" : "flat"}
            tone={backlog > 0 ? "warn" : "muted"}
          />
          <KpiTile
            kind="retries"
            label={t("opsJobs.retriesShort")}
            value={String(retries)}
            detail={t("opsJobs.allTimeAttempts")}
            sharePercent={jobs.length > 0 ? Math.min(100, (retries / Math.max(jobs.length, 1)) * 100) : 0}
            trend={retries > 0 ? "up" : "flat"}
            tone={retries > 0 ? "info" : "muted"}
          />
        </section>

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
              onChange={(event) => setStatusFilter(event.target.value as StatusFilter)}
            >
              <option value="all">{t("opsJobs.statusAll")}</option>
              <option value="RUNNING">{t("opsJobs.running")}</option>
              <option value="COMPLETED">{t("opsJobs.statusCompleted")}</option>
              <option value="FAILED">{t("opsJobs.failed")}</option>
              <option value="RETRYABLE">{t("opsJobs.retryable")}</option>
              <option value="QUEUED">{t("opsJobs.statusQueued")}</option>
              <option value="stale">{t("opsJobs.staleShort")}</option>
            </select>
          </label>

          <label className="ops-jobs-controls__type">
            <span className="visually-hidden">{t("opsJobs.jobType")}</span>
            <select value={jobTypeFilter} onChange={(event) => setJobTypeFilter(event.target.value)}>
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

        {failureCategories.length > 0 ? (
          <div className="ops-jobs-failures" aria-label={t("opsJobs.commonFailureCategories")}>
            <span>{t("opsJobs.commonFailureCategories")}</span>
            <ul>
              {failureCategories.map((item) => (
                <li key={item.error_code}>
                  <code>{item.error_code}</code>
                  <em>{item.count}</em>
                </li>
              ))}
            </ul>
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
                    <th>{t("opsJobs.jobId")}</th>
                    <th>{t("opsJobs.videoSource")}</th>
                    <th>{t("opsJobs.type")}</th>
                    <th>{t("opsJobs.progress")}</th>
                    <th>{t("opsJobs.startedAt")}</th>
                    <th>{t("opsJobs.finishedAt")}</th>
                    <th>{t("opsJobs.duration")}</th>
                    <th>{t("opsJobs.status")}</th>
                    <th>{t("opsJobs.actions")}</th>
                  </tr>
                </thead>
                <tbody>
                  {visibleJobs.map((job) => {
                    const tone =
                      job.status === "COMPLETED" && job.error_message ? "warn" : statusTone(job.status);
                    const typeTone = jobTypePillTone(job.job_type);
                    const source = videoSourceLabel(job);
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
                    const canRetry = job.status === "FAILED" || job.status === "RETRYABLE";
                    return (
                      <tr
                        className={`tone-${tone}${job.id === focusJobId ? " is-focused" : ""}`}
                        id={`ops-job-row-${job.id}`}
                        key={job.id}
                      >
                        <td>
                          <div className="ops-jobs-table__id">
                            <strong title={job.id}>#{job.id.slice(0, 8)}</strong>
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
                        </td>
                        <td>
                          {source.href ? (
                            <Link className="ops-jobs-table__source" href={source.href}>
                              {source.label}
                            </Link>
                          ) : (
                            <span className={`ops-jobs-table__source${source.label === "—" ? " is-empty" : ""}`}>
                              {source.label}
                            </span>
                          )}
                        </td>
                        <td>
                          <span className={`ops-jobs-table__type tone-${typeTone}`} title={job.job_type}>
                            {formatJobTypeLabel(job.job_type)}
                          </span>
                        </td>
                        <td>
                          <div className="ops-jobs-table__progress" aria-label={`${progress}%`}>
                            <div className="ops-jobs-table__bar">
                              <span style={{ width: `${progress}%` }} />
                            </div>
                            <em>{progress}%</em>
                          </div>
                        </td>
                        <td>
                          {job.started_at ? (
                            <time dateTime={job.started_at} title={job.started_at}>
                              {formatTableDateTime(job.started_at)}
                            </time>
                          ) : (
                            <span className="ops-jobs-table__empty">—</span>
                          )}
                        </td>
                        <td>
                          {job.finished_at ? (
                            <time dateTime={job.finished_at} title={job.finished_at}>
                              {formatTableDateTime(job.finished_at)}
                            </time>
                          ) : (
                            <span className="ops-jobs-table__empty">—</span>
                          )}
                        </td>
                        <td>
                          <span className="ops-jobs-table__duration" title={t("opsJobs.duration")}>
                            {formatJobDuration(job.started_at, job.finished_at)}
                          </span>
                        </td>
                        <td className="ops-jobs-table__status-cell">
                          <span className={jobStatusChipClass(job.status, tone)}>
                            <i className="ops-jobs-table__status-dot" aria-hidden="true" />
                            {formatStatusLabel(job.status)}
                          </span>
                        </td>
                        <td>
                          <div className="ops-jobs-table__actions">
                            <AsyncButton
                              type="button"
                              className="ops-jobs-table__retry is-icon"
                              disabled={!canRetry}
                              aria-label={t("opsJobs.retry")}
                              title={t("opsJobs.retry")}
                              pending={action.isPending(`retry-${job.id}`)}
                              pendingLabel="…"
                              onClick={() => void handleRetry(job)}
                            >
                              <JobActionIcon kind="retry" />
                            </AsyncButton>
                            <AsyncButton
                              className="ops-jobs-delete is-icon"
                              type="button"
                              aria-label={t("common.delete")}
                              title={t("common.delete")}
                              pending={action.isPending(`delete-${job.id}`)}
                              pendingLabel="…"
                              onClick={() => void handleDelete(job)}
                            >
                              <JobActionIcon kind="delete" />
                            </AsyncButton>
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </section>
        )}

        {(hasMore || totalCount > 0) && jobs.length > 0 ? (
          <OffsetLoadMoreFooter
            className="ops-jobs-monitor__footer"
            loadedCount={jobs.length}
            loadingMore={loadingMore}
            noun="jobs"
            onLoadMore={() => void loadMore()}
            onPageSizeChange={handlePageSizeChange}
            pageSize={pageSize}
            pageSizeOptions={OPERATOR_LIST_PAGE_SIZE_PRESETS}
            totalCount={totalCount}
            variant="inline"
          />
        ) : null}
      </main>
      </AsyncContentBoundary>
    </OpsConsoleShell>
  );
}
