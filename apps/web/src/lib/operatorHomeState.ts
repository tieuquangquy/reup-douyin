import type { PublishHealthDashboard, PublicationOutcomeItem } from "../types/analytics";
import type { Job } from "../types/jobs";
import type { PublishControlQueue, PublishQueueItem } from "../types/publish-control";
import type { Candidate } from "../types/review-board";
import { humanizeStatus } from "./statusLabels";

export type OperatorMetric = {
  key: string;
  label: string;
  value: string;
  detail: string;
  tone: "good" | "warn" | "danger" | "muted";
  href?: string;
};

export type OperatorActionItem = {
  key: string;
  title: string;
  count: number;
  description: string;
  href: string;
  tone: "good" | "warn" | "danger" | "muted";
  cta: string;
};

export type RecentActivityItem = {
  key: string;
  title: string;
  detail: string;
  at: string | null;
  href: string;
  tone: "good" | "warn" | "danger" | "muted";
};

export type QuickLaunchItem = {
  key: string;
  title: string;
  description: string;
  href: string;
  enabled: boolean;
  tone: "good" | "warn" | "danger" | "muted";
};

export type ContinueItem = {
  key: string;
  title: string;
  description: string;
  href: string;
  tone: "good" | "warn" | "danger" | "muted";
};

const reviewStatuses = new Set(["NEW", "SHORTLISTED", "IN_REVIEW"]);

export function candidatesWaitingReview(candidates: Candidate[]): Candidate[] {
  return candidates.filter((candidate) => reviewStatuses.has(candidate.status));
}

export function pickRecentSourceVideoId(candidates: Candidate[], queue?: PublishControlQueue | null): string | null {
  const readyDraft = queue?.assigned_drafts[0] ?? queue?.unassigned_drafts[0] ?? queue?.scheduled_drafts[0];
  if (readyDraft?.source_video_id) return readyDraft.source_video_id;

  const approved = candidates.find((candidate) => candidate.status === "APPROVED");
  if (approved?.source_video_id) return approved.source_video_id;

  return candidates[0]?.source_video_id ?? null;
}

export function buildOperatorMetrics({
  candidates,
  jobs,
  health,
  queue
}: {
  candidates: Candidate[];
  jobs: Job[];
  health: PublishHealthDashboard | null;
  queue: PublishControlQueue | null;
}): OperatorMetric[] {
  const waiting = candidatesWaitingReview(candidates).length;
  const running = jobs.filter((job) => job.status === "RUNNING").length;
  const failedOrRetryable = jobs.filter((job) => job.status === "FAILED" || job.status === "RETRYABLE").length;
  const readyDrafts = health?.overview.drafts_ready_not_published ?? queueReadyCount(queue);
  const reconciliation = health?.overview.needs_reconciliation_attempts ?? 0;

  return [
    {
      key: "candidates_waiting",
      label: "Candidates waiting review",
      value: String(waiting),
      detail: waiting > 0 ? "Open the review board first." : "No candidate backlog in the current view.",
      tone: waiting > 0 ? "warn" : "good",
      href: "/selection/review-board"
    },
    {
      key: "jobs_running",
      label: "Jobs running",
      value: String(running),
      detail: failedOrRetryable > 0 ? `${failedOrRetryable} failed or retryable jobs need ops review.` : "No failed job pressure from latest job list.",
      tone: failedOrRetryable > 0 ? "danger" : running > 0 ? "warn" : "good",
      href: failedOrRetryable > 0 ? "/ops/jobs" : "/ops/health"
    },
    {
      key: "final_outputs_ready",
      label: "Final outputs ready",
      value: String(readyDrafts),
      detail: "Derived from media publish-ready draft backlog until a dedicated render summary exists.",
      tone: readyDrafts > 0 ? "warn" : "muted",
      href: "/publishing/drafts"
    },
    {
      key: "publish_drafts_ready",
      label: "Publish drafts ready",
      value: String(readyDrafts),
      detail: "Ready drafts waiting for account assignment or publishing.",
      tone: readyDrafts > 0 ? "warn" : "good",
      href: "/publishing/drafts"
    },
    {
      key: "failed_or_reconcile",
      label: "Failed / needs reconciliation",
      value: String(failedOrRetryable + reconciliation),
      detail: `${failedOrRetryable} jobs plus ${reconciliation} publish attempts need attention.`,
      tone: failedOrRetryable + reconciliation > 0 ? "danger" : "good",
      href: reconciliation > 0 ? "/ops/reconciliation" : "/ops/jobs"
    }
  ];
}

