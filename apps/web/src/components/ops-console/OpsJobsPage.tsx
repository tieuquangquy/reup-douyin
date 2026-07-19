"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import { deleteJob, fetchJobs, fetchOperationalMetrics, retryJob } from "../../lib/api";
import { useT } from "../../lib/i18n";
import { hasMoreOffsetItems, mergeOffsetItemsById } from "../../lib/offsetListPagination";
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

const STALE_RUNNING_MINUTES = 60;
const JOBS_PAGE_SIZE_DEFAULT = 50;

type StatusFilter = "all" | "stale" | JobStatus;

function formatJobTypeLabel(jobType: string): string {
  return jobType
    .split(/[_-]+/)
    .filter(Boolean)
    .map((part) => part.charAt(0) + part.slice(1).toLowerCase())
    .join(" ");
}

function formatRelativeStamp(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  const seconds = Math.max(0, Math.floor((Date.now() - date.getTime()) / 1000));
  if (seconds < 60) return `${seconds}s ago`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes} min${minutes === 1 ? "" : "s"} ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 48) return `${hours} hour${hours === 1 ? "" : "s"} ago`;
  const days = Math.floor(hours / 24);
  return `${days} day${days === 1 ? "" : "s"} ago`;
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

function KpiIcon({ kind }: { kind: "running" | "failed" | "retryable" | "stale" }) {
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
  tone = "muted",
  active = false,
  onClick,
}: {
  kind: "running" | "failed" | "retryable" | "stale";
  label: string;
  value: string;
  detail: string;
  tone?: OpsTone | "info";
  active?: boolean;
  onClick?: () => void;
}) {
  return (
    <button
      type="button"
      className={`ops-jobs-kpi tone-${tone}${active ? " is-active" : ""}`}
      title={detail}
      aria-pressed={active}
      onClick={onClick}
    >
      <span className="ops-jobs-kpi__glyph">
        <KpiIcon kind={kind} />
      </span>
      <span className="ops-jobs-kpi__body">
        <em>{label}</em>
        <strong>{value}</strong>
        <small>{detail}</small>
      </span>
    </button>
  );
}

