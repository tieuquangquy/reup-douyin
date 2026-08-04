import type { ReupQueueBatchAction, BatchOperationResponse } from "../types/export-handoff";
import type { ReupQueueAction, ReupQueueAvailableAction, ReupQueueItem, ReupQueueStatus } from "../types/reup-queue";
import { formatExactEngagementMetric } from "./captureInboxCanonical";
import { buildCapturedItemFromReupQueueItem } from "./operatorReupScore";
import { getOperatorTileScoreBadge, type OperatorTileScoreBadge } from "./operatorTileScore";

export type ReupQueueOperatorFilter =
  | "all"
  | "download"
  | "transcript"
  | "render"
  | "export"
  | "handoff"
  | "attention"
  | "done";
export type ReupQueueSortMode = "active-first" | "newest" | "ready-first" | "needs-attention-first" | "export-ready-first";

export type ReupQueueStudioSummary = Record<ReupQueueOperatorFilter, number> & {
  /** Count for Start-all-ready CTA — not a pipeline chip. */
  needs_start: number;
};

export const REUP_QUEUE_STATUS_FILTERS: Array<{ key: ReupQueueOperatorFilter; label: string }> = [
  { key: "all", label: "All" },
  { key: "download", label: "Download" },
  { key: "transcript", label: "Transcript" },
  { key: "render", label: "Render" },
  { key: "export", label: "Export" },
  { key: "handoff", label: "Handoff" },
  { key: "attention", label: "Attention" },
  { key: "done", label: "Done" }
];

export const REUP_QUEUE_PIPELINE_FILTERS: ReupQueueOperatorFilter[] = ["all", "download", "transcript", "render", "export"];
export const REUP_QUEUE_ATTENTION_FILTERS: ReupQueueOperatorFilter[] = ["handoff", "attention", "done"];

export const REUP_QUEUE_SORT_LABELS: Record<ReupQueueSortMode, string> = {
  "active-first": "Active first",
  newest: "Newest",
  "ready-first": "Ready first",
  "needs-attention-first": "Needs attention first",
  "export-ready-first": "Export ready first"
};

export function buildReupQueueSummary(items: ReupQueueItem[]): ReupQueueStudioSummary {
  return {
    all: items.length,
    download: items.filter((item) => matchesReupQueueFilter(item, "download")).length,
    transcript: items.filter((item) => matchesReupQueueFilter(item, "transcript")).length,
    render: items.filter((item) => matchesReupQueueFilter(item, "render")).length,
    export: items.filter((item) => matchesReupQueueFilter(item, "export")).length,
    handoff: items.filter((item) => matchesReupQueueFilter(item, "handoff")).length,
    attention: items.filter((item) => matchesReupQueueFilter(item, "attention")).length,
    done: items.filter((item) => matchesReupQueueFilter(item, "done")).length,
    needs_start: items.filter((item) => item.status === "READY_FOR_PROCESSING").length
  };
}

export function statusesForReupQueueFilter(filter: ReupQueueOperatorFilter): ReupQueueStatus[] | undefined {
  if (filter === "all") return undefined;
  if (filter === "download") return ["READY_FOR_PROCESSING", "WAITING_FOR_MEDIA"];
  if (filter === "transcript") return ["WAITING_FOR_METADATA"];
  if (filter === "render") return ["PROCESSING"];
  if (filter === "export") return ["READY_TO_EXPORT"];
  if (filter === "handoff") return ["READY_TO_PUBLISH", "PUBLISH_HANDOFF_CREATED"];
  if (filter === "attention") return ["FAILED_NEEDS_ATTENTION"];
  if (filter === "done") return ["COMPLETED", "CANCELLED"];
  return undefined;
}

export function buildReupQueueSummaryFromStatusCounts(statusCounts: Record<string, number> | null | undefined): ReupQueueStudioSummary {
  const count = (status: ReupQueueStatus) => Number(statusCounts?.[status] ?? 0);
  const needsStart = count("READY_FOR_PROCESSING");
  const download = needsStart + count("WAITING_FOR_MEDIA");
  const transcript = count("WAITING_FOR_METADATA");
  const render = count("PROCESSING");
  const exportReady = count("READY_TO_EXPORT");
  const handoff = count("READY_TO_PUBLISH") + count("PUBLISH_HANDOFF_CREATED");
  const attention = count("FAILED_NEEDS_ATTENTION");
  const done = count("COMPLETED") + count("CANCELLED");
  const all = Object.values(statusCounts ?? {}).reduce((sum, value) => sum + Number(value || 0), 0);
  return {
    all,
    download,
    transcript,
    render,
    export: exportReady,
    handoff,
    attention,
    done,
    needs_start: needsStart
  };
}

export function matchesReupQueueFilter(item: ReupQueueItem, filter: ReupQueueOperatorFilter): boolean {
  if (filter === "all") return true;
  if (filter === "download" || filter === "transcript" || filter === "render" || filter === "export") {
    return matchesPipelineStageFilter(item, filter);
  }
  if (filter === "handoff") return item.status === "READY_TO_PUBLISH" || item.status === "PUBLISH_HANDOFF_CREATED";
  if (filter === "attention") return item.status === "FAILED_NEEDS_ATTENTION" || Boolean(item.blocked_reason);
  if (filter === "done") return item.status === "COMPLETED" || item.status === "CANCELLED";
  return true;
}

/** Items currently focused on a tile pipeline stage (active/failed), plus Needs-start under Download. */
export function matchesPipelineStageFilter(
  item: ReupQueueItem,
  stageKey: "download" | "transcript" | "render" | "export"
): boolean {
  if (stageKey === "download" && item.status === "READY_FOR_PROCESSING") return true;
  const stage = buildPipelineStages(item).find((entry) => entry.key === stageKey);
  return stage?.state === "active" || stage?.state === "failed";
}

export function matchesReupQueueSearch(item: ReupQueueItem, query: string): boolean {
  const normalized = query.trim().toLowerCase();
  if (!normalized) return true;
  const exportPackageId = metadataString(item.metadata_json, "export_package_id");
  const publishHandoffId = metadataString(item.metadata_json, "publish_handoff_id");
  const values = [
    item.id,
    item.video_candidate_id,
    item.source_video_id,
    item.bucket,
    item.next_action,
    item.blocked_reason,
    item.last_error_code,
    item.last_error_message,
    item.source_video?.caption,
    item.source_video?.source_profile_id,
    item.source_video?.source_video_external_id,
    item.source_video?.source_url,
    exportPackageId,
    publishHandoffId
  ];
  return values.some((value) => typeof value === "string" && value.toLowerCase().includes(normalized));
}

export function compareReupQueueItems(left: ReupQueueItem, right: ReupQueueItem, sortMode: ReupQueueSortMode): number {
  if (sortMode === "active-first") {
    return (
      activeFirstPriority(left) - activeFirstPriority(right) ||
      activeProgressRank(right) - activeProgressRank(left) ||
      newestFirst(left, right)
    );
  }
  if (sortMode === "ready-first") return readyPriority(left) - readyPriority(right) || newestFirst(left, right);
  if (sortMode === "needs-attention-first") return attentionPriority(left) - attentionPriority(right) || newestFirst(left, right);
  if (sortMode === "export-ready-first") return exportPriority(left) - exportPriority(right) || newestFirst(left, right);
  return newestFirst(left, right);
}

export function visibleReupQueueItems(
  items: ReupQueueItem[],
  filter: ReupQueueOperatorFilter,
  searchQuery: string,
  sortMode: ReupQueueSortMode
): ReupQueueItem[] {
  return items
    .filter((item) => matchesReupQueueFilter(item, filter) && matchesReupQueueSearch(item, searchQuery))
    .sort((left, right) => compareReupQueueItems(left, right, sortMode));
}

export function selectedVisibleReupQueueIds(visible: ReupQueueItem[], selectedIds: Set<string>): string[] {
  const visibleIds = new Set(visible.map((item) => item.id));
  return [...selectedIds].filter((id) => visibleIds.has(id));
}

export function toggleReupQueueSelection(selection: Set<string>, itemId: string): Set<string> {
  const next = new Set(selection);
  if (next.has(itemId)) next.delete(itemId);
  else next.add(itemId);
  return next;
}

export function selectAllVisibleReupQueueItems(visible: ReupQueueItem[]): Set<string> {
  return new Set(visible.map((item) => item.id));
}

const BATCH_ACTION_TYPES: ReupQueueBatchAction[] = [
  "START_PROCESSING",
  "START_AUTO_PIPELINE",
  "HOLD",
  "RESUME",
  "RETRY",
  "MARK_MEDIA_READY",
  "CREATE_EXPORT_PACKAGE",
  "CREATE_PUBLISH_HANDOFF",
  "CANCEL",
  "DISMISS"
];

export function isOperatorClearableQueueItem(item: ReupQueueItem): boolean {
  return item.status === "COMPLETED" || item.status === "CANCELLED" || item.status === "FAILED_NEEDS_ATTENTION";
}