export function buildActionQueue({
  candidates,
  health,
  queue,
  recentSourceVideoId
}: {
  candidates: Candidate[];
  health: PublishHealthDashboard | null;
  queue: PublishControlQueue | null;
  recentSourceVideoId: string | null;
}): OperatorActionItem[] {
  const reviewNeeded = candidatesWaitingReview(candidates).length;
  const approvedCandidates = candidates.filter((candidate) => candidate.status === "APPROVED").length;
  const draftsReady = health?.overview.drafts_ready_not_published ?? queueReadyCount(queue);
  const readyDraft = queue?.assigned_drafts[0] ?? queue?.unassigned_drafts[0] ?? queue?.scheduled_drafts[0];
  const readyDraftFromHealth = health?.action_queue.drafts_ready[0];
  const readyDraftId = readyDraft?.publish_draft_id ?? readyDraftFromHealth?.publish_draft_id ?? null;
  const blockedByRisk = health?.overview.drafts_blocked_by_risk ?? 0;
  const reconcileNeeded = health?.action_queue.needs_reconciliation.length ?? 0;
  const reconcileDraftId = health?.action_queue.needs_reconciliation[0]?.publish_draft_id ?? null;

  return [
    {
      key: "review_needed",
      title: "Review needed",
      count: reviewNeeded,
      description: "Candidates waiting for keep/reject decisions.",
      href: "/selection/review-board",
      tone: reviewNeeded > 0 ? "warn" : "good",
      cta: reviewNeeded > 0 ? "Open review board" : "Review board clear"
    },
    {
      key: "transcript_edits_needed",
      title: "Transcript edits needed",
      count: approvedCandidates,
      description: "Approved candidates that may need transcript review before final output.",
      href: recentSourceVideoId ? `/production/transcript-editor/${recentSourceVideoId}` : "/selection/review-board",
      tone: approvedCandidates > 0 ? "warn" : "muted",
      cta: recentSourceVideoId ? "Continue transcript" : "Pick a source video"
    },
    {
      key: "final_review_needed",
      title: "Final review needed",
      count: draftsReady,
      description: "Media publish-ready outputs waiting for final/operator checks.",
      href: recentSourceVideoId ? `/production/final-review/${recentSourceVideoId}` : "/selection/review-board",
      tone: draftsReady > 0 ? "warn" : "muted",
      cta: recentSourceVideoId ? "Open final review" : "Find output"
    },
    {
      key: "blocked_by_risk",
      title: "Blocked by risk",
      count: blockedByRisk,
      description: "Drafts currently blocked or delayed by risk gates.",
      href: blockedByRisk > 0 ? "/ops/risk" : "/ops/publish-health",
      tone: blockedByRisk > 0 ? "danger" : "good",
      cta: blockedByRisk > 0 ? "Review risk" : "No risk block"
    },
    {
      key: "publish_reconciliation_needed",
      title: "Publish reconciliation needed",
      count: reconcileNeeded,
      description: "Publish attempts with uncertain platform status.",
      href: reconcileNeeded > 0 ? "/ops/reconciliation" : (reconcileDraftId ? `/publishing/drafts/${reconcileDraftId}` : "/ops/publish-health"),
      tone: reconcileNeeded > 0 ? "danger" : "good",
      cta: reconcileNeeded > 0 ? "Resolve status" : "Reconciliation clear"
    },
    {
      key: "publish_drafts_ready",
      title: "Publish drafts ready",
      count: draftsReady,
      description: "Drafts ready for account assignment, scheduling, or publish action.",
      href: readyDraftId ? `/publishing/drafts/${readyDraftId}` : "/publishing/drafts",
      tone: draftsReady > 0 ? "warn" : "good",
      cta: draftsReady > 0 ? "Open draft" : "No ready draft"
    }
  ];
}

