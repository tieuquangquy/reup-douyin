import type { Job, JobStatus, JobType } from "../types/jobs";

export type TranscriptActiveJobKind = "tts" | "translate" | "reanalyze";

const ACTIVE_STATUSES = new Set<string>(["QUEUED", "RUNNING"]);

const KIND_BY_TYPE: Partial<Record<JobType, TranscriptActiveJobKind>> = {
  SYNTHESIZE_TTS: "tts",
  BUILD_TRANSLATION_DRAFT: "translate",
  ANALYZE_AUDIO: "reanalyze"
};

export function isActiveTranscriptJobStatus(status: string): boolean {
  return ACTIVE_STATUSES.has(status.toUpperCase());
}

export function transcriptJobKindFromType(jobType: string): TranscriptActiveJobKind | null {
  return KIND_BY_TYPE[jobType as JobType] ?? null;
}

/** Prefer the newest in-flight transcript editor job (TTS / translate / re-ASR). */
export function pickActiveTranscriptJob(jobs: Job[]): Job | null {
  const candidates = jobs.filter(
    (job) => isActiveTranscriptJobStatus(job.status) && transcriptJobKindFromType(job.job_type) !== null
  );
  if (candidates.length === 0) return null;
  return candidates.reduce((best, job) => {
    const bestKey = `${best.updated_at || best.created_at}|${best.created_at}`;
    const jobKey = `${job.updated_at || job.created_at}|${job.created_at}`;
    return jobKey > bestKey ? job : best;
  });
}