export function hasAnyBatchEligibility(item: ReupQueueItem): boolean {
  if (BATCH_ACTION_TYPES.some((action) => isLikelyEligibleForBatch(item, action))) return true;
  return isOperatorClearableQueueItem(item);
}

export function selectableReupQueueItems(items: ReupQueueItem[]): ReupQueueItem[] {
  return items.filter(hasAnyBatchEligibility);
}

export function selectAllActionableReupQueueItems(visible: ReupQueueItem[]): Set<string> {
  return new Set(selectableReupQueueItems(visible).map((item) => item.id));
}

export type ReupQueueSelectionEligibility = {
  start: number;
  startAuto: number;
  setAutomation: number;
  export: number;
  handoff: number;
  hold: number;
  resume: number;
  retry: number;
  markMediaReady: number;
  cancel: number;
  dismiss: number;
  actionable: number;
};

export function buildSelectionEligibility(selected: ReupQueueItem[]): ReupQueueSelectionEligibility {
  return {
    start: eligibleBatchCount(selected, "START_PROCESSING"),
    startAuto: eligibleBatchCount(selected, "START_AUTO_PIPELINE"),
    setAutomation: selected.filter(canChangeAutomation).length,
    export: eligibleBatchCount(selected, "CREATE_EXPORT_PACKAGE"),
    handoff: eligibleBatchCount(selected, "CREATE_PUBLISH_HANDOFF"),
    hold: eligibleBatchCount(selected, "HOLD"),
    resume: eligibleBatchCount(selected, "RESUME"),
    retry: eligibleBatchCount(selected, "RETRY"),
    markMediaReady: eligibleBatchCount(selected, "MARK_MEDIA_READY"),
    cancel: eligibleBatchCount(selected, "CANCEL"),
    dismiss: eligibleBatchCount(selected, "DISMISS"),
    actionable: selectableReupQueueItems(selected).length
  };
}

export function primaryBulkEligibilityTotal(eligibility: ReupQueueSelectionEligibility): number {
  return eligibility.startAuto + eligibility.start + eligibility.export + eligibility.handoff;
}

export function secondaryBulkEligibilityTotal(eligibility: ReupQueueSelectionEligibility): number {
  return eligibility.hold + eligibility.resume + eligibility.retry + eligibility.markMediaReady + eligibility.cancel + eligibility.dismiss;
}

export function formatQuickPathPipelineMeta(summary: ReupQueueStudioSummary, sortLabel: string, visibleCount: number): string {
  return [
    `${visibleCount} in view`,
    `${summary.download} download`,
    `${summary.transcript} transcript`,
    `${summary.render} render`,
    `${summary.export} export`,
    `${summary.handoff} handoff`,
    `${summary.attention} attention`,
    `${summary.done} done`,
    `Sort: ${sortLabel}`
  ].join(" · ");
}

export type ReupQueueHeroStat = {
  key: ReupQueueOperatorFilter;
  label: string;
  count: number;
  tone: "good" | "warn" | "danger" | "muted" | "neutral";
};

export function buildQuickPathHeroStats(summary: ReupQueueStudioSummary): ReupQueueHeroStat[] {
  return REUP_QUEUE_STATUS_FILTERS.map((entry) => ({
    key: entry.key,
    label: entry.label,
    count: summary[entry.key],
    tone: heroStatTone(entry.key, summary)
  }));
}

function heroStatTone(key: ReupQueueOperatorFilter, summary: ReupQueueStudioSummary): ReupQueueHeroStat["tone"] {
  if (summary[key] === 0) return "muted";
  if (key === "all" || key === "handoff") return "neutral";
  if (key === "download") return summary.download > 0 ? "good" : "muted";
  if (key === "transcript" || key === "render") return summary[key] > 0 ? "warn" : "muted";
  if (key === "export") return summary.export > 0 ? "good" : "muted";
  if (key === "attention") return summary.attention > 0 ? "danger" : "muted";
  if (key === "done") return "good";
  return "muted";
}

export function bulkSelectionGuidance(selectedCount: number, eligibility: ReupQueueSelectionEligibility): string | null {
  if (selectedCount === 0) return null;
  if (primaryBulkEligibilityTotal(eligibility) > 0 || secondaryBulkEligibilityTotal(eligibility) > 0) {
    return `${eligibility.actionable} of ${selectedCount} selected can run a bulk action now.`;
  }
  return "None of the selected clips match a bulk action in their current state. Clear selection, change the status filter, or open Details on one tile.";
}

export type InspectorLifecycleActionGroup = "primary" | "neutral" | "danger" | "quiet";

const INSPECTOR_SPOTLIGHT_ACTIONS: ReupQueueAction[] = [
  "START_AUTO_PIPELINE",
  "START_PROCESSING",
  "RETRY",
  "HOLD",
  "RESUME",
  "MARK_MEDIA_READY",
  "MARK_COMPLETED"
];

/** Recover/forward first, pause next, dismiss last within a group. */
const INSPECTOR_LIFECYCLE_ACTION_ORDER: ReupQueueAction[] = [
  "RESUME",
  "START_AUTO_PIPELINE",
  "START_PROCESSING",
  "MARK_MEDIA_READY",
  "RETRY",
  "HOLD",
  "MARK_COMPLETED",
  "CANCEL",
  "MARK_BLOCKED",
  "DISMISS"
];

export function inspectorLifecycleActionGroup(action: ReupQueueAction): InspectorLifecycleActionGroup {
  if (action === "CANCEL" || action === "MARK_BLOCKED") return "danger";
  if (action === "DISMISS") return "quiet";
  if (action === "HOLD") return "neutral";
  return "primary";
}

export function pickInspectorSpotlightAction(actions: ReupQueueAvailableAction[]): ReupQueueAvailableAction | null {
  for (const action of INSPECTOR_SPOTLIGHT_ACTIONS) {
    const match = actions.find((entry) => entry.action === action);
    if (match) return match;
  }
  return null;
}

function sortInspectorLifecycleActions(actions: ReupQueueAvailableAction[]): ReupQueueAvailableAction[] {
  return [...actions].sort((left, right) => {
    const leftRank = INSPECTOR_LIFECYCLE_ACTION_ORDER.indexOf(left.action);
    const rightRank = INSPECTOR_LIFECYCLE_ACTION_ORDER.indexOf(right.action);
    const safeLeft = leftRank === -1 ? Number.MAX_SAFE_INTEGER : leftRank;
    const safeRight = rightRank === -1 ? Number.MAX_SAFE_INTEGER : rightRank;
    return safeLeft - safeRight;
  });
}

export function groupInspectorLifecycleActions(actions: ReupQueueAvailableAction[]): {
  primary: ReupQueueAvailableAction[];
  neutral: ReupQueueAvailableAction[];
  danger: ReupQueueAvailableAction[];
  quiet: ReupQueueAvailableAction[];
} {
  const primary: ReupQueueAvailableAction[] = [];
  const neutral: ReupQueueAvailableAction[] = [];
  const danger: ReupQueueAvailableAction[] = [];
  const quiet: ReupQueueAvailableAction[] = [];
  for (const entry of actions) {
    const group = inspectorLifecycleActionGroup(entry.action);
    if (group === "danger") danger.push(entry);
    else if (group === "quiet") quiet.push(entry);
    else if (group === "neutral") neutral.push(entry);
    else primary.push(entry);
  }
  return {
    primary: sortInspectorLifecycleActions(primary),
    neutral: sortInspectorLifecycleActions(neutral),
    danger: sortInspectorLifecycleActions(danger),
    quiet: sortInspectorLifecycleActions(quiet)
  };
}

export type InspectorWorkflowLink = {
  external?: boolean;
  href: string;
  label: string;
};

export function buildInspectorWorkflowLinks(item: ReupQueueItem): InspectorWorkflowLink[] {
  const exportPackageId = metadataString(item.metadata_json, "export_package_id");
  const publishHandoffId = metadataString(item.metadata_json, "publish_handoff_id");
  const sourceUrl = item.source_video?.source_url ?? null;
  const links: InspectorWorkflowLink[] = [];

  // Gate checkpoints with the same stage authority as worklist CTAs — avoid premature empty editors.
  // Skip Transcript chip when Open Transcript is already the details primary CTA.
  const transcriptHref = worklistTranscriptHref(item);
  if (transcriptHref && !queueTileTranscriptCta(item)) {
    links.push({ href: transcriptHref, label: "Transcript" });
  }
  if (canOpenFinalReview(item)) {
    links.push({ href: `/production/final-review/${item.source_video_id}`, label: "Final review" });
  }
  if (exportPackageId) links.push({ href: `/publishing/export-packages/${exportPackageId}`, label: "Export package" });
  if (publishHandoffId) links.push({ href: `/publishing/publish-handoffs/${publishHandoffId}`, label: "Handoff" });
  if (sourceUrl) links.push({ href: sourceUrl, label: "Source", external: true });
  return links;
}

