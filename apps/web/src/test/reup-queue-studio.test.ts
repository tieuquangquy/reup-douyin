import assert from "node:assert/strict";
import {
  buildPipelineStages,
  buildQueueTileSecondaryLinks,
  buildQuickPathHeroStats,
  buildReupQueueSummary,
  buildReupQueueSummaryFromStatusCounts,
  buildSelectionEligibility,
  bulkCancelConfirmMessage,
  bulkSelectionGuidance,
  cancellableReupQueueItems,
  capStartProcessingBatchIds,
  clearablePurgeReupQueueItems,
  dismissableReupQueueItems,
  downloadJobErrorLine,
  downloadJobProgressPercent,
  formatJobChipLabel,
  hasActiveDownloadJob,
  supportsBulkDismissVisibleScope,
  hasAnyBatchEligibility,
  matchesReupQueueFilter,
  pickInspectorSpotlightAction,
  primaryQueueAction,
  primaryQueueActionLabel,
  queueTileScoreBadge,
  queueTileViewsLabel,
  quickPathGuidance,
  quickPathSuggestedFilter,
  groupInspectorLifecycleActions,
  buildInspectorWorkflowLinks,
  formatBatchResultSummary,
  formatBulkBarScopeMeta,
  REUP_QUEUE_START_PROCESSING_BATCH_LIMIT,
  shouldShowQueueTileDetailsButton,
  startProcessingBatchCapNotice,
  statusesForReupQueueFilter,
  supportsBulkCancelVisibleScope,
  terminalQueueDismissAction,
  queueTilePrimaryButtonTone,
  queueTileShowsForwardArrow,
  compareReupQueueItems,
  queueStageLabel,
  REUP_QUEUE_SORT_LABELS,
  resolveInitialReupQueueFilter,
  selectableReupQueueItems,
  visibleReupQueueItems,
  worklistPrimaryActionLabel,
  worklistStageLabel,
  worklistStageTone,
  markMediaReadyNotice,
  linkedJobActivityLabel,
  shouldShowWorklistOpenJobLink,
  worklistTranscriptHref,
  worklistNoDialogueHint,
  isNoDialogueAnalyzeResult
} from "../lib/reupQueueStudioState";
import type { ReupQueueItem } from "../types/reup-queue";

const ready = makeItem("r1", "READY_FOR_PROCESSING");
const media = makeItem("m1", "WAITING_FOR_MEDIA");
const failed = makeItem("f1", "FAILED_NEEDS_ATTENTION");

assert.equal(matchesReupQueueFilter(ready, "needs_start"), true);
assert.equal(matchesReupQueueFilter(media, "in_production"), true);
assert.equal(matchesReupQueueFilter(failed, "attention"), true);

const summary = buildReupQueueSummary([ready, media, failed]);
assert.equal(summary.all, 3);
assert.equal(summary.needs_start, 1);
assert.equal(summary.in_production, 1);
assert.equal(summary.attention, 1);

