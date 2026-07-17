import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import {
  approvedCandidatesFromIds,
  applyQueuedMembershipToCandidates,
  candidatesPendingApproval,
  formatApproveAndEnqueueNotice,
  formatReupQueueEnqueueNotice,
  isApprovedForReupQueue,
  isCandidateInReupQueue,
  selectableBoardCandidates
} from "../lib/reviewBoardQueueState";
import type { Candidate } from "../types/review-board";

const approved = makeCandidate("a", "APPROVED");
const shortlisted = makeCandidate("b", "SHORTLISTED");
const approvedViaDecision = makeCandidate("c", "SHORTLISTED", "APPROVED");
const queued = makeCandidate("q", "APPROVED", undefined, true);

assert.equal(isApprovedForReupQueue(approved), true);
assert.equal(isApprovedForReupQueue(shortlisted), false);
assert.equal(isApprovedForReupQueue(approvedViaDecision), true);
assert.equal(isCandidateInReupQueue(queued), true);

assert.deepEqual(approvedCandidatesFromIds([approved, shortlisted, approvedViaDecision, queued], ["a", "b", "c", "q", "missing"]), ["a", "c"]);
assert.deepEqual(selectableBoardCandidates([approved, queued]), [approved]);
assert.equal(isCandidateInReupQueue(makeCandidate("x", "APPROVED", undefined, true, "CANCELLED")), false);
assert.equal(isCandidateInReupQueue(makeCandidate("y", "APPROVED", undefined, true, "READY_FOR_PROCESSING")), true);
assert.deepEqual(
  applyQueuedMembershipToCandidates([approved], ["a"], [{ id: "item-1", video_candidate_id: "a", status: "READY_FOR_PROCESSING" } as never])[0].in_reup_queue,
  true
);
assert.equal(
  applyQueuedMembershipToCandidates([approved], ["a"], [{ id: "item-1", video_candidate_id: "a", status: "CANCELLED" } as never])[0].in_reup_queue,
  false
);

assert.match(
  formatReupQueueEnqueueNotice({
    requested_count: 3,
    queued_count: 2,
    already_queued_count: 1,
    skipped_count: 0,
    items: [],
    skipped_candidate_ids: []
  }),
  /2 sent to Reup Queue/
);
assert.match(
  formatReupQueueEnqueueNotice({
    requested_count: 2,
    queued_count: 0,
    already_queued_count: 1,
    skipped_count: 1,
    items: [],
    skipped_candidate_ids: ["x"]
  }),
  /already in queue/
);

assert.deepEqual(candidatesPendingApproval([approved, shortlisted, approvedViaDecision, queued], ["a", "b", "c", "q"]), ["b"]);

assert.match(
  formatApproveAndEnqueueNotice(2, {
    requested_count: 2,
    queued_count: 2,
    already_queued_count: 0,
    skipped_count: 0,
    items: [],
    skipped_candidate_ids: []
  }),
  /2 approved/
);

const testDir = dirname(fileURLToPath(import.meta.url));
const reviewPageSource = readFileSync(resolve(testDir, "../components/review-board/ReviewBoardPage.tsx"), "utf8");
const reviewTileActionsSource = readFileSync(resolve(testDir, "../components/review-board/ReviewBoardTileActions.tsx"), "utf8");
const reviewBoardSource = reviewPageSource + reviewTileActionsSource;

assert.match(reviewPageSource, /enqueueReupCandidates/, "Review Board must call enqueue API");
assert.match(reviewBoardSource, /Send to queue/, "Review Board must expose Send to queue action");
assert.match(reviewBoardSource, /Approve & send/, "Review Board must expose Approve and send combined action");
assert.match(reviewPageSource, /approveAndSendCandidatesToReupQueue/, "Review Board must combine approve and enqueue");
assert.match(reviewPageSource, /candidatesPendingApproval/, "Review Board must detect candidates needing approval before queue");
assert.match(reviewPageSource, /approvedCandidatesFromIds/, "Review Board must guard queue send to approved candidates");
assert.match(reviewBoardSource, /\/selection\/reup-queue/, "Review Board header must link to Reup Queue");
assert.match(reviewPageSource, /async function bulkApproveSelected\(\) \{[\s\S]*?await updateCandidateStatuses\(bulkSelectedIds, "APPROVED"\)/, "Bulk approve must only update candidate status");
assert.match(reviewPageSource, /isCandidateInReupQueue/, "Review Board must detect candidates already in Reup Queue");
assert.match(reviewPageSource, /In queue/, "Review Board must show in-queue badge");
assert.match(reviewPageSource, /applyQueuedMembershipToCandidates/, "Review Board must mark local queue membership after enqueue");
assert.match(reviewPageSource, /selectableBoardCandidates/, "Review Board must exclude queued tiles from bulk selection");

console.log("review-board-queue tests passed");

function makeCandidate(id: string, status: Candidate["status"], decisionStatus?: Candidate["decision_status"], inReupQueue = false, reupQueueStatus?: string): Candidate {
  return {
    id,
    source_video_id: `video-${id}`,
    status,
    decision_status: decisionStatus,
    in_reup_queue: inReupQueue,
    reup_queue_status: reupQueueStatus as Candidate["reup_queue_status"],
    score: 50,
    reup_score: 50,
    estimated_views_mid: 1000,
    score_version: "REUP_SCORE_V1",
    score_label: "usable",
    score_breakdown_json: null,
    score_reason: null,
    preset_name: "viral_discovery",
    filter_config_json: {},
    inclusion_reasons_json: [],
    exclusion_reasons_json: [],
    warnings_json: [],
    evaluated_at: "2026-04-01T00:00:00Z",
    priority: 50,
    metadata_json: {},
    created_at: "2026-04-01T00:00:00Z",
    updated_at: "2026-04-01T00:00:00Z",
    source_video: null
  };
}
