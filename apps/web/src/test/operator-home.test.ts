import assert from "node:assert/strict";
import {
  buildActionQueue,
  buildContinueItems,
  buildOperatorMetrics,
  buildQuickLaunchItems,
  candidatesWaitingReview,
  firstReadyDraftId,
  firstReadyDraftSourceVideoId,
  firstReconciliationDraftId,
  pickRecentSourceVideoId
} from "../lib/operatorHomeState";
import type { PublishHealthDashboard } from "../types/analytics";
import type { Job } from "../types/jobs";
import type { PublishControlQueue } from "../types/publish-control";
import type { Candidate } from "../types/review-board";

const candidates = [
  { id: "candidate-1", source_video_id: "video-1", status: "SHORTLISTED", updated_at: "2026-04-21T00:00:00Z", source_video: null },
  { id: "candidate-2", source_video_id: "video-2", status: "APPROVED", updated_at: "2026-04-21T00:01:00Z", source_video: null }
] as unknown as Candidate[];

const jobs = [
  { id: "job-1", job_type: "RENDER_FINAL", status: "RUNNING", updated_at: "2026-04-21T00:02:00Z", completed_steps: 1, total_steps: 3, error_code: null, error_message: null },
  { id: "job-2", job_type: "PUBLISH_CONTENT", status: "FAILED", updated_at: "2026-04-21T00:03:00Z", completed_steps: 0, total_steps: 3, error_code: "publish_failed", error_message: "Failed" }
] as unknown as Job[];

const health = {
  overview: {
    drafts_ready_not_published: 2,
    needs_reconciliation_attempts: 1,
    drafts_blocked_by_risk: 1
  },
  action_queue: {
    needs_reconciliation: [{ source_video_id: "video-3", publish_draft_id: "draft-3" }],
    drafts_ready: [{ source_video_id: "video-4", publish_draft_id: "draft-4" }],
    recent_successes: []
  }
} as unknown as PublishHealthDashboard;

const queue = {
  unassigned_drafts: [],
  assigned_drafts: [{ source_video_id: "video-5", publish_draft_id: "draft-5" }],
  scheduled_drafts: [],
  needs_attention: []
} as unknown as PublishControlQueue;

assert.equal(candidatesWaitingReview(candidates).length, 1);
assert.equal(pickRecentSourceVideoId(candidates, queue), "video-5");
assert.equal(firstReadyDraftSourceVideoId(null, health), "video-4");
assert.equal(firstReadyDraftId(queue, health), "draft-5");
assert.equal(firstReconciliationDraftId(health), "draft-3");

const metrics = buildOperatorMetrics({ candidates, jobs, health, queue });
assert.equal(metrics.find((item) => item.key === "candidates_waiting")?.value, "1");
assert.equal(metrics.find((item) => item.key === "jobs_running")?.value, "1");
assert.equal(metrics.find((item) => item.key === "failed_or_reconcile")?.value, "2");

const actionQueue = buildActionQueue({ candidates, health, queue, recentSourceVideoId: "video-5" });
assert.equal(actionQueue.find((item) => item.key === "transcript_edits_needed")?.href, "/production/transcript-editor/video-5");
assert.equal(actionQueue.find((item) => item.key === "blocked_by_risk")?.count, 1);
assert.equal(actionQueue.find((item) => item.key === "blocked_by_risk")?.href, "/ops/risk");
assert.equal(actionQueue.find((item) => item.key === "publish_reconciliation_needed")?.href, "/ops/reconciliation");

const quickLaunch = buildQuickLaunchItems({ recentSourceVideoId: "video-5", readyDraftSourceVideoId: "video-4", readyDraftId: "draft-4" });
assert.equal(quickLaunch.find((item) => item.key === "intake")?.href, "/intake");
assert.equal(quickLaunch.find((item) => item.key === "publish")?.href, "/publishing/drafts/draft-4");
assert.equal(quickLaunch.some((item) => item.key === "health" || item.key === "control"), false);
assert.equal(quickLaunch.find((item) => item.key === "ops")?.href, "/ops");

const continueItems = buildContinueItems({ recentSourceVideoId: "video-5", readyDraftId: "draft-4", reconciliationDraftId: "draft-3" });
assert.equal(continueItems.find((item) => item.key === "continue-draft")?.href, "/publishing/drafts/draft-4");

console.log("operator-home state tests passed");
