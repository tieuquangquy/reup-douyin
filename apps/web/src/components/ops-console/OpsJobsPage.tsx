"use client";

import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import { deleteJob, fetchJobs, fetchOperationalMetrics } from "../../lib/api";
import { useT } from "../../lib/i18n";
import { hasMoreOffsetItems, mergeOffsetItemsById } from "../../lib/offsetListPagination";
import {
  OPERATOR_LIST_PAGE_SIZE_PRESETS,
  OPS_JOBS_PAGE_SIZE_STORAGE_KEY,
  readOperatorListPageSize,
  writeOperatorListPageSize,
} from "../../lib/operatorListPageSize";
import type { Job } from "../../types/jobs";
import type { OperationalMetrics } from "../../types/operations";
import { OpsMetricCard, OpsPageHeader, OpsPanel, OpsState, formatDateTime, statusTone } from "./OpsShared";
import { StatusBadge } from "../app-shell/StatusBadge";
import { OffsetLoadMoreFooter } from "../shared/OffsetLoadMoreFooter";

const STALE_RUNNING_MINUTES = 60;
const JOBS_PAGE_SIZE_DEFAULT = 50;

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

  const staleRunning = useMemo(() => jobs.filter((job) => isStaleRunning(job)), [jobs]);
  const failed = jobs.filter((job) => job.status === "FAILED");
  const retryable = jobs.filter((job) => job.status === "RETRYABLE");
  const running = jobs.filter((job) => job.status === "RUNNING");
  const hasMore = hasMoreOffsetItems(jobs.length, totalCount);

  if (loading && jobs.length === 0) return <OpsState title={t("opsJobs.loadingTitle")} detail={t("opsJobs.loadingDetail")} />;
  if (error && jobs.length === 0) return <OpsState title={t("opsJobs.unavailableTitle")} detail={error} retry={() => void load()} />;

  return (
    <main className="ops-page">
      <OpsPageHeader title={t("opsJobs.title")} description={t("opsJobs.description")} actions={<button type="button" onClick={() => void load()}>{t("common.refresh")}</button>} />
      {error ? <div className="inline-error">{error}</div> : null}
      {focusJobId ? (
        <div className={`inline-notice ${focusedJob ? "is-good" : "is-warn"}`} role="status">
          {focusedJob
            ? `Focused job ${focusedJob.id.slice(0, 8)} · ${focusedJob.job_type} · ${focusedJob.status}`
            : `Looking for job ${focusJobId.slice(0, 8)}… not in the first ${jobs.length} rows — use Load more or refresh.`}
        </div>
      ) : null}

      <section className="health-overview-grid">
        <OpsMetricCard label={t("opsJobs.running")} value={String(running.length)} detail={t("opsJobs.currentlyActive")} tone={running.length > 0 ? "good" : "muted"} />
        <OpsMetricCard label={t("opsJobs.failed")} value={String(failed.length)} detail={t("opsJobs.terminalFailures")} tone={failed.length > 0 ? "danger" : "good"} />
        <OpsMetricCard label={t("opsJobs.retryable")} value={String(retryable.length)} detail={t("opsJobs.safeToRetry")} tone={retryable.length > 0 ? "warn" : "good"} />
        <OpsMetricCard label={t("opsJobs.staleRunning")} value={String(staleRunning.length)} detail={`${STALE_RUNNING_MINUTES} ${t("opsJobs.runningOver")}`} tone={staleRunning.length > 0 ? "warn" : "good"} />
        <OpsMetricCard label={t("opsJobs.backlog")} value={String(metrics?.queue_backlog.queued ?? 0)} detail={t("opsJobs.queuedJobs")} />
        <OpsMetricCard label={t("opsJobs.retryAttempts")} value={String(metrics?.total_retry_attempts ?? 0)} detail={t("opsJobs.allTimeAttempts")} />
      </section>

      <section className="ops-grid">
        <OpsPanel title={t("opsJobs.latestJobs")}>
          <table className="health-table">
            <thead>
              <tr><th>{t("opsJobs.job")}</th><th>{t("opsJobs.type")}</th><th>{t("opsJobs.status")}</th><th>{t("opsJobs.progress")}</th><th>{t("opsJobs.currentStep")}</th><th>{t("opsJobs.error")}</th><th>{t("opsJobs.updated")}</th><th>{t("opsJobs.actions")}</th></tr>
            </thead>
            <tbody>
              {jobs.length === 0 ? <tr><td colSpan={8}>{t("opsJobs.noJobsFound")}</td></tr> : null}
              {jobs.map((job) => (
                <tr
                  className={job.id === focusJobId ? "is-job-focused" : undefined}
                  id={`ops-job-row-${job.id}`}
                  key={job.id}
                >
                  <td>{job.id.slice(0, 8)}</td>
                  <td>{job.job_type}</td>
                  <td><StatusBadge label={job.status} tone={statusTone(job.status)} /></td>
                  <td>{job.progress_percent}%</td>
                  <td>{job.current_step_key ?? "-"}</td>
                  <td title={[job.error_code, job.error_message].filter(Boolean).join(": ") || undefined}>
                    {job.error_message ?? job.error_code ?? "-"}
                  </td>
                  <td>{formatDateTime(job.updated_at)}</td>
                  <td>
                    <button
                      className="danger"
                      type="button"
                      disabled={deletingJobId === job.id}
                      onClick={() => void handleDelete(job)}
                    >
                      {deletingJobId === job.id ? t("opsJobs.deleting") : t("common.delete")}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {(hasMore || totalCount > 0) && jobs.length > 0 ? (
            <OffsetLoadMoreFooter
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
        </OpsPanel>

        <OpsPanel title={t("opsJobs.commonFailureCategories")}>
          <ul className="compact-list">
            {(metrics?.common_failure_categories ?? []).length === 0 ? <li>{t("opsJobs.noFailureCategories")}</li> : null}
            {metrics?.common_failure_categories.map((item) => (
              <li key={item.error_code}><strong>{item.error_code}</strong><span>{item.count} jobs</span></li>
            ))}
          </ul>
        </OpsPanel>
      </section>
    </main>
  );
}

function isStaleRunning(job: Job): boolean {
  if (job.status !== "RUNNING") return false;
  const started = new Date(job.started_at ?? job.updated_at);
  if (Number.isNaN(started.getTime())) return false;
  return Date.now() - started.getTime() > STALE_RUNNING_MINUTES * 60 * 1000;
}