/**
 * Details companions must follow stage intent — do not dump every API-allowed action.
 * Mark media ready is only a confirm/retry-analyze control, never a Transcript-ready CTA.
 */
export function shouldShowInspectorMarkMediaReady(item: ReupQueueItem): boolean {
  if (!item.available_actions.some((entry) => entry.action === "MARK_MEDIA_READY")) return false;
  if (isDownloadReadyForConfirm(item)) return true;
  if (isAnalyzeAudioFailed(item)) return true;
  return false;
}

export function filterInspectorCompanionActions(
  item: ReupQueueItem,
  actions: ReupQueueAvailableAction[]
): ReupQueueAvailableAction[] {
  return actions
    .filter((entry) => {
      // SET_AUTOMATION needs a mode argument; it has its own picker instead of a button.
      if (entry.action === "SET_AUTOMATION") return false;
      if (entry.action === "MARK_MEDIA_READY") return shouldShowInspectorMarkMediaReady(item);
      return true;
    })
    .map((entry) => {
      if (entry.action === "MARK_MEDIA_READY" && isAnalyzeAudioFailed(item)) {
        return { ...entry, label: "Retry analyze" };
      }
      return entry;
    });
}

/** Final review is useful once render exists, export stages imply it, or auto pipeline reached ready_final. */
function canOpenFinalReview(item: ReupQueueItem): boolean {
  if (!item.source_video_id) return false;
  if (isAutoPipelineReadyForFinal(item)) return true;
  if (item.render_output_id) return true;
  return item.status === "READY_TO_EXPORT" || isPastExport(item.status);
}

export function isTerminalQueueItem(item: ReupQueueItem): boolean {
  return item.status === "COMPLETED" || item.status === "CANCELLED";
}

export function resolveInitialReupQueueFilter(summary: ReupQueueStudioSummary): ReupQueueOperatorFilter {
  if (summary.needs_start > 0 || summary.download > 0) return "download";
  if (summary.transcript > 0) return "transcript";
  if (summary.render > 0) return "render";
  if (summary.export > 0) return "export";
  if (summary.attention > 0) return "attention";
  if (summary.handoff > 0) return "handoff";
  return "all";
}

export type PipelineStageState = "done" | "active" | "pending" | "failed";

export type PipelineStage = {
  key: string;
  label: string;
  state: PipelineStageState;
};

export function buildPipelineStages(item: ReupQueueItem): PipelineStage[] {
  const exportPackageId = metadataString(item.metadata_json, "export_package_id");
  const failed = item.status === "FAILED_NEEDS_ATTENTION" || isAnalyzeAudioFailed(item);
  return [
    pipelineStage("download", "Download", downloadStageState(item, failed)),
    pipelineStage("transcript", "Transcript", transcriptStageState(item, failed)),
    pipelineStage("render", "Render", renderStageState(item, failed)),
    pipelineStage("export", "Export", exportStageState(item, exportPackageId, failed))
  ];
}

/** Single readable focus line under the compact tile stepper (full labels stay in Details). */
export function pipelineTileFocusLabel(stages: PipelineStage[]): string {
  const failed = stages.find((stage) => stage.state === "failed");
  if (failed) return failed.label;
  const active = stages.find((stage) => stage.state === "active");
  if (active) return `Now: ${active.label}`;
  if (stages.length > 0 && stages.every((stage) => stage.state === "done")) return "Pipeline complete";
  const pending = stages.find((stage) => stage.state === "pending");
  return pending ? `Next: ${pending.label}` : "Pipeline";
}

export type PipelineStageInteraction =
  | { kind: "reveal-download"; title: string }
  | { kind: "href"; href: string; title: string }
  | { kind: "disabled"; title: string };

/** Gated tile stepper actions: reveal local download, or deep-link later checkpoints. */
export function pipelineStageInteraction(item: ReupQueueItem, stage: PipelineStage): PipelineStageInteraction {
  if (stage.key === "download") {
    if (stage.state === "failed") {
      return { kind: "disabled", title: "Download failed — open Details for context" };
    }
    const downloadReady =
      stage.state === "done"
      || Boolean(item.media_ready_at)
      || isDownloadReadyForConfirm(item)
      || item.metadata_json?.download_job_completed === true;
    if (downloadReady) {
      return { kind: "reveal-download", title: "Open downloaded video in Explorer" };
    }
    return { kind: "disabled", title: "Download is not ready yet" };
  }

  if (stage.key === "transcript") {
    const href = worklistTranscriptHref(item);
    if (href) return { kind: "href", href, title: "Open transcript editor" };
    return { kind: "disabled", title: transcriptStageDisabledTitle(item) };
  }

  if (stage.key === "render") {
    if (canOpenFinalReview(item)) {
      return {
        kind: "href",
        href: `/production/final-review/${item.source_video_id}`,
        title: "Open final review"
      };
    }
    return { kind: "disabled", title: "Render output is not ready yet" };
  }

  if (stage.key === "export") {
    const exportPackageId = metadataString(item.metadata_json, "export_package_id");
    if (exportPackageId) {
      return {
        kind: "href",
        href: `/publishing/export-packages/${exportPackageId}`,
        title: "Open export package"
      };
    }
    return { kind: "disabled", title: "Export package is not ready yet" };
  }

  return { kind: "disabled", title: "Not available" };
}

export function isAnalyzeAudioJob(item: ReupQueueItem): boolean {
  const type = (item.job_type ?? "").toUpperCase();
  if (type === "ANALYZE_AUDIO") return true;
  // Explicit non-analyze type (e.g. stale DOWNLOAD after pause) must not masquerade as analyze.
  if (type) return false;
  // After Confirm, linked job is audio analysis even if older payloads omit job_type.
  return item.status === "WAITING_FOR_METADATA" && Boolean(item.job_id);
}

function isActiveAnalyzeJobStatus(status: string | null | undefined): boolean {
  const normalized = (status ?? "").toUpperCase();
  return (
    normalized === "QUEUED"
    || normalized === "RUNNING"
    || normalized === "IN_PROGRESS"
    || normalized === "PROCESSING"
    || normalized === "RETRYABLE"
  );
}

/** Source-video dialogue fields written by ANALYZE_AUDIO (authority when linked job_id is stale). */
export function hasPersistedAnalyzeOutcome(item: ReupQueueItem): boolean {
  if (item.dialogue_phase != null && String(item.dialogue_phase).length > 0) return true;
  if (item.has_speech != null) return true;
  return typeof item.transcript_count === "number";
}

/** Short activity label for the linked worker job (analyze / download). */
export function linkedJobActivityLabel(item: ReupQueueItem): string | null {
  if (!item.job_id) return null;
  const status = (item.job_status ?? "").toUpperCase();
  if (isAnalyzeAudioJob(item)) {
    if (status === "QUEUED") return "Analyze queued";
    if (status === "RUNNING" || status === "IN_PROGRESS" || status === "PROCESSING") return "Analyzing";
    if (status === "RETRYABLE") return "Analyze retrying";
    if (status === "COMPLETED" || status === "SUCCEEDED") {
      return isNoDialogueAnalyzeResult(item) ? "No dialogue" : "Analyzed";
    }
    if (status === "FAILED") return "Analyze failed";
    if (status === "CANCELLED") return "Analyze cancelled";
    return "Analyze";
  }
  return null;
}

export function isAudioAnalysisCompleted(item: ReupQueueItem): boolean {
  if (isAnalyzeAudioJob(item)) {
    const status = (item.job_status ?? "").toUpperCase();
    if (status === "COMPLETED" || status === "SUCCEEDED") return true;
    // Active analyze wins over any leftover dialogue fields from a prior run.
    if (isActiveAnalyzeJobStatus(status)) return false;
  }
  // Stale/non-analyze linked job (pause/resume): trust persisted analyze outcome.
  return hasPersistedAnalyzeOutcome(item);
}

/** ANALYZE_AUDIO job finished in FAILED while the tile is still on Transcript stage. */
export function isAnalyzeAudioFailed(item: ReupQueueItem): boolean {
  if (item.status !== "WAITING_FOR_METADATA") return false;
  if (!isAnalyzeAudioJob(item)) return false;
  return (item.job_status ?? "").toUpperCase() === "FAILED";
}

/** Analyze failed because SOURCE_VIDEO_RAW / SOURCE_AUDIO_EXTRACT is missing. */
export function isMissingSourceAssetAnalyzeFailure(item: ReupQueueItem): boolean {
  if (!isAnalyzeAudioFailed(item)) return false;
  const blob = [
    item.job_error_code,
    item.job_error_message,
    item.last_error_code,
    item.last_error_message
  ]
    .filter((value): value is string => typeof value === "string" && value.length > 0)
    .join(" ")
    .toUpperCase();
  return (
    blob.includes("MISSING_SOURCE_ASSET")
    || blob.includes("SOURCE_AUDIO_EXTRACT")
    || blob.includes("SOURCE_VIDEO_RAW")
  );
}