assert.equal(queueStageLabel(ready), "Needs start");
assert.equal(primaryQueueAction(ready), "START_PROCESSING");
{
  const downloading = makeItem("dl1", "WAITING_FOR_MEDIA");
  downloading.job_id = "job-dl";
  downloading.job_status = "RUNNING";
  downloading.job_progress_percent = 42;
  downloading.available_actions = [
    { action: "HOLD", label: "Pause", description: "Pause", requires_note: false },
    { action: "MARK_MEDIA_READY", label: "Mark media ready", description: "Confirm", requires_note: false },
    { action: "CANCEL", label: "Cancel", description: "Cancel", requires_note: true }
  ];
  assert.equal(queueStageLabel(downloading), "Downloading");
  assert.equal(formatJobChipLabel(downloading), null, "running download must use one stage chip only");
  assert.equal(hasActiveDownloadJob(downloading), true);
  assert.equal(downloadJobProgressPercent(downloading), 42);
  assert.equal(downloadJobErrorLine(downloading), null);
  assert.equal(primaryQueueAction(downloading), "HOLD");
  assert.equal(primaryQueueActionLabel(downloading), "Pause");
  assert.equal(worklistStageLabel(downloading), "Downloading");
  assert.equal(worklistStageTone(downloading), "active");
}
{
  const paused = makeItem("pause1", "WAITING_FOR_MEDIA");
  paused.held_at = "2026-07-14T00:00:00Z";
  paused.job_id = "job-paused";
  paused.job_status = "CANCELLED";
  paused.available_actions = [
    { action: "RESUME", label: "Resume", description: "Resume", requires_note: false },
    { action: "CANCEL", label: "Cancel", description: "Cancel", requires_note: true }
  ];
  assert.equal(queueStageLabel(paused), "Paused");
  assert.equal(downloadJobProgressPercent(paused), null);
  assert.equal(primaryQueueAction(paused), "RESUME");
  assert.equal(primaryQueueActionLabel(paused), "Resume");
  assert.equal(worklistStageLabel(paused), "Paused");
  assert.equal(worklistStageTone(paused), "muted");
}
{
  const failedDownload = makeItem("df1", "FAILED_NEEDS_ATTENTION");
  failedDownload.job_id = "job-fail";
  failedDownload.job_status = "FAILED";
  failedDownload.job_error_code = "DOWNLOAD_VALIDATION_FAILED";
  failedDownload.job_error_message = "Asset content is empty";
  failedDownload.last_error_message = "Asset content is empty";
  assert.equal(queueStageLabel(failedDownload), "Download failed");
  assert.equal(formatJobChipLabel(failedDownload), null, "failed download must use one stage chip only");
  assert.match(downloadJobErrorLine(failedDownload) ?? "", /empty/i);
  assert.equal(hasActiveDownloadJob(failedDownload), false);
}
{
  const waitingDownload = makeItem("w1", "WAITING_FOR_MEDIA");
  waitingDownload.available_actions = [
    { action: "MARK_MEDIA_READY", label: "Mark media ready", description: "Confirm", requires_note: false }
  ];
  waitingDownload.job_status = "COMPLETED";
  waitingDownload.metadata_json = { download_job_completed: true };
  assert.equal(primaryQueueAction(waitingDownload), "MARK_MEDIA_READY");
  assert.equal(queueStageLabel(waitingDownload), "Confirm media ready");
  assert.equal(worklistStageLabel(waitingDownload), "Ready");
  assert.equal(worklistStageTone(waitingDownload), "good");
  assert.equal(primaryQueueActionLabel(waitingDownload), "Mark media ready");
  assert.equal(worklistPrimaryActionLabel(waitingDownload), "Mark media ready");
  assert.equal(
    worklistPrimaryActionLabel(waitingDownload),
    primaryQueueActionLabel(waitingDownload),
    "Worklist CTA labels must stay in sync with Gallery"
  );
  assert.equal(shouldShowQueueTileDetailsButton(waitingDownload), true);
  waitingDownload.job_id = "job-1";
  assert.equal(formatJobChipLabel(waitingDownload), null, "completed download must not duplicate Job completed chip");
}
{
  const analyzing = makeItem("a1", "WAITING_FOR_METADATA");
  analyzing.job_id = "110050de-71f2-483a-a67e-1bbd88393985";
  analyzing.job_type = "ANALYZE_AUDIO";
  analyzing.job_status = "RUNNING";
  assert.equal(worklistStageLabel(analyzing), "Analyzing");
  assert.equal(linkedJobActivityLabel(analyzing), "Analyzing");
  assert.equal(formatJobChipLabel(analyzing), "Analyzing");
  analyzing.job_status = "COMPLETED";
  analyzing.transcript_count = 2;
  analyzing.has_speech = true;
  analyzing.dialogue_phase = "source_auto_approved";
  assert.equal(worklistStageLabel(analyzing), "Analyzed");
  assert.equal(formatJobChipLabel(analyzing), "Audio analyzed");
  assert.match(markMediaReadyNotice(analyzing), /ANALYZE_AUDIO/);
  assert.match(markMediaReadyNotice(analyzing), /110050de/);
  assert.match(markMediaReadyNotice(analyzing), /Completed/i);
  assert.equal(
    worklistTranscriptHref(analyzing),
    `/production/transcript-editor/${analyzing.source_video_id}`,
    "Analyzed worklist rows must deep-link to Checkpoint #1 Transcript"
  );
  assert.equal(shouldShowWorklistOpenJobLink(analyzing), false, "Completed analyze should prefer Transcript over Open job");
  analyzing.job_status = "RUNNING";
  assert.equal(worklistTranscriptHref(analyzing), null);
  assert.equal(shouldShowWorklistOpenJobLink(analyzing), true);
}
{
  const silent = makeItem("silent1", "WAITING_FOR_METADATA");
  silent.job_id = "220050de-71f2-483a-a67e-1bbd88393985";
  silent.job_type = "ANALYZE_AUDIO";
  silent.job_status = "COMPLETED";
  silent.dialogue_phase = "no_dialogue";
  silent.has_speech = false;
  silent.transcript_count = 0;
  assert.equal(isNoDialogueAnalyzeResult(silent), true);
  assert.equal(worklistStageLabel(silent), "No dialogue");
  assert.equal(formatJobChipLabel(silent), "No dialogue");
  assert.equal(worklistTranscriptHref(silent), null, "No-dialogue rows must not open empty Transcript");
  assert.equal(worklistNoDialogueHint(silent), "Skip dubbing — caption/OCR later");
  assert.equal(worklistStageTone(silent), "muted");
}
assert.equal(REUP_QUEUE_START_PROCESSING_BATCH_LIMIT, 30);
{
  const ids = Array.from({ length: 35 }, (_, index) => `id-${index}`);
  const capped = capStartProcessingBatchIds(ids);
  assert.equal(capped.acceptedIds.length, 30);
  assert.equal(capped.overflowCount, 5);
  assert.deepEqual(capped.acceptedIds, ids.slice(0, 30));
  assert.match(startProcessingBatchCapNotice(30, 5, 30), /safe batch limit 30/i);
}
{
  const under = capStartProcessingBatchIds(["a", "b"]);
  assert.deepEqual(under.acceptedIds, ["a", "b"]);
  assert.equal(under.overflowCount, 0);
}
assert.equal(shouldShowQueueTileDetailsButton(ready), true);
assert.equal(primaryQueueAction(makeItem("c1", "CANCELLED")), "inspect");
assert.equal(shouldShowQueueTileDetailsButton(makeItem("c1", "CANCELLED")), false);
{
  const cancelled = makeItem("c-dismiss", "CANCELLED");
  cancelled.available_actions = [{ action: "DISMISS", label: "Dismiss", description: "Hide", requires_note: false }];
  assert.equal(primaryQueueAction(cancelled), "inspect", "cancelled tiles open Details, not green Dismiss");
  assert.equal(terminalQueueDismissAction(cancelled), "DISMISS");
  assert.equal(queueTilePrimaryButtonTone(cancelled), "inspect");
  assert.equal(queueTileShowsForwardArrow(cancelled), false);
}
{
  const failed = makeItem("f-retry", "FAILED_NEEDS_ATTENTION");
  failed.available_actions = [
    { action: "RETRY", label: "Retry", description: "Retry", requires_note: false },
    { action: "DISMISS", label: "Dismiss", description: "Hide", requires_note: false }
  ];
  assert.equal(primaryQueueAction(failed), "RETRY");
  assert.equal(queueTilePrimaryButtonTone(failed), "recover");
  assert.equal(queueTileShowsForwardArrow(failed), false, "Retry must not look like a forward workflow CTA");
  assert.equal(primaryQueueActionLabel(failed), "Retry");
}
assert.equal(buildQueueTileSecondaryLinks(makeItem("c1", "CANCELLED")).length, 0);

