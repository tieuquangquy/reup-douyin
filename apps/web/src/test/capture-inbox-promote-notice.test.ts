import assert from "node:assert/strict";

import {
  buildPromoteSuccessSummary,
  CAPTURE_INBOX_REVIEW_BOARD_HREF,
  promoteSuccessFollowUpLabel
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

console.log("capture-inbox-promote-notice tests passed");