/** Auto-pipeline step running after analyze: translation draft or Vietnamese TTS. */
export function activePipelineStepLabel(item: ReupQueueItem): string | null {
  const type = (item.job_type ?? "").toUpperCase();
  if (!isActiveAnalyzeJobStatus(item.job_status)) return null;
  if (type === "BUILD_TRANSLATION_DRAFT") return "Translating";
  if (type === "SYNTHESIZE_TTS") return "Voicing";
  if (type === "ANALYZE_OCR") return "Scanning OCR";
  if (type === "RENDER_PREVIEW") return "Previewing";
  if (type === "RENDER_FINAL") return "Rendering";
  return null;
}

/** Any worker job the queue is waiting on — drives the worklist label and auto-refresh. */
export function hasActivePipelineJob(item: ReupQueueItem): boolean {
  if (!item.job_id) return false;
  if (!isActiveAnalyzeJobStatus(item.job_status)) return false;
  const type = (item.job_type ?? "").toUpperCase();
  return (
    type === "ANALYZE_AUDIO"
    || type === "BUILD_TRANSLATION_DRAFT"
    || type === "SYNTHESIZE_TTS"
    || type === "ANALYZE_OCR"
    || type === "RENDER_PREVIEW"
    || type === "RENDER_FINAL"
    || isAnalyzeAudioJob(item)
  );
}

/** VAD measured speech the transcription could not decode — a human must judge this clip. */
export function isDialogueUncertain(item: ReupQueueItem): boolean {
  return item.dialogue_phase === "dialogue_uncertain";
}

export function dialogueUncertainHint(item: ReupQueueItem): string | null {
  if (!isDialogueUncertain(item)) return null;
  return "Speech detected but no transcript — review the clip, then re-run analyze or mark no dialogue";
}

/** ANALYZE_AUDIO finished with zero DialogueBeats (skip dubbing / caption-only video). */
export function isNoDialogueAnalyzeResult(item: ReupQueueItem): boolean {
  if (isDialogueUncertain(item)) return false;
  if (!isAudioAnalysisCompleted(item)) return false;
  if (item.dialogue_phase === "no_dialogue") return true;
  if (item.has_speech === false) return true;
  if (typeof item.transcript_count === "number" && item.transcript_count <= 0) return true;
  return false;
}

/** Operator-facing reason when the Transcript stepper is not clickable. */
export function transcriptStageDisabledTitle(item: ReupQueueItem): string {
  if (isNoDialogueAnalyzeResult(item)) {
    return "No spoken dialogue — skip dubbing";
  }
  if (isMissingSourceAssetAnalyzeFailure(item)) {
    return "Raw video missing — check Download, then Retry from start";
  }
  if (isAnalyzeAudioFailed(item)) {
    return "Analyze failed — Retry analyze after fixing the cause";
  }
  if (isAnalyzeAudioJob(item) && isActiveAnalyzeJobStatus(item.job_status)) {
    return "Analyze still running";
  }
  return "Transcript is not ready yet";
}

/** Worklist deep-link to Checkpoint #1 only when analyze produced spoken beats. */
export function worklistTranscriptHref(item: ReupQueueItem): string | null {
  if (!item.source_video_id || !isAudioAnalysisCompleted(item)) return null;
  if (isNoDialogueAnalyzeResult(item) || isDialogueUncertain(item)) return null;
  return `/production/transcript-editor/${item.source_video_id}`;
}

/** Gallery primary CTA when Transcript editor is ready (stepper stays as secondary deep-link). */
export function queueTileTranscriptCta(item: ReupQueueItem): { href: string; label: string } | null {
  const href = worklistTranscriptHref(item);
  if (!href) return null;
  return { href, label: "Open Transcript" };
}

/** Compact gallery failure copy — long recovery stays in title/tooltip / Details. */
export type QueueTileFailureAlert = {
  detail: string;
  message: string;
};

export function queueTileFailureAlert(item: ReupQueueItem): QueueTileFailureAlert | null {
  if (isMissingSourceAssetAnalyzeFailure(item)) {
    return {
      message: "Raw video missing",
      detail: "Click Download to check the file. If missing: Retry from start → Start processing → Mark media ready."
    };
  }
  if (isAnalyzeAudioFailed(item)) {
    const detail =
      item.job_error_message?.trim()
      || item.last_error_message?.trim()
      || "Open Details for context, then Retry analyze.";
    return { message: "Analyze failed", detail };
  }
  const downloadError = downloadJobErrorLine(item);
  if (downloadError) {
    return {
      message: downloadError.length > 72 ? `${downloadError.slice(0, 69)}…` : downloadError,
      detail: downloadError
    };
  }
  return null;
}

/** Thumbnail bottom strip — skip when message duplicates the stage chip. */
export function queueTileFailureStrip(item: ReupQueueItem): QueueTileFailureAlert | null {
  const alert = queueTileFailureAlert(item);
  if (!alert) return null;
  const normalize = (value: string) => value.trim().toLowerCase().replace(/\s+/g, " ");
  if (normalize(alert.message) === normalize(queueStageLabel(item))) return null;
  return alert;
}

/** Visible next-step copy when gallery primary CTA is wait/inspect (not Confirm/Start). */
export function queueTileNextStepHint(item: ReupQueueItem): string | null {
  // Failure tiles use queueTileFailureAlert — avoid stacked error + long hint.
  if (queueTileFailureAlert(item)) return null;
  if (isAwaitingPipelineSlot(item)) {
    return "Queued for auto — starts automatically when a slot frees";
  }
  if (item.status === "WAITING_FOR_MEDIA") {
    if (isDownloadReadyForConfirm(item)) return null;
    if (isProgressPaused(item)) return "Paused — Resume from Details";
    if (hasActiveDownloadJob(item)) {
      const jobStatus = (item.job_status ?? "").toUpperCase();
      if (jobStatus === "RUNNING" || jobStatus === "IN_PROGRESS" || jobStatus === "PROCESSING") {
        return "Downloading — wait, then Confirm ready";
      }
      return "Download queued — worker will start soon";
    }
    return "Waiting for download job — open Details if stuck";
  }
  if (item.status !== "WAITING_FOR_METADATA") return null;
  if (isAutoPipelineReadyForFinal(item)) return "Auto done — Open Final Review for OCR/Render";
  const autoChip = pipelineStepChipLabel(item);
  if (autoChip && !isAutoPipelineReadyForFinal(item)) {
    if (item.held_at || item.metadata_json?.pipeline_hold === true) {
      return "Auto paused — Resume from Details or edit in Transcript";
    }
    const step = getPipelineStep(item);
    if (step === "translate" || step === "tts") {
      return `${autoChip} — open Transcript to review anytime`;
    }
    const activeStep = activePipelineStepLabel(item);
    const jobStatus = (item.job_status ?? "").toUpperCase();
    if (
      activeStep
      && typeof item.job_progress_percent === "number"
      && (jobStatus === "RUNNING" || jobStatus === "IN_PROGRESS" || jobStatus === "PROCESSING")
    ) {
      return `${activeStep} — ${clampJobProgressPercent(item.job_progress_percent)}%`;
    }
    return `${autoChip} — waiting for worker`;
  }
  if (worklistTranscriptHref(item)) return null;
  if (isNoDialogueAnalyzeResult(item)) return worklistNoDialogueHint(item);
  if (isAnalyzeAudioJob(item) && isActiveAnalyzeJobStatus(item.job_status)) {
    return "Analyze still running — Transcript opens when done";
  }
  return "Waiting for audio analysis";
}

/** Secondary note when analyze found no speech — do not open empty Transcript. */
export function worklistNoDialogueHint(item: ReupQueueItem): string | null {
  if (!isNoDialogueAnalyzeResult(item)) return null;
  return "Skip dubbing — caption/OCR later";
}

/** Keep Open job while analyze runs; hide once Transcript becomes the CTA. */
export function shouldShowWorklistOpenJobLink(item: ReupQueueItem): boolean {
  if (!item.job_id || item.status !== "WAITING_FOR_METADATA") return false;
  return !isAudioAnalysisCompleted(item);
}

export function markMediaReadyNotice(item: ReupQueueItem): string {
  const statusLabel = operatorStatusLabel(item.status);
  if (!item.job_id) {
    return `Mark media ready applied. Current state: ${statusLabel}.`;
  }
  const jobType = (item.job_type ?? "ANALYZE_AUDIO").toUpperCase();
  const jobStatus = item.job_status ?? "QUEUED";
  return (
    `Mark media ready applied → ${statusLabel}. `
    + `${jobType} ${jobStatus} (${item.job_id.slice(0, 8)}). `
    + "Check Pipeline for job progress (Completed jobs still appear in the list)."
  );
}