export function buildRecentActivity({
  jobs,
  health,
  candidates
}: {
  jobs: Job[];
  health: PublishHealthDashboard | null;
  candidates: Candidate[];
}): RecentActivityItem[] {
  const jobItems = jobs.slice(0, 4).map((job) => ({
    key: `job-${job.id}`,
    title: `${formatToken(job.job_type)} ${formatToken(job.status)}`,
    detail: job.error_code ? `${job.error_code}: ${job.error_message ?? "No detail"}` : `${job.completed_steps}/${job.total_steps} steps completed`,
    at: job.updated_at,
    href: job.status === "FAILED" || job.status === "RETRYABLE" ? "/ops/jobs" : "/ops/health",
    tone: job.status === "FAILED" || job.status === "RETRYABLE" ? "danger" as const : job.status === "COMPLETED" ? "good" as const : "warn" as const
  }));

  const publishItems = [
    ...(health?.action_queue.recent_successes ?? []).slice(0, 2).map((item) => publicationActivity(item, "Published", "good" as const)),
    ...(health?.action_queue.needs_reconciliation ?? []).slice(0, 2).map((item) => publicationActivity(item, "Needs reconciliation", "danger" as const))
  ];

  const candidateItems = candidates.slice(0, 2).map((candidate) => ({
    key: `candidate-${candidate.id}`,
    title: `Candidate ${formatToken(candidate.status)}`,
    detail: candidate.source_video?.caption ?? candidate.source_video_id,
    at: candidate.updated_at,
    href: "/selection/review-board",
    tone: candidate.status === "REJECTED" ? "muted" as const : "warn" as const
  }));

  return [...jobItems, ...publishItems, ...candidateItems]
    .sort((left, right) => new Date(right.at ?? 0).getTime() - new Date(left.at ?? 0).getTime())
    .slice(0, 8);
}

export function buildQuickLaunchItems({
  recentSourceVideoId,
  readyDraftSourceVideoId,
  readyDraftId
}: {
  recentSourceVideoId: string | null;
  readyDraftSourceVideoId: string | null;
  readyDraftId?: string | null;
}): QuickLaunchItem[] {
  const transcriptHref = recentSourceVideoId ? `/production/transcript-editor/${recentSourceVideoId}` : "/selection/review-board";
  const finalReviewHref = recentSourceVideoId ? `/production/final-review/${recentSourceVideoId}` : "/selection/review-board";
  const publishHref = readyDraftId ? `/publishing/drafts/${readyDraftId}` : readyDraftSourceVideoId ? "/publishing/drafts" : finalReviewHref;

  return [
    { key: "intake", title: "Source intake", description: "Enter a Douyin profile and discover candidates.", href: "/intake", enabled: true, tone: "good" },
    { key: "review", title: "Review board", description: "Scan and keep/reject scored candidates.", href: "/selection/review-board", enabled: true, tone: "good" },
    { key: "transcript", title: "Transcript editor", description: "Open the recent/current source video editor.", href: transcriptHref, enabled: Boolean(recentSourceVideoId), tone: recentSourceVideoId ? "warn" : "muted" },
    { key: "final", title: "Final review", description: "Review the latest source video final output.", href: finalReviewHref, enabled: Boolean(recentSourceVideoId), tone: recentSourceVideoId ? "warn" : "muted" },
    { key: "publish", title: "Publish drafts", description: "Prepare caption, CTA, hashtags, and publish state.", href: publishHref, enabled: Boolean(readyDraftSourceVideoId || recentSourceVideoId), tone: "warn" },
    { key: "optimization", title: "Optimization", description: "Review outcome and routing hints.", href: "/optimization", enabled: true, tone: "good" },
    { key: "ops", title: "Ops Console", description: "Open publish health, publish control, reconciliation, and system tools.", href: "/ops", enabled: true, tone: "muted" }
  ];
}

