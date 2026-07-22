import type { ReupQueueEnqueueResponse, ReupQueueItem } from "../types/reup-queue";
import type { Candidate } from "../types/review-board";

const ACTIVE_REUP_QUEUE_STATUSES = new Set([
  "READY_FOR_PROCESSING",
  "WAITING_FOR_MEDIA",
  "WAITING_FOR_METADATA",
  "PROCESSING",
  "READY_TO_EXPORT",
  "EXPORT_PACKAGE_CREATED",
  "READY_TO_PUBLISH",
  "PUBLISH_HANDOFF_CREATED",
  "FAILED_NEEDS_ATTENTION"
]);

export function isActiveReupQueueStatus(status: string | null | undefined): boolean {
  return status != null && ACTIVE_REUP_QUEUE_STATUSES.has(status);
}

export function isCandidateInReupQueue(candidate: Candidate): boolean {
  if (candidate.in_reup_queue !== true) return false;
  if (candidate.reup_queue_status && !isActiveReupQueueStatus(candidate.reup_queue_status)) return false;
  return true;
}

export function isApprovedForReupQueue(candidate: Candidate): boolean {
  return candidate.status === "APPROVED" || candidate.decision_status === "APPROVED";
}

export type ReviewBoardDetailsActionVisibility = {
  approvedForQueue: boolean;
  inReupQueue: boolean;
  showApproveOnly: boolean;
  showLater: boolean;
  showReject: boolean;
};

/** Stage-aware Review Board tile/details companions — drop no-op Later/Reject. */
export function reviewBoardDetailsActionVisibility(candidate: {
  status: Candidate["status"];
  decision_status?: Candidate["decision_status"];
  in_reup_queue?: boolean | null;
  reup_queue_status?: string | null;
}): ReviewBoardDetailsActionVisibility {
  const inReupQueue = isCandidateInReupQueue(candidate as Candidate);
  const approvedForQueue = isApprovedForReupQueue(candidate as Candidate);
  if (inReupQueue) {
    return {
      approvedForQueue,
      inReupQueue: true,
      showApproveOnly: false,
      showLater: false,
      showReject: false
    };
  }
  const rejected = candidate.status === "REJECTED" || candidate.decision_status === "REJECTED";
  const inReview = candidate.status === "IN_REVIEW" || candidate.decision_status === "IN_REVIEW";
  return {
    approvedForQueue,
    inReupQueue: false,
    showApproveOnly: !approvedForQueue,
    showLater: !rejected && !inReview,
    showReject: !rejected
  };
}

export function approvedCandidatesFromIds(pool: Candidate[], ids: string[]): string[] {
  const byId = new Map(pool.map((candidate) => [candidate.id, candidate]));
  return ids.filter((id) => {
    const candidate = byId.get(id);
    return candidate ? isApprovedForReupQueue(candidate) && !isCandidateInReupQueue(candidate) : false;
  });
}

export function candidatesPendingApproval(pool: Candidate[], ids: string[]): string[] {
  const byId = new Map(pool.map((candidate) => [candidate.id, candidate]));
  return ids.filter((id) => {
    const candidate = byId.get(id);
    return candidate ? !isApprovedForReupQueue(candidate) && !isCandidateInReupQueue(candidate) : false;
  });
}

export function selectableBoardCandidates(candidates: Candidate[]): Candidate[] {
  return candidates.filter((candidate) => !isCandidateInReupQueue(candidate));
}

export function applyQueuedMembershipToCandidates(
  candidates: Candidate[],
  candidateIds: string[],
  items: ReupQueueItem[] = []
): Candidate[] {
  if (candidateIds.length === 0) return candidates;
  const queuedIds = new Set(candidateIds);
  const itemsByCandidateId = new Map(items.map((item) => [item.video_candidate_id, item]));
  return candidates.map((candidate) => {
    if (!queuedIds.has(candidate.id) && !itemsByCandidateId.has(candidate.id)) return candidate;
    const item = itemsByCandidateId.get(candidate.id);
    const active = item ? isActiveReupQueueStatus(item.status) : true;
    return {
      ...candidate,
      in_reup_queue: active,
      reup_queue_item_id: item?.id ?? candidate.reup_queue_item_id ?? null,
      reup_queue_status: item?.status ?? candidate.reup_queue_status ?? null
    };
  });
}

export function formatReupQueueEnqueueNotice(result: ReupQueueEnqueueResponse): string {
  const parts: string[] = [];
  if (result.queued_count > 0) {
    parts.push(`${result.queued_count} sent to Reup Queue`);
  }
  if (result.already_queued_count > 0) {
    parts.push(`${result.already_queued_count} already in queue`);
  }
  if (result.skipped_count > 0) {
    parts.push(`${result.skipped_count} skipped (not approved)`);
  }
  if (parts.length === 0) return "No candidates were sent to Reup Queue.";
  return parts.join(" · ");
}

export function formatApproveAndEnqueueNotice(newlyApprovedCount: number, result: ReupQueueEnqueueResponse): string {
  const parts: string[] = [];
  if (newlyApprovedCount > 0) {
    parts.push(`${newlyApprovedCount} approved`);
  }
  parts.push(formatReupQueueEnqueueNotice(result));
  return parts.join(" · ");
}
