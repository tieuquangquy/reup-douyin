import type { PublishHealthDashboard, PublicationOutcomeItem } from "../types/analytics";
import type { DouyinExtensionStatusResponse } from "../types/douyin-extension-setup";
import type { Job } from "../types/jobs";
import type {
  PipelineDashboardAttentionItem,
  PipelineDashboardResponse,
  PipelineDashboardStage,
  PipelineDashboardStatus,
  PipelineStageKey
} from "../types/operations";
import type { PublishControlQueue, PublishQueueItem } from "../types/publish-control";
import type { Candidate } from "../types/review-board";
import { operatorSafeHref } from "./opsConsoleBoundary";
import { humanizeStatus } from "./statusLabels";

export { isOpsConsoleHref } from "./opsConsoleBoundary";

export type OperatorHomeTone = "good" | "warn" | "danger" | "muted";

export type OperatorMetric = {
  key: string;
  label: string;
  value: string;
  detail: string;
  tone: OperatorHomeTone;
  href?: string;
};

export type OperatorActionItem = {
  key: string;
  title: string;
  count: number;
  description: string;
  href: string;
  tone: OperatorHomeTone;
  cta: string;
};

export type RecentActivityItem = {
  key: string;
  title: string;
  detail: string;
  at: string | null;
  href: string;
  tone: OperatorHomeTone;
};

export type QuickLaunchItem = {
  key: string;
  title: string;
  description: string;
  href: string;
  enabled: boolean;
  tone: OperatorHomeTone;
};

export type ContinueItem = {
  key: string;
  title: string;
  description: string;
  href: string;
  tone: OperatorHomeTone;
};

export type OperatorNextWorkItem = {
  key: string;
  title: string;
  detail: string;
  count: number;
  href: string;
  stageKey: PipelineStageKey;
  severity: PipelineDashboardAttentionItem["severity"];
  tone: OperatorHomeTone;
  cta: string;
};

export type OperatorExtensionSignal = {
  label: string;
  detail: string;
  href: string;
  tone: OperatorHomeTone;
};

export type OperatorFreshness = {
  generatedAt: string | null;
  overallStatus: PipelineDashboardStatus | null;
  headline: string | null;
  pipelineHref: string;
};

const NEXT_WORK_LIMIT = 3;
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

export function pipelineStage(
  pipeline: PipelineDashboardResponse | null | undefined,
  key: PipelineStageKey
): PipelineDashboardStage | null {
  return pipeline?.stages.find((stage) => stage.key === key) ?? null;
}

export function buildFreshness(pipeline: PipelineDashboardResponse | null | undefined): OperatorFreshness {
  return {
    generatedAt: pipeline?.generated_at ?? null,
    overallStatus: pipeline?.overall_status ?? null,
    headline: pipeline?.headline ?? null,
    pipelineHref: "/ops/pipeline"
  };
}

export function buildOperatorMetrics({
  candidates,
  jobs,
  health,
  queue,
  pipeline
}: {
  candidates: Candidate[];
  jobs: Job[];
  health: PublishHealthDashboard | null;
  queue: PublishControlQueue | null;
  pipeline?: PipelineDashboardResponse | null;
}): OperatorMetric[] {
  const capture = pipelineStage(pipeline, "capture");
  const review = pipelineStage(pipeline, "review");
  const reup = pipelineStage(pipeline, "reup_queue");
  const exportStage = pipelineStage(pipeline, "export_package");
  const handoff = pipelineStage(pipeline, "publish_handoff");

  const captureWaiting = capture?.primary_count ?? 0;
  const reviewWaiting = review?.primary_count ?? candidatesWaitingReview(candidates).length;
  const reupActive = reup?.primary_count ?? 0;
  const readyDrafts = health?.overview.drafts_ready_not_published ?? queueReadyCount(queue);
  const exportHandoff = (exportStage?.primary_count ?? 0) + (handoff?.primary_count ?? 0);

  const failedOrRetryable = jobs.filter((job) => job.status === "FAILED" || job.status === "RETRYABLE").length;
  const reconciliation = health?.overview.needs_reconciliation_attempts ?? 0;
  const blockedByRisk = health?.overview.drafts_blocked_by_risk ?? 0;
  const blockers = failedOrRetryable + reconciliation + blockedByRisk;

  return [
    {
      key: "capture_waiting",
      label: "Capture waiting",
      value: String(captureWaiting),
      detail: capture
        ? `${capture.primary_label}; ${capture.secondary_count} ${capture.secondary_label.toLowerCase()}`
        : "Open Capture Inbox to stage Douyin items.",
      tone: captureWaiting > 0 ? "warn" : "good",
      href: operatorSafeHref(capture?.href, "/selection/capture-inbox")
    },
    {
      key: "review_waiting",
      label: "Review waiting",
      value: String(reviewWaiting),
      detail: reviewWaiting > 0 ? "Open the review board first." : "No candidate backlog in the current view.",
      tone: reviewWaiting > 0 ? "warn" : "good",
      href: operatorSafeHref(review?.href, "/selection/review-board")
    },
    {
      key: "reup_queue",
      label: "Reup queue",
      value: String(reupActive),
      detail: reup
        ? `${reup.primary_label}; ${reup.secondary_count} ${reup.secondary_label.toLowerCase()}`
        : "Active reup queue depth.",
      tone: reup?.status === "blocked" ? "danger" : reupActive > 0 ? "warn" : "muted",
      href: operatorSafeHref(reup?.href, "/selection/reup-queue")
    },
    {
      key: "ready_drafts",
      label: "Publish drafts ready",
      value: String(readyDrafts),
      detail: "Ready drafts waiting for assignment or publish.",
      tone: readyDrafts > 0 ? "warn" : "good",
      href: "/publishing/drafts"
    },
    {
      key: "export_handoff",
      label: "Export / handoff ready",
      value: String(exportHandoff),
      detail: "Packages or handoffs ready for downstream work.",
      tone: exportHandoff > 0 ? "warn" : "muted",
      href: (exportStage?.primary_count ?? 0) > 0
        ? (exportStage?.href ?? "/publishing/export-packages")
        : (handoff?.href ?? "/publishing/publish-handoffs")
    },
    {
      key: "blockers",
      label: "Blockers",
      value: String(blockers),
      detail: `${blockedByRisk} risk · ${failedOrRetryable} jobs · ${reconciliation} reconcile`,
      tone: blockers > 0 ? "danger" : "good"
    }
  ];
}