export function formatJobChipLabel(item: ReupQueueItem): string | null {
  if (!item.job_id) return null;
  // Stage chip already says "Confirm ready" once download finished.
  if (isDownloadReadyForConfirm(item)) return null;
  const analyzeLabel = linkedJobActivityLabel(item);
  if (analyzeLabel) {
    if (analyzeLabel === "Analyzed") return "Audio analyzed";
    if (analyzeLabel === "No dialogue") return "No dialogue";
    return analyzeLabel;
  }
  const status = (item.job_status ?? "").toUpperCase();
  // Avoid duplicate orange chips: stage label covers in-flight download states.
  if (
    status === "RUNNING"
    || status === "IN_PROGRESS"
    || status === "PROCESSING"
    || status === "QUEUED"
    || status === "RETRYABLE"
  ) {
    return null;
  }
  if (status === "FAILED") {
    // Queue stage owns the failure chip when item is already FAILED_NEEDS_ATTENTION.
    if (item.status === "FAILED_NEEDS_ATTENTION") return null;
    return "Download failed";
  }
  if (status === "CANCELLED") return "Job cancelled";
  if (status === "COMPLETED" || status === "SUCCEEDED") return null;
  const fallback = (item.job_status ?? "queued").toLowerCase().replace(/_/g, " ");
  return `Job ${fallback}`;
}

export function jobChipTone(item: ReupQueueItem): "good" | "warn" | "danger" | "muted" {
  const status = (item.job_status ?? "").toUpperCase();
  if (status === "FAILED" || status === "CANCELLED") return "danger";
  if (status === "RUNNING" || status === "IN_PROGRESS" || status === "PROCESSING" || status === "RETRYABLE") return "warn";
  if (status === "COMPLETED" || status === "SUCCEEDED") return "good";
  return "muted";
}

export function hasActiveDownloadJob(item: ReupQueueItem): boolean {
  if (!item.job_id) return false;
  if (isDownloadReadyForConfirm(item)) return false;
  const status = (item.job_status ?? "").toUpperCase();
  return status === "QUEUED" || status === "RUNNING" || status === "RETRYABLE" || status === "IN_PROGRESS" || status === "PROCESSING";
}

export function isProgressPaused(item: ReupQueueItem): boolean {
  return Boolean(item.held_at) && (item.status === "WAITING_FOR_MEDIA" || item.status === "WAITING_FOR_METADATA" || item.status === "PROCESSING");
}

export function downloadJobProgressPercent(item: ReupQueueItem): number | null {
  if (isProgressPaused(item)) return null;
  if (!hasActiveDownloadJob(item)) return null;
  const status = (item.job_status ?? "").toUpperCase();
  if (status !== "RUNNING" && status !== "IN_PROGRESS" && status !== "PROCESSING") return null;
  return clampJobProgressPercent(item.job_progress_percent);
}

export function downloadJobErrorLine(item: ReupQueueItem): string | null {
  const status = (item.job_status ?? "").toUpperCase();
  const failed = item.status === "FAILED_NEEDS_ATTENTION" || status === "FAILED";
  if (!failed) return null;
  const message = item.job_error_message || item.last_error_message || item.job_error_code || item.last_error_code;
  if (!message) return "Download failed. Open Details for more context.";
  const trimmed = message.trim();
  return trimmed.length > 120 ? `${trimmed.slice(0, 117)}…` : trimmed;
}

function clampJobProgressPercent(value: number | null | undefined): number {
  if (typeof value !== "number" || Number.isNaN(value)) return 0;
  return Math.max(0, Math.min(100, Math.round(value)));
}

function pipelineStage(key: string, label: string, state: PipelineStageState): PipelineStage {
  return { key, label, state };
}

function downloadStageState(item: ReupQueueItem, failed: boolean): PipelineStageState {
  if (failed && item.status === "FAILED_NEEDS_ATTENTION" && !item.media_ready_at) return "failed";
  // Needs-start: chip/CTA own the truth — do not mark Download done from stale media_ready_at.
  if (item.status === "READY_FOR_PROCESSING") return "pending";
  if (item.media_ready_at || item.status === "WAITING_FOR_METADATA" || isPastProduction(item.status)) return "done";
  if (item.status === "WAITING_FOR_MEDIA" || item.status === "PROCESSING" || item.job_id) return "active";
  return "pending";
}

function transcriptStageState(item: ReupQueueItem, failed: boolean): PipelineStageState {
  if (isAnalyzeAudioFailed(item)) return "failed";
  if (failed && item.status === "WAITING_FOR_METADATA") return "failed";
  if (item.media_prep_status === "READY_FOR_EXPORT" || isPastProduction(item.status)) return "done";
  if (item.status === "WAITING_FOR_METADATA") return "active";
  return "pending";
}

function renderStageState(item: ReupQueueItem, failed: boolean): PipelineStageState {
  if (item.render_output_id || item.status === "READY_TO_EXPORT" || isPastExport(item.status)) return "done";
  if (item.status === "PROCESSING" && item.media_prep_status === "READY_FOR_EXPORT") return "active";
  if (failed && item.status === "PROCESSING") return "failed";
  return "pending";
}

function exportStageState(item: ReupQueueItem, exportPackageId: string | null, failed: boolean): PipelineStageState {
  if (exportPackageId || item.status === "EXPORT_PACKAGE_CREATED" || isPastHandoff(item.status)) return "done";
  if (item.status === "READY_TO_EXPORT") return "active";
  if (failed && item.status === "READY_TO_EXPORT") return "failed";
  return "pending";
}

function isPastProduction(status: ReupQueueItem["status"]): boolean {
  return status === "READY_TO_EXPORT" || status === "EXPORT_PACKAGE_CREATED" || status === "READY_TO_PUBLISH" || status === "PUBLISH_HANDOFF_CREATED" || status === "COMPLETED";
}

function isPastExport(status: ReupQueueItem["status"]): boolean {
  return status === "EXPORT_PACKAGE_CREATED" || status === "READY_TO_PUBLISH" || status === "PUBLISH_HANDOFF_CREATED" || status === "COMPLETED";
}

function isPastHandoff(status: ReupQueueItem["status"]): boolean {
  return status === "PUBLISH_HANDOFF_CREATED" || status === "COMPLETED";
}

export function isLikelyEligibleForBatch(item: ReupQueueItem, action: ReupQueueBatchAction): boolean {
  if (action === "CREATE_EXPORT_PACKAGE" || action === "CREATE_PUBLISH_HANDOFF") {
    return item.status === "READY_TO_EXPORT" && item.media_prep_status === "READY_FOR_EXPORT";
  }
  if (action === "MARK_MEDIA_READY") {
    return item.available_actions.some((available) => available.action === "MARK_MEDIA_READY");
  }
  return item.available_actions.some((available) => available.action === action);
}

export function eligibleBatchCount(items: ReupQueueItem[], action: ReupQueueBatchAction): number {
  return items.filter((item) => isLikelyEligibleForBatch(item, action)).length;
}

/** Mirrors API `reup_queue_start_processing_batch_limit` default (Playwright download safety). */
export const REUP_QUEUE_START_PROCESSING_BATCH_LIMIT = 30;

export function capStartProcessingBatchIds(
  itemIds: string[],
  limit: number = REUP_QUEUE_START_PROCESSING_BATCH_LIMIT
): { acceptedIds: string[]; overflowCount: number } {
  if (limit < 1) {
    throw new Error("start processing batch limit must be >= 1");
  }
  if (itemIds.length <= limit) {
    return { acceptedIds: [...itemIds], overflowCount: 0 };
  }
  return { acceptedIds: itemIds.slice(0, limit), overflowCount: itemIds.length - limit };
}

export function startProcessingBatchCapNotice(acceptedCount: number, overflowCount: number, limit: number): string {
  return `Starting ${acceptedCount} of ${acceptedCount + overflowCount} ready clip(s) (safe batch limit ${limit}). Start the rest after this batch finishes.`;
}

export function cancellableReupQueueItems(items: ReupQueueItem[]): ReupQueueItem[] {
  return items.filter((item) => isLikelyEligibleForBatch(item, "CANCEL"));
}

export function dismissableReupQueueItems(items: ReupQueueItem[]): ReupQueueItem[] {
  return items.filter((item) => isLikelyEligibleForBatch(item, "DISMISS"));
}

export function clearablePurgeReupQueueItems(items: ReupQueueItem[]): ReupQueueItem[] {
  return items.filter(isOperatorClearableQueueItem);
}

export function supportsBulkCancelVisibleScope(operatorFilter: ReupQueueOperatorFilter): boolean {
  return operatorFilter !== "done";
}

export function supportsBulkDismissVisibleScope(operatorFilter: ReupQueueOperatorFilter): boolean {
  return operatorFilter === "done" || operatorFilter === "attention";
}

export function supportsBulkPurgeVisibleScope(operatorFilter: ReupQueueOperatorFilter): boolean {
  return operatorFilter === "done" || operatorFilter === "attention";
}