const handoffOnly = buildReupQueueSummary([makeItem("h1", "PUBLISH_HANDOFF_CREATED")]);
assert.match(quickPathGuidance(handoffOnly, "all") ?? "", /handoff/i);

const heroStats = buildQuickPathHeroStats(summary);
assert.equal(heroStats.find((stat) => stat.key === "needs_start")?.count, 1);
assert.equal(heroStats.find((stat) => stat.key === "all")?.count, 3);
assert.equal(quickPathSuggestedFilter(summary, "all"), "needs_start");
assert.equal(quickPathSuggestedFilter(summary, "needs_start"), "attention");
assert.equal(quickPathGuidance(buildReupQueueSummary([failed]), "attention"), null);

const readyActions = [{ action: "START_PROCESSING" as const, label: "Start processing", description: "Start", requires_note: false }];
assert.equal(pickInspectorSpotlightAction(readyActions)?.action, "START_PROCESSING");
const mixedActions = [
  { action: "CANCEL" as const, label: "Cancel", description: "Cancel", requires_note: false },
  { action: "HOLD" as const, label: "Hold / pause", description: "Hold", requires_note: false },
  { action: "START_PROCESSING" as const, label: "Start processing", description: "Start", requires_note: false }
];
const grouped = groupInspectorLifecycleActions(mixedActions.filter((entry) => entry.action !== "START_PROCESSING"));
assert.equal(grouped.danger.length, 1);
assert.equal(grouped.neutral.length, 1);
assert.equal(buildInspectorWorkflowLinks(ready).length >= 2, true);

