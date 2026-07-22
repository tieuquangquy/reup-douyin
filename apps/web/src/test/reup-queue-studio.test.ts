import assert from "node:assert/strict";
import {
  buildPipelineStages,
  buildQueueTileSecondaryLinks,
  pipelineTileFocusLabel,
  pipelineStageInteraction,
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
  buildInspectorWorkflowLinks,
  filterInspectorCompanionActions,
  groupInspectorLifecycleActions,
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
  queueStageTone,
  queueTileNextStepHint,
  queueTileFailureAlert,
  queueTileTranscriptCta,
  isAnalyzeAudioFailed,
  isMissingSourceAssetAnalyzeFailure,
  transcriptStageDisabledTitle,
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
  isNoDialogueAnalyzeResult,
  transcriptStageDisabledTitle,
  buildQueueInspectorEngagementStats
} from "../lib/reupQueueStudioState";
import type { ReupQueueItem } from "../types/reup-queue";

const ready = makeItem("r1", "READY_FOR_PROCESSING");
const media = makeItem("m1", "WAITING_FOR_MEDIA");
const failed = makeItem("f1", "FAILED_NEEDS_ATTENTION");

assert.equal(matchesReupQueueFilter(ready, "download"), true);
assert.equal(matchesReupQueueFilter(media, "download"), true);
assert.equal(matchesReupQueueFilter(failed, "download"), true, "Failed pre-media items stay in Download stage");
assert.equal(matchesReupQueueFilter(failed, "attention"), true);