export function bulkDismissConfirmMessage(count: number, operatorFilter: ReupQueueOperatorFilter): string {
  const filterLabel = REUP_QUEUE_STATUS_FILTERS.find((entry) => entry.key === operatorFilter)?.label ?? "current view";
  return `Clear ${count} clip(s) from ${filterLabel}? They will be hidden from Reup Queue. Source media stays intact and clips can be re-sent from Review Board.`;
}

export function bulkPurgeConfirmMessage(count: number, operatorFilter: ReupQueueOperatorFilter): string {
  const filterLabel = REUP_QUEUE_STATUS_FILTERS.find((entry) => entry.key === operatorFilter)?.label ?? "current view";
  return `Permanently delete ${count} queue record(s) in ${filterLabel}? This cannot be undone. Source media and Review Board candidates are not deleted.`;
}

export function bulkCancelConfirmMessage(count: number, operatorFilter: ReupQueueOperatorFilter): string {
  const filterLabel = REUP_QUEUE_STATUS_FILTERS.find((entry) => entry.key === operatorFilter)?.label ?? "current view";
  return `Cancel ${count} clip(s) in ${filterLabel}? They will move to Done and can be re-sent from Review Board.`;
}

export function formatBulkBarScopeMeta(actionableVisibleCount: number, visibleCount: number, selectedCount: number): string {
  if (selectedCount > 0) return `${selectedCount} selected`;
  return `${actionableVisibleCount}/${visibleCount} actionable`;
}

export function formatBatchResultSummary(result: BatchOperationResponse): string {
  return `${result.succeeded_count}/${result.requested_count} succeeded · ${result.skipped_count} skipped · ${result.failed_count} failed`;
}

export function queueStageLabel(item: ReupQueueItem): string {
  if (item.status === "READY_TO_EXPORT") return "Ready to export";
  if (item.status === "EXPORT_PACKAGE_CREATED") return "Export package created";
  if (item.status === "READY_TO_PUBLISH") return "Ready for handoff";
  if (item.status === "PUBLISH_HANDOFF_CREATED") return "Handoff created";
  if (item.status === "READY_FOR_PROCESSING") return "Needs start";
  if (isProgressPaused(item)) return "Paused";
  if (item.status === "WAITING_FOR_MEDIA") {
    if (isDownloadReadyForConfirm(item)) return "Confirm ready";
    const jobStatus = (item.job_status ?? "").toUpperCase();
    if (jobStatus === "RUNNING" || jobStatus === "IN_PROGRESS" || jobStatus === "PROCESSING") return "Downloading";
    if (jobStatus === "QUEUED") return "Queued";
    if (jobStatus === "RETRYABLE") return "Retrying";
    return "Waiting for media";
  }
  if (item.status === "WAITING_FOR_METADATA") {
    const pipelineStep = activePipelineStepLabel(item);
    if (pipelineStep) return pipelineStep;
    if (isNoDialogueAnalyzeResult(item)) return "No dialogue";
    if (isAnalyzeAudioFailed(item)) return "Analyze failed";
    if (isAnalyzeAudioJob(item) && isActiveAnalyzeJobStatus(item.job_status)) return "Analyzing";
    if (worklistTranscriptHref(item)) return "Transcript ready";
    return "Transcript";
  }
  if (item.status === "PROCESSING") return "Processing";
  if (item.status === "FAILED_NEEDS_ATTENTION") {
    return isDownloadFailureAttention(item) ? "Download failed" : "Needs attention";
  }
  if (item.status === "COMPLETED") return "Completed";
  if (item.status === "CANCELLED") return "Cancelled";
  return operatorStatusLabel(item.status);
}

/** Short labels for dense Worklist rail — align with Pipeline stage chips; Gallery keeps queueStageLabel. */
export function worklistStageLabel(item: ReupQueueItem): string {
  if (isProgressPaused(item)) return "Paused";
  if (isDialogueUncertain(item)) return "Check dialogue";
  if (item.status === "READY_FOR_PROCESSING" || item.status === "WAITING_FOR_MEDIA") return "Download";
  if (item.status === "WAITING_FOR_METADATA") {
    const pipelineStep = activePipelineStepLabel(item);
    if (pipelineStep) return pipelineStep;
    if (isNoDialogueAnalyzeResult(item)) return "No dialogue";
    if (isAnalyzeAudioFailed(item)) return "Analyze failed";
    if (isAnalyzeAudioJob(item) && isActiveAnalyzeJobStatus(item.job_status)) return "Analyzing";
    if (worklistTranscriptHref(item)) return "Transcript ready";
    return "Transcript";
  }
  if (item.status === "PROCESSING") return "Render";
  if (item.status === "FAILED_NEEDS_ATTENTION") {
    return isDownloadFailureAttention(item) ? "Failed" : "Attention";
  }
  if (item.status === "READY_TO_EXPORT" || item.status === "EXPORT_PACKAGE_CREATED") return "Export";
  if (item.status === "READY_TO_PUBLISH" || item.status === "PUBLISH_HANDOFF_CREATED") return "Handoff";
  if (item.status === "COMPLETED") return "Done";
  if (item.status === "CANCELLED") return "Cancelled";
  return queueStageLabel(item);
}

/** Worklist status color: active=blue download, good=ready, muted=paused. Gallery keeps queueStageTone. */
export type WorklistStageTone = "active" | "good" | "muted" | "danger" | "warn";

export function worklistStageTone(item: ReupQueueItem): WorklistStageTone {
  if (isProgressPaused(item)) return "muted";
  if (isDialogueUncertain(item)) return "warn";
  if (isDownloadReadyForConfirm(item)) return "good";
  if (item.status === "WAITING_FOR_MEDIA" && hasActiveDownloadJob(item)) return "active";
  if (item.status === "WAITING_FOR_METADATA") {
    const status = (item.job_status ?? "").toUpperCase();
    if (status === "FAILED") return "danger";
    if (status === "COMPLETED" || status === "SUCCEEDED") {
      return isNoDialogueAnalyzeResult(item) ? "muted" : "good";
    }
    if (status === "RUNNING" || status === "QUEUED" || status === "RETRYABLE" || status === "IN_PROGRESS") return "active";
    return "warn";
  }
  if (item.status === "FAILED_NEEDS_ATTENTION") return "danger";
  if (item.status === "CANCELLED") return "muted";
  const tone = queueStageTone(item);
  if (tone === "good") return "good";
  if (tone === "danger") return "danger";
  if (tone === "muted") return "muted";
  return "warn";
}

function isDownloadFailureAttention(item: ReupQueueItem): boolean {
  const jobStatus = (item.job_status ?? "").toUpperCase();
  if (jobStatus === "FAILED") return true;
  if (item.job_error_code || item.job_error_message) return true;
  const code = (item.last_error_code ?? "").toUpperCase();
  return code.includes("DOWNLOAD") || code.startsWith("DOUYIN_");
}

export function queueStageTone(item: ReupQueueItem): "good" | "warn" | "danger" | "muted" {
  if (item.status === "READY_FOR_PROCESSING" || item.status === "READY_TO_EXPORT" || item.status === "READY_TO_PUBLISH") return "good";
  if (item.status === "EXPORT_PACKAGE_CREATED" || item.status === "PUBLISH_HANDOFF_CREATED" || item.status === "COMPLETED") return "good";
  if (item.status === "FAILED_NEEDS_ATTENTION") return "danger";
  if (item.status === "CANCELLED") return "muted";
  if (isDownloadReadyForConfirm(item)) return "good";
  if (item.status === "WAITING_FOR_METADATA") {
    if (isNoDialogueAnalyzeResult(item)) return "muted";
    if (isAnalyzeAudioFailed(item)) return "danger";
    if (worklistTranscriptHref(item)) return "good";
    return "warn";
  }
  if (item.status === "WAITING_FOR_MEDIA" || item.status === "PROCESSING") return "warn";
  return "muted";
}

export function itemTitle(item: ReupQueueItem): string {
  return item.source_video?.caption || item.source_video?.source_video_external_id || `Candidate ${item.video_candidate_id.slice(0, 8)}`;
}

export function metadataString(metadata: Record<string, unknown> | null | undefined, key: string): string | null {
  const value = metadata?.[key];
  return typeof value === "string" && value.length > 0 ? value : null;
}

function metadataRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : null;
}

function metadataNumber(...values: unknown[]): number | null {
  for (const value of values) {
    if (typeof value === "number" && Number.isFinite(value) && value >= 0) return value;
  }
  return null;
}

function queueTileSourceMetadata(item: ReupQueueItem): Record<string, unknown> | null {
  const metadata = metadataRecord(item.source_video?.metadata_json);
  if (!metadata) return null;
  return metadataRecord(metadata.source_metadata) ?? metadata;
}

function formatQueueViewsNumber(value: number): string {
  return new Intl.NumberFormat("en", {
    notation: value >= 10000 ? "compact" : "standard",
    maximumFractionDigits: value >= 10000 ? 1 : 0
  }).format(value);
}