export function queueReadyCount(queue: PublishControlQueue | null): number {
  if (!queue) return 0;
  return queue.unassigned_drafts.length + queue.assigned_drafts.length + queue.scheduled_drafts.length;
}

export function firstReadyDraftSourceVideoId(queue: PublishControlQueue | null, health: PublishHealthDashboard | null): string | null {
  const queueItem: PublishQueueItem | undefined = queue?.assigned_drafts[0] ?? queue?.unassigned_drafts[0] ?? queue?.scheduled_drafts[0];
  if (queueItem?.source_video_id) return queueItem.source_video_id;
  return health?.action_queue.drafts_ready[0]?.source_video_id ?? null;
}

export function formatToken(value: string): string {
  return value.toLowerCase().replaceAll("_", " ");
}

function publicationActivity(item: PublicationOutcomeItem, label: string, tone: RecentActivityItem["tone"]): RecentActivityItem {
  return {
    key: `publication-${label}-${item.publish_draft_id}`,
    title: label,
    detail: item.external_permalink ?? `${item.platform} / ${humanizeStatus(item.status)}`,
    at: item.published_at ?? item.last_publish_synced_at,
    href: label === "Needs reconciliation" ? "/ops/reconciliation" : `/publishing/drafts/${item.publish_draft_id}`,
    tone
  };
}

export function buildContinueItems({
  recentSourceVideoId,
  readyDraftId,
  reconciliationDraftId
}: {
  recentSourceVideoId: string | null;
  readyDraftId: string | null;
  reconciliationDraftId: string | null;
}): ContinueItem[] {
  const items: ContinueItem[] = [];
  if (recentSourceVideoId) {
    items.push({
      key: "continue-transcript",
      title: "Continue source video",
      description: "Jump back into transcript editing for the latest active source video.",
      href: `/production/transcript-editor/${recentSourceVideoId}`,
      tone: "warn"
    });
    items.push({
      key: "continue-final-review",
      title: "Check final output",
      description: "Open final review for the same source video.",
      href: `/production/final-review/${recentSourceVideoId}`,
      tone: "warn"
    });
  }
  if (readyDraftId) {
    items.push({
      key: "continue-draft",
      title: "Continue publish draft",
      description: "Open the latest ready draft directly.",
      href: `/publishing/drafts/${readyDraftId}`,
      tone: "good"
    });
  }
  if (reconciliationDraftId) {
    items.push({
      key: "continue-reconcile",
      title: "Resolve publish uncertainty",
      description: "Open reconciliation queue for the latest uncertain publish attempt.",
      href: "/ops/reconciliation",
      tone: "danger"
    });
  }
  return items.slice(0, 4);
}

export function firstReadyDraftId(queue: PublishControlQueue | null, health: PublishHealthDashboard | null): string | null {
  const queueItem: PublishQueueItem | undefined = queue?.assigned_drafts[0] ?? queue?.unassigned_drafts[0] ?? queue?.scheduled_drafts[0];
  if (queueItem?.publish_draft_id) return queueItem.publish_draft_id;
  return health?.action_queue.drafts_ready[0]?.publish_draft_id ?? null;
}

export function firstReconciliationDraftId(health: PublishHealthDashboard | null): string | null {
  return health?.action_queue.needs_reconciliation[0]?.publish_draft_id ?? null;
}