const doneItem = makeItem("d1", "COMPLETED");
assert.equal(cancellableReupQueueItems([ready, doneItem]).length, 1);
assert.match(bulkCancelConfirmMessage(3, "needs_start"), /Needs start/);
assert.equal(supportsBulkCancelVisibleScope("done"), false);
assert.equal(formatBulkBarScopeMeta(3, 10, 0), "3/10 actionable");
assert.match(formatBatchResultSummary({ requested_count: 4, succeeded_count: 4, skipped_count: 0, failed_count: 0 } as never), /4\/4 succeeded/);
assert.equal(hasAnyBatchEligibility(doneItem), true, "Terminal queue items must be selectable for clear/purge cleanup");
assert.equal(selectableReupQueueItems([ready, doneItem]).length, 2);

assert.equal(resolveInitialReupQueueFilter(summary), "needs_start");
assert.equal(resolveInitialReupQueueFilter(buildReupQueueSummary([makeItem("h1", "PUBLISH_HANDOFF_CREATED")])), "handoff");

const pipeline = buildPipelineStages(ready);
assert.equal(pipeline.find((stage) => stage.key === "download")?.state, "pending");

const eligibility = buildSelectionEligibility([ready, doneItem]);
assert.equal(eligibility.start, 1);
assert.match(bulkSelectionGuidance(2, { ...eligibility, actionable: 1 }) ?? "", /can run a bulk action/);

assert.deepEqual(
  visibleReupQueueItems([ready, media, failed], "needs_start", "", "newest").map((item) => item.id),
  ["r1"]
);

{
  assert.ok("active-first" in REUP_QUEUE_SORT_LABELS, "active-first must be a named sort mode");
  const idleWaiting = makeItem("idle-w", "WAITING_FOR_MEDIA");
  idleWaiting.queued_at = "2026-07-15T10:00:00Z";
  const running = makeItem("run-w", "WAITING_FOR_MEDIA");
  running.queued_at = "2026-07-15T09:00:00Z";
  running.job_id = "job-run";
  running.job_status = "RUNNING";
  running.job_progress_percent = 37;
  const queued = makeItem("q-w", "WAITING_FOR_MEDIA");
  queued.queued_at = "2026-07-15T11:00:00Z";
  queued.job_id = "job-q";
  queued.job_status = "QUEUED";
  const paused = makeItem("p-w", "WAITING_FOR_MEDIA");
  paused.queued_at = "2026-07-15T12:00:00Z";
  paused.held_at = "2026-07-15T12:01:00Z";
  paused.job_id = "job-p";
  paused.job_status = "CANCELLED";
  const attention = makeItem("att-w", "FAILED_NEEDS_ATTENTION");
  attention.queued_at = "2026-07-15T13:00:00Z";
  const needsStart = makeItem("ns-w", "READY_FOR_PROCESSING");
  needsStart.queued_at = "2026-07-15T14:00:00Z";

  assert.ok(compareReupQueueItems(running, idleWaiting, "active-first") < 0, "RUNNING must sort before idle waiting");
  assert.ok(compareReupQueueItems(running, queued, "active-first") < 0, "RUNNING must sort before QUEUED");
  assert.ok(compareReupQueueItems(queued, paused, "active-first") < 0, "QUEUED must sort before Paused");
  assert.ok(compareReupQueueItems(paused, attention, "active-first") < 0, "Paused must sort before failed attention");
  assert.ok(compareReupQueueItems(attention, needsStart, "active-first") < 0, "Attention must sort before needs start");
  assert.deepEqual(
    visibleReupQueueItems(
      [needsStart, idleWaiting, attention, paused, queued, running],
      "all",
      "",
      "active-first"
    ).map((item) => item.id),
    ["run-w", "q-w", "p-w", "att-w", "ns-w", "idle-w"]
  );
}

const viewsItem = makeItem("views-1", "READY_FOR_PROCESSING");
viewsItem.source_video = {
  id: "video-views-1",
  source_profile_id: "profile-1",
  source_video_external_id: "aweme-views-1",
  source_url: "https://example.test/video",
  caption: "Fixture",
  posted_at: null,
  duration_seconds: 57,
  metadata_json: {
    source_metadata: { estimated_views_display: "717.8K-3.6M", like_count: 55_590 },
    like_count: 55_590
  }
};
assert.equal(queueTileViewsLabel(viewsItem), "717.8K-3.6M", "Queue tiles must resolve nested source_metadata estimated views");