export function queueTileThumbnailUrl(item: ReupQueueItem): string | null {
  return (
    metadataString(item.source_video?.metadata_json ?? null, "thumbnail_url")
    ?? metadataString(item.metadata_json, "thumbnail_url")
  );
}

export function queueTilePostedLabel(item: ReupQueueItem): string {
  return (
    metadataString(item.source_video?.metadata_json ?? null, "posted_display")
    ?? metadataString(item.source_video?.metadata_json ?? null, "posted_text")
    ?? (item.source_video?.posted_at ? formatDateTime(item.source_video.posted_at) : "—")
  );
}

export function queueTileDurationLabel(item: ReupQueueItem): string {
  const durationText = metadataString(item.source_video?.metadata_json ?? null, "duration_text");
  if (durationText) return durationText;
  const seconds = item.source_video?.duration_seconds;
  if (seconds == null) return "—";
  const mins = Math.floor(seconds / 60);
  const secs = seconds % 60;
  return `${mins}:${String(secs).padStart(2, "0")}`;
}

export function queueTileViewsLabel(item: ReupQueueItem): string {
  const metadata = metadataRecord(item.source_video?.metadata_json);
  const sourceMetadata = queueTileSourceMetadata(item);
  const display = metadataString(sourceMetadata, "estimated_views_display")
    ?? metadataString(sourceMetadata, "estimated_views_text")
    ?? metadataString(metadata, "estimated_views_display")
    ?? metadataString(metadata, "view_count_text");
  if (display) return display;

  const min = metadataNumber(
    sourceMetadata?.estimated_views_min,
    metadata?.estimated_views_min
  );
  const max = metadataNumber(
    sourceMetadata?.estimated_views_max,
    metadata?.estimated_views_max
  );
  if (min !== null && max !== null) {
    return min === max
      ? formatQueueViewsNumber(min)
      : `${formatQueueViewsNumber(min)}–${formatQueueViewsNumber(max)}`;
  }

  const mid = metadataNumber(
    sourceMetadata?.estimated_views_mid,
    metadata?.estimated_views_mid
  );
  if (mid !== null) return formatQueueViewsNumber(mid);

  const likeCount = metadataNumber(
    sourceMetadata?.like_count,
    metadata?.like_count
  );
  if (likeCount !== null && likeCount > 0) {
    const low = Math.round(likeCount * 20);
    const high = Math.round(likeCount * 100);
    return `${formatQueueViewsNumber(low)}–${formatQueueViewsNumber(high)}`;
  }

  return "—";
}

export function queueTileScoreBadge(item: ReupQueueItem): OperatorTileScoreBadge {
  return getOperatorTileScoreBadge(buildCapturedItemFromReupQueueItem(item));
}

export function queueTileMetric(
  metadata: Record<string, unknown> | null | undefined,
  textKey: string,
  countKey: string
): string {
  const count = metadata?.[countKey];
  const text = metadataString(metadata, textKey);
  return formatExactEngagementMetric(typeof count === "number" ? count : null, text);
}

export type QueueInspectorEngagementStat = {
  icon: "perf-views" | "perf-engagement" | "stat-comments" | "stat-shares";
  label: string;
  value: string;
};

/** Source social metrics for Details — keep gallery tiles production-focused. */
export function buildQueueInspectorEngagementStats(item: ReupQueueItem): QueueInspectorEngagementStat[] {
  return [
    { icon: "perf-views", label: "Est. Views", value: queueTileViewsLabel(item) },
    { icon: "perf-engagement", label: "Likes", value: queueInspectorEngagementMetric(item, "like_count_text", "like_count") },
    { icon: "stat-comments", label: "Comments", value: queueInspectorEngagementMetric(item, "comment_count_text", "comment_count") },
    { icon: "stat-shares", label: "Shares", value: queueInspectorEngagementMetric(item, "share_count_text", "share_count") }
  ];
}

function queueInspectorEngagementMetric(item: ReupQueueItem, textKey: string, countKey: string): string {
  const nested = queueTileSourceMetadata(item);
  const top = metadataRecord(item.source_video?.metadata_json);
  const fromNested = queueTileMetric(nested, textKey, countKey);
  if (fromNested !== "—") return fromNested;
  return queueTileMetric(top, textKey, countKey);
}

export function primaryQueueAction(item: ReupQueueItem): ReupQueueAction | ReupQueueBatchAction | "inspect" | null {
  if (item.available_actions.some((entry) => entry.action === "START_AUTO_PIPELINE")) return "START_AUTO_PIPELINE";
  if (item.available_actions.some((entry) => entry.action === "START_PROCESSING")) return "START_PROCESSING";
  if (item.status === "READY_TO_EXPORT" && item.media_prep_status === "READY_FOR_EXPORT") return "CREATE_EXPORT_PACKAGE";
  if (item.status === "READY_TO_PUBLISH") return "CREATE_PUBLISH_HANDOFF";
  if (item.available_actions.some((entry) => entry.action === "RETRY")) return "RETRY";
  if (item.status === "FAILED_NEEDS_ATTENTION") return "inspect";
  // Resume when paused OR idle download restart (API offers RESUME without Pause first).
  if (item.available_actions.some((entry) => entry.action === "RESUME")) {
    return "RESUME";
  }
  if (isAutoPipelineReadyForFinal(item)) return "inspect";
  if (isAnalyzeAudioFailed(item) && item.available_actions.some((entry) => entry.action === "MARK_MEDIA_READY")) {
    return "MARK_MEDIA_READY";
  }
  if (
    isDownloadReadyForConfirm(item) &&
    !isAutoPipeline(item) &&
    item.available_actions.some((entry) => entry.action === "MARK_MEDIA_READY")
  ) {
    return "MARK_MEDIA_READY";
  }
  if (hasActiveDownloadJob(item) && item.available_actions.some((entry) => entry.action === "HOLD")) {
    return "HOLD";
  }
  if (
    item.status === "WAITING_FOR_MEDIA"
    || item.status === "WAITING_FOR_METADATA"
    || item.status === "PROCESSING"
  ) {
    return "inspect";
  }
  // Terminal rows: Details is the main CTA; Dismiss is a quiet companion (not green forward).
  if (item.status === "CANCELLED" || item.status === "COMPLETED") return "inspect";
  return item.available_actions[0]?.action ?? "inspect";
}

/** Quiet dismiss for completed/cancelled tiles (pair with Details). */
export function terminalQueueDismissAction(item: ReupQueueItem): "DISMISS" | null {
  if (item.status !== "CANCELLED" && item.status !== "COMPLETED") return null;
  return item.available_actions.some((entry) => entry.action === "DISMISS") ? "DISMISS" : null;
}

export type QueueTilePrimaryButtonTone = "forward" | "recover" | "quiet" | "inspect";

export function queueTilePrimaryButtonTone(item: ReupQueueItem): QueueTilePrimaryButtonTone {
  const action = primaryQueueAction(item);
  if (action === "inspect") return "inspect";
  if (action === "DISMISS" || action === "CANCEL" || action === "HOLD") return "quiet";
  if (action === "RETRY" || action === "RESUME") return "recover";
  if (
    action === "START_PROCESSING"
    || action === "START_AUTO_PIPELINE"
    || action === "MARK_MEDIA_READY"
    || action === "CREATE_EXPORT_PACKAGE"
    || action === "CREATE_PUBLISH_HANDOFF"
  ) {
    return "forward";
  }
  return "forward";
}

/** Green primary with → is only for forward workflow steps. */
export function queueTileShowsForwardArrow(item: ReupQueueItem): boolean {
  return queueTilePrimaryButtonTone(item) === "forward";
}

/** True when DOWNLOAD_VIDEO finished and operator can confirm via Mark media ready. */
export function isDownloadReadyForConfirm(item: ReupQueueItem): boolean {
  if (item.status !== "WAITING_FOR_MEDIA" && item.status !== "PROCESSING") return false;
  if (item.metadata_json?.download_job_completed === true) return true;
  if (item.job_status === "COMPLETED") return true;
  return false;
}

export type ReupPipelineMode = "manual" | "auto_to_tts" | "auto_to_render";
export type ReupPipelineStep =
  | "download"
  | "analyze_audio"
  | "translate"
  | "tts"
  | "ocr"
  | "render"
  | "ready_final"
  | "needs_attention";

export function getPipelineMode(item: ReupQueueItem): ReupPipelineMode {
  const mode = item.metadata_json?.pipeline_mode;
  if (mode === "auto_to_tts" || mode === "auto_to_render" || mode === "manual") return mode;
  return "manual";
}

export function isAutoPipeline(item: ReupQueueItem): boolean {
  const mode = getPipelineMode(item);
  return mode === "auto_to_tts" || mode === "auto_to_render";
}

