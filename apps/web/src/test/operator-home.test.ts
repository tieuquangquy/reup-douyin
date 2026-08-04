import assert from "node:assert/strict";
import {
  buildActionQueue,
  buildContinueItems,
  buildExtensionSignal,
  buildFreshness,
  buildNextWork,
  buildOperatorMetrics,
  buildPublishSuccessMetric,
  buildQuickLaunchItems,
  candidatesWaitingReview,
  firstReadyDraftId,
  firstReadyDraftSourceVideoId,
  firstReconciliationDraftId,
  isOpsConsoleHref,
  pickRecentSourceVideoId
} from "../lib/operatorHomeState";
import type { PublishHealthDashboard } from "../types/analytics";
import type { DouyinExtensionStatusResponse } from "../types/douyin-extension-setup";
import type { Job } from "../types/jobs";
import type { PipelineDashboardResponse } from "../types/operations";
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
    drafts_blocked_by_risk: 1,
    succeeded_attempts: 7,
    success_rate_percent: 70
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

const pipeline = {
  generated_at: "2026-04-21T00:10:00Z",
  overall_status: "needs_attention",
  headline: "Capture and reup need operator attention.",
  stages: [
    {
      key: "capture",
      label: "Capture",
      primary_count: 4,
      primary_label: "Ready items",
      secondary_count: 1,
      secondary_label: "Sessions 24h",
      status: "needs_attention",
      href: "/selection/capture-inbox",
      attention_count: 5,
      metrics: [{ key: "failed", label: "Failed", value: 1, detail: null }],
      description: "",
      next_action: ""
    },
    {
      key: "review",
      label: "Review",
      primary_count: 3,
      primary_label: "Backlog",
      secondary_count: 0,
      secondary_label: "",
      status: "needs_attention",
      href: "/selection/review-board",
      attention_count: 3,
      metrics: [],
      description: "",
      next_action: ""
    },
    {
      key: "reup_queue",
      label: "Reup queue",
      primary_count: 6,
      primary_label: "Active",
      secondary_count: 2,
      secondary_label: "Waiting",
      status: "in_progress",
      href: "/selection/reup-queue",
      attention_count: 2,
      metrics: [],
      description: "",
      next_action: ""
    },
    {
      key: "export_package",
      label: "Export",
      primary_count: 2,
      primary_label: "Ready",
      secondary_count: 0,
      secondary_label: "",
      status: "needs_attention",
      href: "/publishing/export-packages",
      attention_count: 2,
      metrics: [],
      description: "",
      next_action: ""
    },
    {
      key: "publish_handoff",
      label: "Handoff",
      primary_count: 1,
      primary_label: "Ready",
      secondary_count: 0,
      secondary_label: "",
      status: "needs_attention",
      href: "/publishing/publish-handoffs",
      attention_count: 1,
      metrics: [],
      description: "",
      next_action: ""
    }
  ],
  attention_items: [
    {
      id: "a1",
      severity: "critical",
      stage_key: "capture",
      title: "Capture failures",
      detail: "1 failed",
      count: 1,
      href: "/selection/capture-inbox",
      recommended_action: "Inspect failures"
    },
    {
      id: "a2",
      severity: "warning",
      stage_key: "reup_queue",
      title: "Queue waiting work",
      detail: "2 waiting",
      count: 2,
      href: "/selection/reup-queue",
      recommended_action: "Confirm readiness"
    },
    {
      id: "a3",
      severity: "info",
      stage_key: "export_package",
      title: "Ready to export",
      detail: "info only",
      count: 2,
      href: "/publishing/export-packages",
      recommended_action: "Create package"
    }
  ]
} as unknown as PipelineDashboardResponse;

const extension = {
  status: "connected",
  connected: true,
  compatible: true,
  version_status: "compatible",
  operator_message: "Extension connected",
  recommended_next_action_label: "Open Douyin and capture"
} as unknown as DouyinExtensionStatusResponse;

assert.equal(candidatesWaitingReview(candidates).length, 1);
assert.equal(pickRecentSourceVideoId(candidates, queue), "video-5");
assert.equal(firstReadyDraftSourceVideoId(null, health), "video-4");
assert.equal(firstReadyDraftId(queue, health), "draft-5");
assert.equal(firstReconciliationDraftId(health), "draft-3");

const metrics = buildOperatorMetrics({ candidates, jobs, health, queue, pipeline });
assert.equal(metrics.find((item) => item.key === "capture_waiting")?.value, "4");
assert.equal(metrics.find((item) => item.key === "review_waiting")?.value, "3");
assert.equal(metrics.find((item) => item.key === "reup_queue")?.value, "6");
assert.equal(metrics.find((item) => item.key === "ready_drafts")?.value, "2");
assert.equal(metrics.find((item) => item.key === "export_handoff")?.value, "3");
assert.equal(metrics.find((item) => item.key === "blockers")?.value, "3");
assert.equal(metrics.find((item) => item.key === "blockers")?.href, undefined);
assert.equal(metrics.some((item) => item.key === "final_outputs_ready"), false);
assert.equal(metrics.some((item) => item.key === "jobs_running"), false);

const nextWork = buildNextWork(pipeline);
assert.equal(nextWork.length, 2);
assert.equal(nextWork[0]?.key, "a1");
assert.equal(nextWork[1]?.key, "a2");

const publishSuccess = buildPublishSuccessMetric(health);
assert.equal(publishSuccess.value, "7");
assert.equal(publishSuccess.href, undefined);

const extensionSignal = buildExtensionSignal(extension);
assert.equal(extensionSignal.tone, "good");
assert.match(extensionSignal.href, /douyin-extension/);

const actionQueue = buildActionQueue({ candidates, health, queue, recentSourceVideoId: "video-5" });
assert.equal(actionQueue.find((item) => item.key === "transcript_edits_needed")?.href, "/production/transcript-editor/video-5");
assert.equal(actionQueue.find((item) => item.key === "blocked_by_risk")?.count, 1);
assert.equal(actionQueue.find((item) => item.key === "blocked_by_risk")?.href, "/publishing/drafts");
assert.equal(actionQueue.find((item) => item.key === "publish_reconciliation_needed")?.href, "/publishing/drafts/draft-3");

const quickLaunch = buildQuickLaunchItems({ recentSourceVideoId: "video-5", readyDraftSourceVideoId: "video-4", readyDraftId: "draft-4" });
assert.equal(quickLaunch.find((item) => item.key === "intake")?.href, "/intake");
assert.equal(quickLaunch.find((item) => item.key === "publish")?.href, "/publishing/drafts/draft-4");
assert.equal(quickLaunch.some((item) => item.key === "health" || item.key === "control" || item.key === "ops"), false);

const continueItems = buildContinueItems({ recentSourceVideoId: "video-5", readyDraftId: "draft-4", reconciliationDraftId: "draft-3" });
assert.equal(continueItems.find((item) => item.key === "continue-draft")?.href, "/publishing/drafts/draft-4");
assert.equal(continueItems.find((item) => item.key === "continue-reconcile")?.href, "/publishing/drafts/draft-3");

const homeHrefs = [
  ...metrics.map((item) => item.href),
  ...actionQueue.map((item) => item.href),
  ...quickLaunch.map((item) => item.href),
  ...continueItems.map((item) => item.href),
  publishSuccess.href,
  extensionSignal.href,
  buildFreshness(pipeline).pipelineHref
].filter(Boolean) as string[];
for (const href of homeHrefs) {
  assert.equal(
    isOpsConsoleHref(href),
    false,
    `Operator home must not deep-link Ops Console surfaces (got ${href})`
  );
}

console.log("operator-home state tests passed");