const likesOnlyItem = makeItem("views-2", "READY_FOR_PROCESSING");
likesOnlyItem.source_video = {
  id: "video-views-2",
  source_profile_id: "profile-1",
  source_video_external_id: "aweme-views-2",
  source_url: "https://example.test/video-2",
  caption: "Fixture 2",
  posted_at: null,
  duration_seconds: 57,
  metadata_json: { like_count: 35_888 }
};
assert.match(queueTileViewsLabel(likesOnlyItem), /K/, "Queue tiles must estimate views from likes when display is missing");

const defaultBadge = queueTileScoreBadge({ ...makeItem("p-default", "READY_FOR_PROCESSING"), priority: 100 });
assert.notEqual(defaultBadge.tierLabel, "queue", "Default queue priority must not show misleading P100 queue badge");
assert.equal(defaultBadge.valueLabel, "0", "Queue tiles without metadata should operator-score to zero");

const scoredItem = makeItem("p-score", "READY_FOR_PROCESSING");
scoredItem.source_video = {
  id: "video-score",
  source_profile_id: "profile-1",
  source_video_external_id: "aweme-score",
  source_url: "https://example.test/score",
  caption: "Fixture score",
  posted_at: null,
  duration_seconds: 57,
  metadata_json: { reup_score: 88, like_count: 35_888 }
};
const scoredBadge = queueTileScoreBadge(scoredItem);
assert.notEqual(scoredBadge.score, 88, "Queue tiles must not use stale stored reup_score");
assert.ok(scoredBadge.tierLabel.length > 0, "Queue tiles should show operator tier label");

assert.equal(supportsBulkDismissVisibleScope("done"), true, "Done tab must support soft clear");
assert.equal(supportsBulkDismissVisibleScope("needs_start"), false, "Active tabs should not show clear-visible shortcut");
assert.equal(clearablePurgeReupQueueItems([{ ...makeItem("done-1", "CANCELLED"), available_actions: [{ action: "DISMISS", label: "Dismiss", description: "", requires_note: false }] }]).length, 1);
assert.equal(dismissableReupQueueItems([{ ...makeItem("done-1", "CANCELLED"), available_actions: [{ action: "DISMISS", label: "Dismiss", description: "", requires_note: false }] }]).length, 1);

assert.deepEqual(statusesForReupQueueFilter("all"), undefined);
assert.deepEqual(statusesForReupQueueFilter("needs_start"), ["READY_FOR_PROCESSING"]);
assert.deepEqual(statusesForReupQueueFilter("in_production"), [
  "WAITING_FOR_MEDIA",
  "WAITING_FOR_METADATA",
  "PROCESSING"
]);

const countsSummary = buildReupQueueSummaryFromStatusCounts({
  READY_FOR_PROCESSING: 19,
  WAITING_FOR_MEDIA: 40,
  FAILED_NEEDS_ATTENTION: 2
});
assert.equal(countsSummary.needs_start, 19);
assert.equal(countsSummary.in_production, 40);
assert.equal(countsSummary.attention, 2);
assert.equal(countsSummary.all, 61);
assert.equal(resolveInitialReupQueueFilter(countsSummary), "needs_start");

console.log("reup-queue-studio tests passed");

function makeItem(id: string, status: ReupQueueItem["status"]): ReupQueueItem {
  return {
    id,
    workspace_id: "ws-1",
    video_candidate_id: `cand-${id}`,
    source_video_id: `video-${id}`,
    status,
    bucket: status,
    next_action: "Start processing",
    priority: 50,
    queued_reason: "review_board_approved",
    operator_note: null,
    last_error_code: null,
    last_error_message: null,
    media_prep_status: "NOT_STARTED",
    media_prep_notes: null,
    media_ready_at: null,
    blocked_reason: null,
    blocked_at: null,
    held_at: null,
    failed_at: null,
    last_action: null,
    last_action_at: null,
    last_action_note: null,
    available_actions: status === "READY_FOR_PROCESSING"
      ? [
          { action: "START_PROCESSING", label: "Start processing", description: "Start", requires_note: false },
          { action: "CANCEL", label: "Cancel", description: "Cancel", requires_note: true }
        ]
      : [],
    queued_at: "2026-04-01T00:00:00Z",
    started_at: null,
    completed_at: null,
    cancelled_at: null,
    job_id: null,
    render_output_id: null,
    publish_draft_id: null,
    metadata_json: null,
    source_video: null,
    created_at: "2026-04-01T00:00:00Z",
    updated_at: "2026-04-01T00:00:00Z"
  };
}
