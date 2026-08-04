import type { Job, JobStatus, JobType } from "../types/jobs";

const ACTIVE_STATUSES = new Set<string>(["QUEUED", "RUNNING"]);

// RENDER_PREVIEW is the durable Phase 3 review + adaptive visual-preview job in
// QUALITY_LOCALIZATION_V24_1.  Final Review presents both jobs as one
// localization preparation session, so refresh/reopen must reattach to either.
const OCR_JOB_TYPES = new Set<JobType>(["ANALYZE_OCR", "RENDER_PREVIEW"]);
const RENDER_JOB_TYPES = new Set<JobType>(["RENDER_FINAL"]);

export function isActiveFinalReviewJobStatus(status: string): boolean {
  return ACTIVE_STATUSES.has(status.toUpperCase());
}

export function isOcrJobType(jobType: string): boolean {
  return OCR_JOB_TYPES.has(jobType as JobType);
}

export function isRenderJobType(jobType: string): boolean {
  return RENDER_JOB_TYPES.has(jobType as JobType);
}

function pickNewestActiveJob(jobs: Job[], matchesType: (jobType: string) => boolean): Job | null {
  const candidates = jobs.filter(
    (job) => isActiveFinalReviewJobStatus(job.status) && matchesType(job.job_type)
  );
  if (candidates.length === 0) return null;
  return candidates.reduce((best, job) => {
    const bestKey = `${best.updated_at || best.created_at}|${best.created_at}`;
    const jobKey = `${job.updated_at || job.created_at}|${job.created_at}`;
    return jobKey > bestKey ? job : best;
  });
}

/** Prefer the newest in-flight localization-preparation job for Final Review. */
export function pickActiveOcrJob(jobs: Job[]): Job | null {
  return pickNewestActiveJob(jobs, isOcrJobType);
}

/** Prefer the newest in-flight RENDER_FINAL job for Final Review start/rerender. */
export function pickActiveRenderJob(jobs: Job[]): Job | null {
  return pickNewestActiveJob(jobs, isRenderJobType);
}

export function isActiveOcrJobStatus(status: JobStatus | string): boolean {
  return isActiveFinalReviewJobStatus(status);
}