export function buildNextWork(pipeline: PipelineDashboardResponse | null | undefined): OperatorNextWorkItem[] {
  if (!pipeline) return [];
  return [...pipeline.attention_items]
    .filter((item) => item.severity === "critical" || item.severity === "warning")
    .sort((a, b) => severityRank(a.severity) - severityRank(b.severity))
    .slice(0, NEXT_WORK_LIMIT)
    .map((item) => ({
      key: item.id,
      title: item.title,
      detail: item.detail,
      count: item.count,
      href: operatorSafeHref(item.href, operatorFallbackForStage(item.stage_key)),
      stageKey: item.stage_key,
      severity: item.severity,
      tone: toneForSeverity(item.severity),
      cta: item.recommended_action
    }));
}

function operatorFallbackForStage(stageKey: PipelineStageKey): string {
  if (stageKey === "capture") return "/selection/capture-inbox";
  if (stageKey === "review") return "/selection/review-board";
  if (stageKey === "reup_queue") return "/selection/reup-queue";
  if (stageKey === "export_package") return "/publishing/export-packages";
  if (stageKey === "publish_handoff") return "/publishing/publish-handoffs";
  return "/publishing/drafts";
}

export function buildPublishSuccessMetric(health: PublishHealthDashboard | null): OperatorMetric {
  const succeeded = health?.overview.succeeded_attempts ?? 0;
  const rate = health?.overview.success_rate_percent;
  return {
    key: "publish_success",
    label: "Publish success (7d)",
    value: String(succeeded),
    detail: rate != null ? `${rate}% success rate in current window` : "Succeeded publish attempts in current window",
    tone: succeeded > 0 ? "good" : "muted"
  };
}

export function buildExtensionSignal(extension: DouyinExtensionStatusResponse | null | undefined): OperatorExtensionSignal {
  if (!extension) {
    return {
      label: "Extension unknown",
      detail: "Could not load Douyin extension status.",
      href: "/setup/douyin-extension",
      tone: "muted"
    };
  }
  if (extension.status === "connected" && extension.compatible) {
    return {
      label: "Extension connected",
      detail: extension.operator_message || extension.recommended_next_action_label,
      href: "/setup/douyin-extension",
      tone: "good"
    };
  }
  if (extension.status === "version_mismatch" || extension.status === "backend_unreachable_from_extension") {
    return {
      label: "Extension needs fix",
      detail: extension.operator_message || extension.recommended_next_action_label,
      href: "/setup/douyin-extension",
      tone: "danger"
    };
  }
  return {
    label: "Extension setup",
    detail: extension.operator_message || extension.recommended_next_action_label,
    href: "/setup/douyin-extension",
    tone: "warn"
  };
}

function severityRank(severity: PipelineDashboardAttentionItem["severity"]): number {
  if (severity === "critical") return 0;
  if (severity === "warning") return 1;
  return 2;
}

function toneForSeverity(severity: PipelineDashboardAttentionItem["severity"]): OperatorHomeTone {
  if (severity === "critical") return "danger";
  if (severity === "warning") return "warn";
  return "muted";
}

export function toneForPipelineStatus(status: PipelineDashboardStatus | null | undefined): OperatorHomeTone {
  if (status === "blocked") return "danger";
  if (status === "needs_attention") return "warn";
  if (status === "healthy" || status === "in_progress") return "good";
  return "muted";
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
      href: "/publishing/drafts",
      tone: blockedByRisk > 0 ? "danger" : "good",
      cta: blockedByRisk > 0 ? "Review drafts" : "No risk block"
    },
    {
      key: "publish_reconciliation_needed",
      title: "Publish reconciliation needed",
      count: reconcileNeeded,
      description: "Publish attempts with uncertain platform status.",
      href: reconcileDraftId ? `/publishing/drafts/${reconcileDraftId}` : "/publishing/drafts",
      tone: reconcileNeeded > 0 ? "danger" : "good",
      cta: reconcileNeeded > 0 ? "Open draft" : "Reconciliation clear"
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
    href: "/ops/pipeline",
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
    { key: "optimization", title: "Optimization", description: "Review outcome and routing hints.", href: "/optimization", enabled: true, tone: "good" }
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
    href: `/publishing/drafts/${item.publish_draft_id}`,
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
      description: "Open the draft that needs publish status confirmation.",
      href: `/publishing/drafts/${reconciliationDraftId}`,
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