export function OpsJobsPage() {
  const t = useT();
  const searchParams = useSearchParams();
  const focusJobId = (searchParams.get("job_id") ?? "").trim() || null;
  const [pageSize, setPageSize] = useState(() =>
    readOperatorListPageSize(OPS_JOBS_PAGE_SIZE_STORAGE_KEY, OPERATOR_LIST_PAGE_SIZE_PRESETS, JOBS_PAGE_SIZE_DEFAULT)
  );
  const [jobs, setJobs] = useState<Job[]>([]);
  const [totalCount, setTotalCount] = useState(0);
  const [metrics, setMetrics] = useState<OperationalMetrics | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [deletingJobId, setDeletingJobId] = useState<string | null>(null);
  const [retryingJobId, setRetryingJobId] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [jobTypeFilter, setJobTypeFilter] = useState("all");
  const [searchQuery, setSearchQuery] = useState("");
  const [copiedJobId, setCopiedJobId] = useState<string | null>(null);

  async function load(nextPageSize = pageSize) {
    setLoading(true);
    setError(null);
    try {
      const [jobPayload, metricsPayload] = await Promise.all([
        fetchJobs(undefined, { limit: nextPageSize, offset: 0 }),
        fetchOperationalMetrics(),
      ]);
      setJobs(jobPayload.jobs);
      setTotalCount(jobPayload.total_count);
      setMetrics(metricsPayload);
    } catch (err) {
      setError(err instanceof Error ? err.message : t("opsJobs.unavailableTitle"));
    } finally {
      setLoading(false);
    }
  }

  async function loadMore() {
    if (loadingMore || !hasMoreOffsetItems(jobs.length, totalCount)) return;
    setLoadingMore(true);
    setError(null);
    try {
      const jobPayload = await fetchJobs(undefined, { limit: pageSize, offset: jobs.length });
      setJobs((current) => mergeOffsetItemsById(current, jobPayload.jobs));
      setTotalCount(jobPayload.total_count);
    } catch (err) {
      setError(err instanceof Error ? err.message : t("opsJobs.unavailableTitle"));
    } finally {
      setLoadingMore(false);
    }
  }

  function handlePageSizeChange(nextPageSize: number) {
    if (nextPageSize === pageSize) return;
    writeOperatorListPageSize(OPS_JOBS_PAGE_SIZE_STORAGE_KEY, nextPageSize, OPERATOR_LIST_PAGE_SIZE_PRESETS);
    setPageSize(nextPageSize);
    void load(nextPageSize);
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
    void load();
  }, [t]);

  useEffect(() => {
    if (!focusJobId || loading) return;
    const row = document.getElementById(`ops-job-row-${focusJobId}`);
    row?.scrollIntoView({ block: "center", behavior: "smooth" });
  }, [focusJobId, loading, jobs]);

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

    setDeletingJobId(job.id);
    setError(null);
    try {
      await deleteJob(job.id);
      setJobs((current) => current.filter((item) => item.id !== job.id));
      setTotalCount((current) => Math.max(0, current - 1));
    } catch (err) {
      setError(err instanceof Error ? err.message : t("opsJobs.deleteFailed"));
    } finally {
      setDeletingJobId(null);
    }
  }

  async function handleRetry(job: Job) {
    setRetryingJobId(job.id);
    setError(null);
    try {
      const updated = await retryJob(job.id);
      setJobs((current) => current.map((item) => (item.id === job.id ? updated : item)));
    } catch (err) {
      setError(err instanceof Error ? err.message : t("opsJobs.retryFailed"));
    } finally {
      setRetryingJobId(null);
    }
  }

  async function handleCopyId(jobId: string) {
    try {
      await navigator.clipboard.writeText(jobId);
      setCopiedJobId(jobId);
      window.setTimeout(() => setCopiedJobId((current) => (current === jobId ? null : current)), 1200);
    } catch {
      setError(t("opsJobs.copyFailed"));
    }
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
    <TopbarRefreshButton busy={loading && jobs.length > 0} disabled={loading && jobs.length === 0} onClick={() => void load()} />
  );

  if (loading && jobs.length === 0) {
    return (
      <OpsConsoleShell actions={refreshAction} description={t("opsJobs.description")} title={t("opsJobs.title")}>
        <OpsState title={t("opsJobs.loadingTitle")} detail={t("opsJobs.loadingDetail")} />
      </OpsConsoleShell>
    );
  }

  if (error && jobs.length === 0) {
    return (
      <OpsConsoleShell actions={refreshAction} description={t("opsJobs.description")} title={t("opsJobs.title")}>
        <OpsState title={t("opsJobs.unavailableTitle")} detail={error} retry={() => void load()} />
      </OpsConsoleShell>
    );
  }

  return (
    <OpsConsoleShell actions={refreshAction} description={t("opsJobs.description")} title={t("opsJobs.title")}>
      <main className="ops-page ops-jobs-monitor is-compact">
        {error ? <div className="inline-error">{error}</div> : null}

        <section className="ops-jobs-kpis" role="group" aria-label={t("opsJobs.filterByStatus")}>
          <KpiTile
            kind="running"
            label={t("opsJobs.running")}
            value={String(running.length)}
            detail={t("opsJobs.jobsActive")}
            tone={running.length > 0 ? "info" : "muted"}
            active={statusFilter === "RUNNING"}
            onClick={() => toggleStatusFilter("RUNNING")}
          />
          <KpiTile
            kind="failed"
            label={t("opsJobs.failed")}
            value={String(failed.length)}
            detail={t("opsJobs.jobErrors")}
            tone={failed.length > 0 ? "danger" : "muted"}
            active={statusFilter === "FAILED"}
            onClick={() => toggleStatusFilter("FAILED")}
          />
          <KpiTile
            kind="retryable"
            label={t("opsJobs.retryable")}
            value={String(retryable.length)}
            detail={t("opsJobs.jobsToRetry")}
            tone={retryable.length > 0 ? "warn" : "muted"}
            active={statusFilter === "RETRYABLE"}
            onClick={() => toggleStatusFilter("RETRYABLE")}
          />
          <KpiTile
            kind="stale"
            label={t("opsJobs.staleShort")}
            value={String(staleRunning.length)}
            detail={t("opsJobs.idleJobs")}
            tone="muted"
            active={statusFilter === "stale"}
            onClick={() => toggleStatusFilter("stale")}
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

          <p className="ops-jobs-controls__showing">
            {t("opsJobs.showingOf")
              .replace("{shown}", String(shownCount))
              .replace("{total}", String(totalCount))}
          </p>

          <div className="ops-jobs-controls__pill" title={`${t("opsJobs.queuedJobs")} · ${t("opsJobs.allTimeAttempts")}`}>
            <span>
              {t("opsJobs.backlog")}: {backlog}
            </span>
            <span aria-hidden="true">|</span>
            <span>
              {t("opsJobs.retriesShort")}: {retries}
            </span>
          </div>

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
          <div className="ops-jobs-table-wrap">
            <table className="ops-jobs-table">
              <thead>
                <tr>
                  <th>{t("opsJobs.job")}</th>
                  <th>{t("opsJobs.videoSource")}</th>
                  <th>{t("opsJobs.status")}</th>
                  <th>{t("opsJobs.progress")}</th>
                  <th>{t("opsJobs.updated")}</th>
                  <th>{t("opsJobs.actions")}</th>
                </tr>
              </thead>
              <tbody>
                {visibleJobs.map((job) => {
                  const tone =
                    job.status === "COMPLETED" && job.error_message ? "warn" : statusTone(job.status);
                  const source = videoSourceLabel(job);
                  const progress = Math.max(0, Math.min(100, Number(job.progress_percent) || 0));
                  const showProgress = !(job.status === "COMPLETED" && progress >= 100);
                  const canRetry = job.status === "FAILED" || job.status === "RETRYABLE";
                  const deleting = deletingJobId === job.id;
                  const retrying = retryingJobId === job.id;
                  return (
                    <tr
                      className={`tone-${tone}${job.id === focusJobId ? " is-focused" : ""}`}
                      id={`ops-job-row-${job.id}`}
                      key={job.id}
                    >
                      <td>
                        <div className="ops-jobs-table__job is-inline">
                          <strong title={job.job_type}>{formatJobTypeLabel(job.job_type)}</strong>
                          <code title={job.id}>{job.id.slice(0, 8)}</code>
                          <button
                            type="button"
                            className="ops-jobs-table__copy"
                            aria-label={t("opsJobs.copyId")}
                            title={copiedJobId === job.id ? t("opsJobs.copied") : t("opsJobs.copyId")}
                            onClick={() => void handleCopyId(job.id)}
                          >
                            {copiedJobId === job.id ? "✓" : "⧉"}
                          </button>
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
                        <span className={`ops-jobs-table__badge tone-${tone}`}>{job.status}</span>
                      </td>
                      <td>
                        {showProgress ? (
                          <div className="ops-jobs-table__progress" aria-label={`${progress}%`}>
                            <div className="ops-jobs-table__bar">
                              <span style={{ width: `${progress}%` }} />
                            </div>
                            <em>{progress}%</em>
                          </div>
                        ) : (
                          <span className="ops-jobs-table__done">{t("opsJobs.doneShort")}</span>
                        )}
                      </td>
                      <td>
                        <time dateTime={job.updated_at} title={job.updated_at}>
                          {formatRelativeStamp(job.updated_at)}
                        </time>
                      </td>
                      <td>
                        <div className="ops-jobs-table__actions">
                          {job.source_video_id ? (
                            <Link
                              className="ops-jobs-table__view"
                              href={`/source-videos/${job.source_video_id}`}
                              aria-label={t("opsJobs.viewJob")}
                              title={t("opsJobs.viewJob")}
                            >
                              <svg viewBox="0 0 24 24" aria-hidden="true">
                                <path
                                  d="M2.5 12s3.5-6.5 9.5-6.5S21.5 12 21.5 12s-3.5 6.5-9.5 6.5S2.5 12 2.5 12Z"
                                  fill="none"
                                  stroke="currentColor"
                                  strokeWidth="1.7"
                                />
                                <circle cx="12" cy="12" r="2.5" fill="none" stroke="currentColor" strokeWidth="1.7" />
                              </svg>
                            </Link>
                          ) : (
                            <span className="ops-jobs-table__view is-disabled" aria-hidden="true">
                              <svg viewBox="0 0 24 24">
                                <path
                                  d="M2.5 12s3.5-6.5 9.5-6.5S21.5 12 21.5 12s-3.5 6.5-9.5 6.5S2.5 12 2.5 12Z"
                                  fill="none"
                                  stroke="currentColor"
                                  strokeWidth="1.7"
                                />
                                <circle cx="12" cy="12" r="2.5" fill="none" stroke="currentColor" strokeWidth="1.7" />
                              </svg>
                            </span>
                          )}
                          <button
                            type="button"
                            className="ops-jobs-table__retry"
                            disabled={!canRetry || retrying}
                            aria-label={t("opsJobs.retry")}
                            title={t("opsJobs.retry")}
                            onClick={() => void handleRetry(job)}
                          >
                            {retrying ? "…" : (
                              <svg viewBox="0 0 24 24" aria-hidden="true">
                                <path
                                  d="M19.5 12a7.5 7.5 0 1 1-2.2-5.3"
                                  fill="none"
                                  stroke="currentColor"
                                  strokeWidth="1.7"
                                  strokeLinecap="round"
                                />
                                <path
                                  d="M19.5 5v5h-5"
                                  fill="none"
                                  stroke="currentColor"
                                  strokeWidth="1.7"
                                  strokeLinecap="round"
                                  strokeLinejoin="round"
                                />
                              </svg>
                            )}
                          </button>
                          <button
                            className="ops-jobs-delete"
                            type="button"
                            disabled={deleting}
                            aria-label={t("common.delete")}
                            title={t("common.delete")}
                            onClick={() => void handleDelete(job)}
                          >
                            {deleting ? "…" : "×"}
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
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
          />
        ) : null}
      </main>
    </OpsConsoleShell>
  );
}
