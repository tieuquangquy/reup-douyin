import assert from "node:assert/strict";

import {
  buildPromoteSuccessSummary,
  CAPTURE_INBOX_REVIEW_BOARD_HREF,
  promoteSuccessFollowUpLabel,
  reviewBoardHrefForCaptureSession
} from "../lib/captureInboxPromoteNotice";

const summary = buildPromoteSuccessSummary({
  message: "Promoted 3 Capture Inbox item(s).",
  affected_item_ids: ["a", "b", "c"],
  candidate_created_count: 3
});
assert.equal(summary.promotedCount, 3);
assert.equal(summary.candidateCount, 3);
assert.equal(promoteSuccessFollowUpLabel(summary), "Open Review Board (3 new candidates)");
assert.equal(CAPTURE_INBOX_REVIEW_BOARD_HREF, "/selection/review-board");

const noCandidates = buildPromoteSuccessSummary({
  message: "No new candidates.",
  affected_item_ids: [],
  candidate_created_count: 0
});
assert.equal(promoteSuccessFollowUpLabel(noCandidates), null);

// After promoting, the operator should land on a board already scoped to that batch
// instead of hunting for the clips they just pushed.
assert.equal(
  reviewBoardHrefForCaptureSession("6b0f0b0e-0000-4000-8000-000000000001"),
  "/selection/review-board?capture_session=6b0f0b0e-0000-4000-8000-000000000001"
);
assert.equal(
  reviewBoardHrefForCaptureSession("a b&c"),
  "/selection/review-board?capture_session=a%20b%26c",
  "Session ids must be URL-encoded"
);
assert.equal(
  reviewBoardHrefForCaptureSession(""),
  CAPTURE_INBOX_REVIEW_BOARD_HREF,
  "Without a session the link falls back to the unfiltered board"
);
assert.equal(reviewBoardHrefForCaptureSession(null), CAPTURE_INBOX_REVIEW_BOARD_HREF);

console.log("capture-inbox-promote-notice tests passed");