const summary = buildReupQueueSummary([ready, media, failed]);
assert.equal(summary.all, 3);
assert.equal(summary.needs_start, 1);
assert.equal(summary.download, 3);
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
  assert.equal(worklistStageLabel(downloading), "Download");
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
  const pausedReady = makeItem("pause-ready", "WAITING_FOR_MEDIA");
  pausedReady.held_at = "2026-07-14T00:00:00Z";
  pausedReady.job_status = "COMPLETED";
  pausedReady.metadata_json = { download_job_completed: true };
  pausedReady.available_actions = [
    { action: "RESUME", label: "Resume", description: "Resume", requires_note: false },
    { action: "MARK_MEDIA_READY", label: "Mark media ready", description: "Confirm", requires_note: false }
  ];
  assert.equal(primaryQueueAction(pausedReady), "RESUME", "Paused tiles must prefer Resume over Mark media ready");
}
{
  const pausedTranscript = makeItem("pause-meta", "WAITING_FOR_METADATA");
  pausedTranscript.held_at = "2026-07-14T00:00:00Z";
  pausedTranscript.media_ready_at = "2026-07-14T00:00:00Z";
  pausedTranscript.available_actions = [
    { action: "RESUME", label: "Resume", description: "Resume", requires_note: false },
    { action: "CANCEL", label: "Cancel", description: "Cancel", requires_note: true }
  ];
  assert.equal(primaryQueueAction(pausedTranscript), "RESUME");
  assert.equal(queueStageLabel(pausedTranscript), "Paused");
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
  assert.equal(queueStageLabel(waitingDownload), "Confirm ready");
  assert.equal(worklistStageLabel(waitingDownload), "Download");
  assert.equal(worklistStageTone(waitingDownload), "good");
  assert.equal(primaryQueueActionLabel(waitingDownload), "Mark media ready");
  assert.equal(worklistPrimaryActionLabel(waitingDownload), "Mark media ready");
  assert.equal(
    worklistPrimaryActionLabel(waitingDownload),
    primaryQueueActionLabel(waitingDownload),
    "Worklist CTA labels must stay in sync with Gallery"
  );
  assert.equal(shouldShowQueueTileDetailsButton(waitingDownload), false, "Details open from thumbnail/title, not a tile button");
  waitingDownload.job_id = "job-1";
  assert.equal(formatJobChipLabel(waitingDownload), null, "completed download must not duplicate Job completed chip");
}
{
  const idleDownload = makeItem("w-idle", "WAITING_FOR_MEDIA");
  assert.equal(worklistStageLabel(idleDownload), "Download", "Idle media wait maps to Download pipeline stage");
  assert.equal(queueStageLabel(idleDownload), "Waiting for media");
  assert.equal(primaryQueueAction(idleDownload), "inspect");
  assert.match(
    queueTileNextStepHint(idleDownload) ?? "",
    /Waiting for download job|open Details if stuck/i,
    "Idle Waiting for media tiles must explain the next step"
  );
  assert.equal(
    shouldShowQueueTileDetailsButton(idleDownload),
    true,
    "Idle download-wait tiles must expose Open details when primary is inspect"
  );
}
{
  const downloadingHint = makeItem("dl-hint", "WAITING_FOR_MEDIA");
  downloadingHint.job_id = "job-dl-hint";
  downloadingHint.job_status = "RUNNING";
  downloadingHint.available_actions = [
    { action: "HOLD", label: "Pause", description: "Pause", requires_note: false }
  ];
  assert.match(queueTileNextStepHint(downloadingHint) ?? "", /Downloading|Confirm ready/i);
  assert.equal(shouldShowQueueTileDetailsButton(downloadingHint), false, "Active download with Pause CTA must not add Open details");
}
{
  const queuedHint = makeItem("q-hint", "WAITING_FOR_MEDIA");
  queuedHint.job_id = "job-q-hint";
  queuedHint.job_status = "QUEUED";
  queuedHint.available_actions = [
    { action: "HOLD", label: "Pause", description: "Pause", requires_note: false }
  ];
  assert.match(queueTileNextStepHint(queuedHint) ?? "", /queued|worker will start/i);
}
{
  const pausedHint = makeItem("p-hint", "WAITING_FOR_MEDIA");
  pausedHint.held_at = "2026-07-14T00:00:00Z";
  pausedHint.job_id = "job-p-hint";
  pausedHint.job_status = "CANCELLED";
  pausedHint.available_actions = [
    { action: "RESUME", label: "Resume", description: "Resume", requires_note: false }
  ];
  assert.match(queueTileNextStepHint(pausedHint) ?? "", /Paused|Resume/i);
}
{
  const confirmReadyHint = makeItem("confirm-hint", "WAITING_FOR_MEDIA");
  confirmReadyHint.job_status = "COMPLETED";
  confirmReadyHint.metadata_json = { download_job_completed: true };
  confirmReadyHint.available_actions = [
    { action: "MARK_MEDIA_READY", label: "Mark media ready", description: "Confirm", requires_note: false }
  ];
  assert.equal(queueTileNextStepHint(confirmReadyHint), null, "Confirm-ready tiles use CTA, not a waiting hint");
  assert.equal(shouldShowQueueTileDetailsButton(confirmReadyHint), false);
}
{
  const metaWait = makeItem("meta-wait", "WAITING_FOR_METADATA");
  assert.equal(queueStageLabel(metaWait), "Transcript", "Gallery chip must use short Transcript label (not truncated Waiting for metadata)");
  assert.equal(worklistStageLabel(metaWait), "Transcript");
}
{
  const analyzingChip = makeItem("meta-analyzing", "WAITING_FOR_METADATA");
  analyzingChip.job_id = "analyze-run";
  analyzingChip.job_type = "ANALYZE_AUDIO";
  analyzingChip.job_status = "RUNNING";
  assert.equal(queueStageLabel(analyzingChip), "Analyzing", "Gallery chip must show Analyzing while analyze runs");
  assert.equal(queueStageTone(analyzingChip), "warn");
  assert.equal(queueTileTranscriptCta(analyzingChip), null);
  assert.match(queueTileNextStepHint(analyzingChip) ?? "", /still running|opens when done/i);
}
{
  const readyChip = makeItem("meta-ready", "WAITING_FOR_METADATA");
  readyChip.job_id = "analyze-done";
  readyChip.job_type = "ANALYZE_AUDIO";
  readyChip.job_status = "COMPLETED";
  readyChip.has_speech = true;
  readyChip.dialogue_phase = "source_auto_approved";
  readyChip.transcript_count = 4;
  assert.equal(queueStageLabel(readyChip), "Transcript ready");
  assert.equal(queueStageTone(readyChip), "good");
  assert.deepEqual(queueTileTranscriptCta(readyChip), {
    href: `/production/transcript-editor/${readyChip.source_video_id}`,
    label: "Open Transcript"
  });
  assert.equal(queueTileNextStepHint(readyChip), null, "Ready tiles use CTA, not a waiting hint");
  readyChip.available_actions = [
    { action: "MARK_MEDIA_READY", label: "Mark media ready", description: "Confirm", requires_note: false },
    { action: "HOLD", label: "Pause", description: "Pause", requires_note: false },
    { action: "CANCEL", label: "Cancel", description: "Cancel", requires_note: true },
    { action: "MARK_BLOCKED", label: "Mark blocked", description: "Block", requires_note: true }
  ];
  assert.deepEqual(
    filterInspectorCompanionActions(readyChip, readyChip.available_actions).map((entry) => entry.action),
    ["HOLD", "CANCEL", "MARK_BLOCKED"],
    "Transcript ready details must not expose Mark media ready"
  );
  assert.equal(
    buildInspectorWorkflowLinks(readyChip).some((link) => link.label === "Transcript"),
    false,
    "Transcript ready must not duplicate Open Transcript as a workflow chip"
  );
}
{
  const silentChip = makeItem("meta-silent", "WAITING_FOR_METADATA");
  silentChip.job_id = "analyze-silent";
  silentChip.job_type = "ANALYZE_AUDIO";
  silentChip.job_status = "COMPLETED";
  silentChip.has_speech = false;
  silentChip.dialogue_phase = "no_dialogue";
  silentChip.transcript_count = 0;
  assert.equal(queueStageLabel(silentChip), "No dialogue");
  assert.equal(queueStageTone(silentChip), "muted");
  assert.equal(queueTileTranscriptCta(silentChip), null);
  assert.match(queueTileNextStepHint(silentChip) ?? "", /Skip dubbing|caption/i);
}
{
  const missingAsset = makeItem("meta-missing-asset", "WAITING_FOR_METADATA");
  missingAsset.job_id = "analyze-fail";
  missingAsset.job_type = "ANALYZE_AUDIO";
  missingAsset.job_status = "FAILED";
  missingAsset.job_error_code = "MISSING_SOURCE_ASSET";
  missingAsset.job_error_message = "No SOURCE_AUDIO_EXTRACT or SOURCE_VIDEO_RAW asset is available";
  missingAsset.available_actions = [
    { action: "RETRY", label: "Retry", description: "Retry", requires_note: false },
    { action: "MARK_MEDIA_READY", label: "Mark media ready", description: "Confirm", requires_note: false },
    { action: "HOLD", label: "Pause", description: "Pause", requires_note: false }
  ];
  assert.equal(isAnalyzeAudioFailed(missingAsset), true);
  assert.equal(isMissingSourceAssetAnalyzeFailure(missingAsset), true);
  assert.equal(queueStageLabel(missingAsset), "Analyze failed");
  assert.equal(queueStageTone(missingAsset), "danger");
  assert.equal(queueTileTranscriptCta(missingAsset), null);
  assert.equal(queueTileNextStepHint(missingAsset), null, "Gallery uses compact failure alert instead of long recovery copy");
  assert.deepEqual(queueTileFailureAlert(missingAsset), {
    message: "Raw video missing",
    detail: "Click Download to check the file. If missing: Retry from start → Start processing → Mark media ready."
  });
  assert.equal(
    buildPipelineStages(missingAsset).find((stage) => stage.key === "transcript")?.state,
    "failed",
    "Analyze-failed tiles must mark Transcript as failed, not active"
  );
  assert.equal(primaryQueueAction(missingAsset), "RETRY");
  assert.equal(primaryQueueActionLabel(missingAsset), "Retry from start");
  assert.match(transcriptStageDisabledTitle(missingAsset), /missing|Raw video|Download/i);
}
{
  const analyzeFailed = makeItem("meta-analyze-fail", "WAITING_FOR_METADATA");
  analyzeFailed.job_id = "analyze-fail-generic";
  analyzeFailed.job_type = "ANALYZE_AUDIO";
  analyzeFailed.job_status = "FAILED";
  analyzeFailed.job_error_message = "Speech gate provider timed out";
  analyzeFailed.available_actions = [
    { action: "MARK_MEDIA_READY", label: "Mark media ready", description: "Confirm", requires_note: false }
  ];
  assert.equal(isMissingSourceAssetAnalyzeFailure(analyzeFailed), false);
  assert.equal(queueStageLabel(analyzeFailed), "Analyze failed");
  assert.equal(queueTileNextStepHint(analyzeFailed), null, "Analyze-failed gallery uses compact alert, not long hint");
  assert.equal(queueTileFailureAlert(analyzeFailed)?.message, "Analyze failed");
  assert.match(queueTileFailureAlert(analyzeFailed)?.detail ?? "", /Speech gate|Details|Retry analyze/i);
  assert.equal(primaryQueueAction(analyzeFailed), "MARK_MEDIA_READY");
  assert.equal(primaryQueueActionLabel(analyzeFailed), "Retry analyze");
  assert.equal(
    filterInspectorCompanionActions(analyzeFailed, analyzeFailed.available_actions).some((entry) => entry.action === "MARK_MEDIA_READY"),
    true,
    "Analyze-failed details may keep Retry analyze when it is not already the spotlight primary"
  );
  assert.equal(
    filterInspectorCompanionActions(analyzeFailed, analyzeFailed.available_actions).find((entry) => entry.action === "MARK_MEDIA_READY")?.label,
    "Retry analyze"
  );
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
  assert.equal(worklistStageLabel(analyzing), "Transcript ready");
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
  const staleLink = makeItem("stale-analyze", "WAITING_FOR_METADATA");
  staleLink.job_id = "cancelled-download";
  staleLink.job_type = "DOWNLOAD_VIDEO";
  staleLink.job_status = "CANCELLED";
  staleLink.has_speech = true;
  staleLink.dialogue_phase = "source_auto_approved";
  staleLink.transcript_count = 3;
  assert.equal(
    worklistTranscriptHref(staleLink),
    `/production/transcript-editor/${staleLink.source_video_id}`,
    "Persisted analyze outcome must unlock Transcript even if linked job_id is stale"
  );
  assert.equal(
    pipelineStageInteraction(staleLink, buildPipelineStages(staleLink).find((stage) => stage.key === "transcript")!).kind,
    "href"
  );
}
{
  const running = makeItem("run-analyze", "WAITING_FOR_METADATA");
  running.job_id = "analyze-running";
  running.job_type = "ANALYZE_AUDIO";
  running.job_status = "RUNNING";
  assert.match(
    transcriptStageDisabledTitle(running),
    /still running|Analyze/i,
    "Running analyze must explain why Transcript is not clickable"
  );
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
  assert.match(transcriptStageDisabledTitle(silent), /spoken dialogue|No dialogue/i);
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
assert.equal(shouldShowQueueTileDetailsButton(ready), false, "Ready tiles must not expose a Details button");
assert.equal(primaryQueueAction(makeItem("c1", "CANCELLED")), "inspect");
assert.equal(shouldShowQueueTileDetailsButton(makeItem("c1", "CANCELLED")), false);
{
  const cancelled = makeItem("c-dismiss", "CANCELLED");
  cancelled.available_actions = [{ action: "DISMISS", label: "Dismiss", description: "Hide", requires_note: false }];
  assert.equal(primaryQueueAction(cancelled), "inspect", "cancelled tiles rely on thumbnail/title for details, not green Dismiss");
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
{
  const preAnalyze = makeItem("sec-ready", "WAITING_FOR_MEDIA");
  preAnalyze.metadata_json = { download_job_completed: true };
  assert.equal(
    buildQueueTileSecondaryLinks(preAnalyze).some((link) => /transcript/i.test(link.label)),
    false,
    "Gallery tiles must not expose Transcript before analyze completes"
  );

  const analyzed = makeItem("sec-analyzed", "WAITING_FOR_METADATA");
  analyzed.job_id = "sec-analyze-job";
  analyzed.job_type = "ANALYZE_AUDIO";
  analyzed.job_status = "COMPLETED";
  analyzed.transcript_count = 2;
  analyzed.has_speech = true;
  analyzed.dialogue_phase = "source_auto_approved";
  const analyzedLinks = buildQueueTileSecondaryLinks(analyzed);
  assert.equal(
    analyzedLinks.some((link) => /transcript/i.test(link.label)),
    false,
    "Analyzed gallery tiles keep Transcript off secondary links (primary CTA + stepper own it)"
  );
  assert.equal(queueTileTranscriptCta(analyzed)?.label, "Open Transcript");

  const stages = buildPipelineStages(preAnalyze);
  assert.equal(pipelineTileFocusLabel(stages).startsWith("Now:"), true, "Tile pipeline focus must call out the active stage");
  assert.equal(pipelineTileFocusLabel(buildPipelineStages(analyzed)).length > 0, true);
  assert.equal(
    pipelineStageInteraction(preAnalyze, stages[0]!).kind,
    "reveal-download",
    "Download-ready tiles must reveal the local raw video"
  );
  assert.equal(
    pipelineStageInteraction(analyzed, buildPipelineStages(analyzed).find((stage) => stage.key === "transcript")!).kind,
    "href",
    "Analyzed tiles must deep-link Transcript"
  );
  assert.equal(
    pipelineStageInteraction(preAnalyze, stages.find((stage) => stage.key === "export")!).kind,
    "disabled",
    "Export must stay disabled until a package exists"
  );
}

const handoffOnly = buildReupQueueSummary([makeItem("h1", "PUBLISH_HANDOFF_CREATED")]);
assert.equal(handoffOnly.handoff, 1);

const heroStats = buildQuickPathHeroStats(summary);
assert.equal(heroStats.find((stat) => stat.key === "download")?.count, 3);
assert.equal(heroStats.find((stat) => stat.key === "all")?.count, 3);
assert.equal(heroStats.find((stat) => stat.key === "all")?.tone, "neutral", "All queue bars must keep the same colored neutral accent as Review Board");
const completedHeroStats = buildQuickPathHeroStats(buildReupQueueSummary([makeItem("done-1", "COMPLETED")]));
assert.equal(completedHeroStats.find((stat) => stat.key === "done")?.tone, "good", "Completed queue bars must use the semantic success color");

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
{
  const attentionActions = [
    { action: "DISMISS" as const, label: "Dismiss", description: "Hide", requires_note: false },
    { action: "RESUME" as const, label: "Resume", description: "Resume", requires_note: false },
    { action: "CANCEL" as const, label: "Cancel", description: "Cancel", requires_note: true },
    { action: "RETRY" as const, label: "Retry", description: "Retry", requires_note: false }
  ];
  const remaining = attentionActions.filter((entry) => entry.action !== "RETRY");
  const attentionGrouped = groupInspectorLifecycleActions(remaining);
  assert.deepEqual(
    attentionGrouped.primary.map((entry) => entry.action),
    ["RESUME"],
    "Attention recover actions must list Resume before quiet/danger"
  );
  assert.deepEqual(
    attentionGrouped.quiet.map((entry) => entry.action),
    ["DISMISS"],
    "Dismiss must sit in the quiet trailing group, not between Retry and Resume"
  );
  assert.deepEqual(
    attentionGrouped.danger.map((entry) => entry.action),
    ["CANCEL"],
    "Cancel stays in the danger group after recover actions"
  );
}
{
  const readyLinks = buildInspectorWorkflowLinks(ready);
  assert.equal(
    readyLinks.some((link) => link.label === "Transcript"),
    false,
    "Ready / pre-analyze inspector must not expose Transcript"
  );
  assert.equal(
    readyLinks.some((link) => link.label === "Final review"),
    false,
    "Ready / pre-render inspector must not expose Final review"
  );

  const analyzed = makeItem("wf-analyzed", "WAITING_FOR_METADATA");
  analyzed.job_id = "wf-analyze-job";
  analyzed.job_type = "ANALYZE_AUDIO";
  analyzed.job_status = "COMPLETED";
  analyzed.transcript_count = 2;
  analyzed.has_speech = true;
  analyzed.dialogue_phase = "source_auto_approved";
  const analyzedLinks = buildInspectorWorkflowLinks(analyzed);
  assert.equal(
    analyzedLinks.some((link) => link.href === `/production/transcript-editor/${analyzed.source_video_id}` && link.label === "Transcript"),
    false,
    "Analyzed + speech inspector must not duplicate Open Transcript as a workflow chip"
  );
  assert.equal(
    analyzedLinks.some((link) => link.label === "Final review"),
    false,
    "Analyzed without render output must not expose Final review yet"
  );

  const silent = makeItem("wf-silent", "WAITING_FOR_METADATA");
  silent.job_id = "wf-silent-job";
  silent.job_type = "ANALYZE_AUDIO";
  silent.job_status = "COMPLETED";
  silent.dialogue_phase = "no_dialogue";
  silent.has_speech = false;
  silent.transcript_count = 0;
  assert.equal(
    buildInspectorWorkflowLinks(silent).some((link) => link.label === "Transcript"),
    false,
    "No-dialogue inspector must not open empty Transcript"
  );

  const rendered = makeItem("wf-render", "READY_TO_EXPORT");
  rendered.render_output_id = "render-1";
  rendered.media_prep_status = "READY_FOR_EXPORT";
  assert.equal(
    buildInspectorWorkflowLinks(rendered).some((link) => link.href === `/production/final-review/${rendered.source_video_id}` && link.label === "Final review"),
    true,
    "Inspector must expose Final review once render output exists"
  );
}

const doneItem = makeItem("d1", "COMPLETED");
assert.equal(cancellableReupQueueItems([ready, doneItem]).length, 1);
assert.match(bulkCancelConfirmMessage(3, "download"), /Download/);
assert.equal(supportsBulkCancelVisibleScope("done"), false);
assert.equal(formatBulkBarScopeMeta(3, 10, 0), "3/10 actionable");
assert.match(formatBatchResultSummary({ requested_count: 4, succeeded_count: 4, skipped_count: 0, failed_count: 0 } as never), /4\/4 succeeded/);
assert.equal(hasAnyBatchEligibility(doneItem), true, "Terminal queue items must be selectable for clear/purge cleanup");
assert.equal(selectableReupQueueItems([ready, doneItem]).length, 2);

assert.equal(resolveInitialReupQueueFilter(summary), "download");
assert.equal(resolveInitialReupQueueFilter(buildReupQueueSummary([makeItem("h1", "PUBLISH_HANDOFF_CREATED")])), "handoff");

const pipeline = buildPipelineStages(ready);
assert.equal(pipeline.find((stage) => stage.key === "download")?.state, "pending");

const eligibility = buildSelectionEligibility([ready, doneItem]);
assert.equal(eligibility.start, 1);
assert.match(bulkSelectionGuidance(2, { ...eligibility, actionable: 1 }) ?? "", /can run a bulk action/);

assert.deepEqual(
  visibleReupQueueItems([ready, media, failed], "download", "", "newest").map((item) => item.id),
  ["r1", "m1", "f1"]
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
{
  const engagement = buildQueueInspectorEngagementStats(viewsItem);
  assert.equal(engagement.find((stat) => stat.label === "Est. Views")?.value, "717.8K-3.6M");
  assert.equal(engagement.find((stat) => stat.label === "Likes")?.value, "55,590");
  assert.equal(engagement.find((stat) => stat.label === "Comments")?.value, "—");
  assert.equal(engagement.find((stat) => stat.label === "Shares")?.value, "—");
}

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
assert.equal(supportsBulkDismissVisibleScope("download"), false, "Active tabs should not show clear-visible shortcut");
assert.equal(clearablePurgeReupQueueItems([{ ...makeItem("done-1", "CANCELLED"), available_actions: [{ action: "DISMISS", label: "Dismiss", description: "", requires_note: false }] }]).length, 1);
assert.equal(dismissableReupQueueItems([{ ...makeItem("done-1", "CANCELLED"), available_actions: [{ action: "DISMISS", label: "Dismiss", description: "", requires_note: false }] }]).length, 1);

assert.deepEqual(statusesForReupQueueFilter("all"), undefined);
assert.deepEqual(statusesForReupQueueFilter("download"), ["READY_FOR_PROCESSING", "WAITING_FOR_MEDIA"]);
assert.deepEqual(statusesForReupQueueFilter("transcript"), ["WAITING_FOR_METADATA"]);
assert.deepEqual(statusesForReupQueueFilter("render"), ["PROCESSING"]);
assert.deepEqual(statusesForReupQueueFilter("export"), ["READY_TO_EXPORT"]);

{
  const transcriptItem = makeItem("t1", "WAITING_FOR_METADATA");
  const renderItem = makeItem("rnd1", "PROCESSING");
  renderItem.media_ready_at = "2026-07-14T00:00:00Z";
  renderItem.media_prep_status = "READY_FOR_EXPORT";
  const exportItem = makeItem("e1", "READY_TO_EXPORT");
  exportItem.media_prep_status = "READY_FOR_EXPORT";
  assert.equal(matchesReupQueueFilter(transcriptItem, "transcript"), true);
  assert.equal(matchesReupQueueFilter(renderItem, "render"), true);
  assert.equal(matchesReupQueueFilter(exportItem, "export"), true);
  assert.equal(matchesReupQueueFilter(exportItem, "download"), false);
  const stageSummary = buildReupQueueSummary([ready, transcriptItem, renderItem, exportItem]);
  assert.equal(stageSummary.download, 1);
  assert.equal(stageSummary.transcript, 1);
  assert.equal(stageSummary.render, 1);
  assert.equal(stageSummary.export, 1);
}

const countsSummary = buildReupQueueSummaryFromStatusCounts({
  READY_FOR_PROCESSING: 19,
  WAITING_FOR_MEDIA: 40,
  FAILED_NEEDS_ATTENTION: 2
});
assert.equal(countsSummary.needs_start, 19);
assert.equal(countsSummary.download, 59);
assert.equal(countsSummary.attention, 2);
assert.equal(countsSummary.all, 61);
assert.equal(resolveInitialReupQueueFilter(countsSummary), "download");

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
