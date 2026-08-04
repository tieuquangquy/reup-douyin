import type { CaptureInboxActionResponse } from "../types/capture-inbox";

export const CAPTURE_INBOX_REVIEW_BOARD_HREF = "/selection/review-board";

export type PromoteSuccessSummary = {
  message: string;
  candidateCount: number;
  promotedCount: number;
};

export function buildPromoteSuccessSummary(
  response: Pick<CaptureInboxActionResponse, "message" | "affected_item_ids" | "candidate_created_count">
): PromoteSuccessSummary {
  return {
    message: response.message,
    candidateCount: Math.max(0, response.candidate_created_count),
    promotedCount: response.affected_item_ids.length
  };
}

/**
 * Review Board scoped to one Capture Inbox batch. The batch link is exact where a date
 * filter is not: re-pushing a clip the board already holds updates it instead of creating
 * it, so its creation date still points at the original intake.
 */
export function reviewBoardHrefForCaptureSession(captureSessionId: string | null | undefined): string {
  const sessionId = captureSessionId?.trim();
  if (!sessionId) return CAPTURE_INBOX_REVIEW_BOARD_HREF;
  return `${CAPTURE_INBOX_REVIEW_BOARD_HREF}?capture_session=${encodeURIComponent(sessionId)}`;
}

export function promoteSuccessFollowUpLabel(summary: PromoteSuccessSummary): string | null {
  if (summary.candidateCount <= 0) return null;
  const noun = summary.candidateCount === 1 ? "candidate" : "candidates";
  return `Open Review Board (${summary.candidateCount} new ${noun})`;
}