export function getPipelineStep(item: ReupQueueItem): ReupPipelineStep | null {
  const step = item.metadata_json?.pipeline_step;
  if (typeof step !== "string" || !step) return null;
  return step as ReupPipelineStep;
}

export type AutomationModeOption = {
  mode: ReupPipelineMode;
  label: string;
  description: string;
};

/** Full auto first: it is the default path and what most items should stay on. */
const AUTOMATION_MODE_OPTIONS: AutomationModeOption[] = [
  {
    mode: "auto_to_render",
    label: "Full auto",
    description: "Run every stage through render, then just review the finished video"
  },
  {
    mode: "auto_to_tts",
    label: "Auto → TTS",
    description: "Stop after voice-over so you can edit before OCR and render"
  },
  {
    mode: "manual",
    label: "Manual",
    description: "Stop advancing automatically; you drive each stage from here"
  }
];

export function automationModeOptions(): AutomationModeOption[] {
  return AUTOMATION_MODE_OPTIONS;
}

export function currentAutomationMode(item: ReupQueueItem): ReupPipelineMode {
  return getPipelineMode(item);
}

export function canChangeAutomation(item: ReupQueueItem): boolean {
  return item.available_actions.some((entry) => entry.action === "SET_AUTOMATION");
}

export function isAutoPipelineReadyForFinal(item: ReupQueueItem): boolean {
  return isAutoPipeline(item) && getPipelineStep(item) === "ready_final";
}

export function isAutoPipelineNeedsAttention(item: ReupQueueItem): boolean {
  return (
    getPipelineStep(item) === "needs_attention" ||
    (isAutoPipeline(item) && item.status === "FAILED_NEEDS_ATTENTION")
  );
}

/** True when the work-in-progress cap accepted this clip but has not started it yet. */
export function isAwaitingPipelineSlot(item: ReupQueueItem): boolean {
  return item.metadata_json?.pipeline_awaiting_slot === true;
}

export function pipelineStepChipLabel(item: ReupQueueItem): string | null {
  if (!isAutoPipeline(item)) return null;
  if (item.held_at || item.metadata_json?.pipeline_hold === true) return "Auto · Paused";
  if (isAwaitingPipelineSlot(item)) return "Auto · Queued";
  const step = getPipelineStep(item);
  if (step === "download") return "Auto · Download";
  if (step === "analyze_audio") return "Auto · ASR";
  if (step === "translate") return "Auto · Translate";
  if (step === "tts") return "Auto · TTS";
  if (step === "ocr") return "Auto · OCR";
  if (step === "render") return "Auto · Render";
  if (step === "ready_final") return "Auto · Ready for Final";
  if (step === "needs_attention") return "Auto · Needs attention";
  return "Auto pipeline";
}

export function pipelineRecipeChipLabel(item: ReupQueueItem): string | null {
  const raw = item.metadata_json?.pipeline_recipe_lock;
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) return null;
  const release = (raw as Record<string, unknown>).release_label;
  const sha = (raw as Record<string, unknown>).recipe_sha256;
  if (typeof release !== "string" || !release.trim()) return null;
  if (typeof sha !== "string" || !/^[a-f0-9]{64}$/i.test(sha)) return null;
  return `${release} locked · ${sha.slice(0, 8)}`;
}

export function worklistFinalReviewHref(item: ReupQueueItem): string | null {
  if (!item.source_video_id) return null;
  if (isAutoPipelineReadyForFinal(item)) return `/production/final-review/${item.source_video_id}`;
  return null;
}

export function primaryQueueActionLabel(item: ReupQueueItem): string {
  const action = primaryQueueAction(item);
  if (action === "inspect") {
    if (isAutoPipelineReadyForFinal(item)) return "Open Final Review";
    return "Details";
  }
  if (action === "CREATE_EXPORT_PACKAGE") return "Create export package";
  if (action === "CREATE_PUBLISH_HANDOFF") return "Create publish handoff";
  if (action === "START_AUTO_PIPELINE") return "Start auto";
  if (action === "START_PROCESSING") return "Start processing";
  if (action === "MARK_MEDIA_READY") {
    return isAnalyzeAudioFailed(item) ? "Retry analyze" : "Mark media ready";
  }
  if (action === "RETRY") {
    return isMissingSourceAssetAnalyzeFailure(item) || isAnalyzeAudioFailed(item)
      ? "Retry from start"
      : "Retry";
  }
  if (action === "HOLD") return "Pause";
  if (action === "RESUME") return isProgressPaused(item) ? "Resume" : "Restart download";
  if (action === "DISMISS") return "Dismiss";
  return action ? actionLabel(action) : "Details";
}

export function worklistPrimaryActionLabel(item: ReupQueueItem): string {
  return primaryQueueActionLabel(item);
}

export function shouldShowQueueTileDetailsButton(item: ReupQueueItem): boolean {
  // Quiet CTA only when download-wait has no forward action (primary === inspect).
  if (item.status !== "WAITING_FOR_MEDIA") return false;
  return primaryQueueAction(item) === "inspect";
}

export function queueTilePrimaryButtonClassName(item: ReupQueueItem): string {
  const tone = queueTilePrimaryButtonTone(item);
  if (tone === "inspect") return "review-board-tile-btn is-secondary";
  if (tone === "quiet") return "review-board-tile-btn is-muted";
  if (tone === "recover") return "review-board-tile-btn is-primary is-recover is-no-arrow";
  if (queueTileShowsForwardArrow(item)) return "review-board-tile-btn is-primary is-promoted-open";
  return "review-board-tile-btn is-primary is-no-arrow";
}

export type QueueTileSecondaryLink = {
  external?: boolean;
  href: string;
  label: string;
};

export function buildQueueTileSecondaryLinks(item: ReupQueueItem): QueueTileSecondaryLink[] {
  const exportPackageId = metadataString(item.metadata_json, "export_package_id");
  const publishHandoffId = metadataString(item.metadata_json, "publish_handoff_id");
  const links: QueueTileSecondaryLink[] = [];
  if (exportPackageId) links.push({ href: `/publishing/export-packages/${exportPackageId}`, label: "Export" });
  if (publishHandoffId) links.push({ href: `/publishing/publish-handoffs/${publishHandoffId}`, label: "Handoff" });
  return links;
}

export function operatorStatusLabel(status: string): string {
  return status.toLowerCase().replace(/_/g, " ").replace(/^./, (letter) => letter.toUpperCase());
}

export function actionLabel(action: ReupQueueAction | ReupQueueBatchAction): string {
  return action.toLowerCase().replace(/_/g, " ").replace(/^./, (letter) => letter.toUpperCase());
}

export function formatDateTime(value: string | null): string {
  if (!value) return "Pending";
  return new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(new Date(value));
}

function readyPriority(item: ReupQueueItem): number {
  if (item.status === "READY_FOR_PROCESSING") return 0;
  if (item.status === "PROCESSING") return 1;
  if (item.status === "WAITING_FOR_MEDIA" || item.status === "WAITING_FOR_METADATA") return 2;
  return 3;
}

/** Pin jobs operator is watching: running → queued/retry → paused → attention → needs start → rest. */
function activeFirstPriority(item: ReupQueueItem): number {
  if (isProgressPaused(item)) return 2;
  if (item.status === "PROCESSING") return 0;
  if (hasActiveDownloadJob(item)) {
    const status = (item.job_status ?? "").toUpperCase();
    if (status === "RUNNING" || status === "IN_PROGRESS" || status === "PROCESSING") return 0;
    return 1;
  }
  if (hasActivePipelineJob(item)) {
    const status = (item.job_status ?? "").toUpperCase();
    if (status === "RUNNING" || status === "IN_PROGRESS" || status === "PROCESSING") return 0;
    return 1;
  }
  if (item.status === "FAILED_NEEDS_ATTENTION" || Boolean(item.blocked_reason)) return 3;
  if (item.status === "READY_FOR_PROCESSING") return 4;
  return 5;
}

function activeProgressRank(item: ReupQueueItem): number {
  if (activeFirstPriority(item) !== 0) return 0;
  return clampJobProgressPercent(item.job_progress_percent);
}

function attentionPriority(item: ReupQueueItem): number {
  if (item.status === "FAILED_NEEDS_ATTENTION") return 0;
  if (item.blocked_reason || item.last_error_message || item.last_error_code) return 1;
  if (item.status === "WAITING_FOR_MEDIA" || item.status === "WAITING_FOR_METADATA") return 2;
  return 3;
}

function exportPriority(item: ReupQueueItem): number {
  if (item.status === "READY_TO_EXPORT") return 0;
  if (item.status === "EXPORT_PACKAGE_CREATED") return 1;
  if (item.status === "READY_TO_PUBLISH" || item.status === "PUBLISH_HANDOFF_CREATED") return 2;
  return 3;
}

function newestFirst(left: ReupQueueItem, right: ReupQueueItem): number {
  return new Date(right.queued_at ?? right.created_at).getTime() - new Date(left.queued_at ?? left.created_at).getTime();
}
