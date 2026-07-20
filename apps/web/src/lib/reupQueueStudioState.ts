import type { ReupQueueBatchAction, BatchOperationResponse } from "../types/export-handoff";
import type { ReupQueueAction, ReupQueueAvailableAction, ReupQueueItem, ReupQueueStatus } from "../types/reup-queue";
import { formatExactEngagementMetric } from "./captureInboxCanonical";
import { buildCapturedItemFromReupQueueItem } from "./operatorReupScore";
import { getOperatorTileScoreBadge, type OperatorTileScoreBadge } from "./operatorTileScore";

export type ReupQueueOperatorFilter = "all" | "needs_start" | "in_production" | "export" | "handoff" | "attention" | "done";
export type ReupQueueSortMode = "active-first" | "newest" | "ready-first" | "needs-attention-first" | "export-ready-first";

export type ReupQueueStudioSummary = Record<ReupQueueOperatorFilter, number>;

export const REUP_QUEUE_STATUS_FILTERS: Array<{ key: ReupQueueOperatorFilter; label: string }> = [
  { key: "all", label: "All" },
  { key: "needs_start", label: "Needs start" },
  { key: "in_production", label: "In production" },
  { key: "export", label: "Export" },
  { key: "handoff", label: "Handoff" },
  { key: "attention", label: "Attention" },
  { key: "done", label: "Done" }
];

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
    needs_start: items.filter((item) => item.status === "READY_FOR_PROCESSING").length,
    in_production: items.filter((item) =>
      item.status === "WAITING_FOR_MEDIA" || item.status === "WAITING_FOR_METADATA" || item.status === "PROCESSING"
    ).length,
    export: items.filter((item) => item.status === "READY_TO_EXPORT" || item.status === "EXPORT_PACKAGE_CREATED").length,
    handoff: items.filter((item) => item.status === "READY_TO_PUBLISH" || item.status === "PUBLISH_HANDOFF_CREATED").length,
    attention: items.filter((item) => item.status === "FAILED_NEEDS_ATTENTION" || Boolean(item.blocked_reason)).length,
    done: items.filter((item) => item.status === "COMPLETED" || item.status === "CANCELLED").length
  };
}

export function statusesForReupQueueFilter(filter: ReupQueueOperatorFilter): ReupQueueStatus[] | undefined {
  if (filter === "all") return undefined;
  if (filter === "needs_start") return ["READY_FOR_PROCESSING"];
  if (filter === "in_production") return ["WAITING_FOR_MEDIA", "WAITING_FOR_METADATA", "PROCESSING"];
  if (filter === "export") return ["READY_TO_EXPORT", "EXPORT_PACKAGE_CREATED"];
  if (filter === "handoff") return ["READY_TO_PUBLISH", "PUBLISH_HANDOFF_CREATED"];
  if (filter === "attention") return ["FAILED_NEEDS_ATTENTION"];
  if (filter === "done") return ["COMPLETED", "CANCELLED"];
  return undefined;
}

export function buildReupQueueSummaryFromStatusCounts(statusCounts: Record<string, number> | null | undefined): ReupQueueStudioSummary {
  const count = (status: ReupQueueStatus) => Number(statusCounts?.[status] ?? 0);
  const needsStart = count("READY_FOR_PROCESSING");
  const inProduction = count("WAITING_FOR_MEDIA") + count("WAITING_FOR_METADATA") + count("PROCESSING");
  const exportReady = count("READY_TO_EXPORT") + count("EXPORT_PACKAGE_CREATED");
  const handoff = count("READY_TO_PUBLISH") + count("PUBLISH_HANDOFF_CREATED");
  const attention = count("FAILED_NEEDS_ATTENTION");
  const done = count("COMPLETED") + count("CANCELLED");
  const all = Object.values(statusCounts ?? {}).reduce((sum, value) => sum + Number(value || 0), 0);
  return {
    all,
    needs_start: needsStart,
    in_production: inProduction,
    export: exportReady,
    handoff,
    attention,
    done
  };
}

export function matchesReupQueueFilter(item: ReupQueueItem, filter: ReupQueueOperatorFilter): boolean {
  if (filter === "all") return true;
  if (filter === "needs_start") return item.status === "READY_FOR_PROCESSING";
  if (filter === "in_production") {
    return item.status === "WAITING_FOR_MEDIA" || item.status === "WAITING_FOR_METADATA" || item.status === "PROCESSING";
  }
  if (filter === "export") return item.status === "READY_TO_EXPORT" || item.status === "EXPORT_PACKAGE_CREATED";
  if (filter === "handoff") return item.status === "READY_TO_PUBLISH" || item.status === "PUBLISH_HANDOFF_CREATED";
  if (filter === "attention") return item.status === "FAILED_NEEDS_ATTENTION" || Boolean(item.blocked_reason);
  if (filter === "done") return item.status === "COMPLETED" || item.status === "CANCELLED";
  return true;
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
  return eligibility.start + eligibility.export + eligibility.handoff;
}

export function secondaryBulkEligibilityTotal(eligibility: ReupQueueSelectionEligibility): number {
  return eligibility.hold + eligibility.resume + eligibility.retry + eligibility.markMediaReady + eligibility.cancel + eligibility.dismiss;
}

export function formatQuickPathPipelineMeta(summary: ReupQueueStudioSummary, sortLabel: string, visibleCount: number): string {
  return [
    `${visibleCount} in view`,
    `${summary.needs_start} needs start`,
    `${summary.in_production} in production`,
    `${summary.export} export`,
    `${summary.handoff} handoff`,
    `${summary.attention} attention`,
    `${summary.done} done`,
    `Sort: ${sortLabel}`
  ].join(" · ");
}

export function quickPathGuidanceTone(summary: ReupQueueStudioSummary): "danger" | "warn" | "success" | "info" {
  if (summary.attention > 0) return "danger";
  if (summary.needs_start > 0) return "success";
  if (summary.in_production > 0) return "warn";
  return "info";
}

export function quickPathSuggestedFilter(summary: ReupQueueStudioSummary, activeFilter: ReupQueueOperatorFilter): ReupQueueOperatorFilter | null {
  if (summary.needs_start > 0 && activeFilter !== "needs_start") return "needs_start";
  if (summary.attention > 0 && activeFilter !== "attention") return "attention";
  if (summary.in_production > 0 && activeFilter !== "in_production") return "in_production";
  if (summary.export > 0 && activeFilter !== "export") return "export";
  if (summary.handoff > 0 && activeFilter !== "handoff") return "handoff";
  if (summary.done > 0 && activeFilter !== "done" && summary.needs_start === 0 && summary.in_production === 0) return "done";
  return null;
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
  if (key === "needs_start") return summary.needs_start > 0 ? "good" : "muted";
  if (key === "in_production") return summary.in_production > 0 ? "warn" : "muted";
  if (key === "export") return summary.export > 0 ? "good" : "muted";
  if (key === "attention") return summary.attention > 0 ? "danger" : "muted";
  if (key === "handoff") return summary.handoff > 0 ? "neutral" : "muted";
  return "muted";
}

export function quickPathGuidance(summary: ReupQueueStudioSummary, activeFilter: ReupQueueOperatorFilter): string | null {
  if (summary.all === 0) return null;
  if (summary.needs_start > 0 && activeFilter !== "needs_start") {
    return "Clips are ready to start — open Needs start or use Start all ready.";
  }
  if (summary.in_production > 0 && activeFilter !== "in_production") {
    return "Clips are in production — open In production to track progress.";
  }
  if (summary.export > 0 && activeFilter !== "export") {
    return "Clips are ready for export — open Export to package them.";
  }
  if (summary.attention > 0 && activeFilter !== "attention") {
    return "Some clips need attention — open Attention to retry or cancel safely.";
  }
  if (summary.handoff > 0 && summary.needs_start === 0 && summary.in_production === 0 && activeFilter !== "handoff") {
    return "Clips are in handoff — open Handoff to inspect payloads.";
  }
  if (summary.done === summary.all) {
    return "All queue items are done or cancelled. Open Review Board to send new approved clips.";
  }
  if (summary.needs_start === 0 && activeFilter === "all") {
    return "No clips are waiting to start — use the stage chips above to find handoff or completed work.";
  }
  return null;
}

export function bulkSelectionGuidance(selectedCount: number, eligibility: ReupQueueSelectionEligibility): string | null {
  if (selectedCount === 0) return null;
  if (primaryBulkEligibilityTotal(eligibility) > 0 || secondaryBulkEligibilityTotal(eligibility) > 0) {
    return `${eligibility.actionable} of ${selectedCount} selected can run a bulk action now.`;
  }
  return "None of the selected clips match a bulk action in their current state. Clear selection, change the status filter, or open Details on one tile.";
}

export type InspectorLifecycleActionGroup = "primary" | "neutral" | "danger";

const INSPECTOR_SPOTLIGHT_ACTIONS: ReupQueueAction[] = [
  "START_PROCESSING",
  "RETRY",
  "HOLD",
  "RESUME",
  "MARK_MEDIA_READY",
  "MARK_COMPLETED"
];

export function inspectorLifecycleActionGroup(action: ReupQueueAction): InspectorLifecycleActionGroup {
  if (action === "CANCEL" || action === "MARK_BLOCKED") return "danger";
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

export function groupInspectorLifecycleActions(actions: ReupQueueAvailableAction[]): {
  primary: ReupQueueAvailableAction[];
  neutral: ReupQueueAvailableAction[];
  danger: ReupQueueAvailableAction[];
} {
  const primary: ReupQueueAvailableAction[] = [];
  const neutral: ReupQueueAvailableAction[] = [];
  const danger: ReupQueueAvailableAction[] = [];
  for (const entry of actions) {
    const group = inspectorLifecycleActionGroup(entry.action);
    if (group === "danger") danger.push(entry);
    else if (group === "neutral") neutral.push(entry);
    else primary.push(entry);
  }
  return { primary, neutral, danger };
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
  const links: InspectorWorkflowLink[] = [
    { href: `/production/transcript-editor/${item.source_video_id}`, label: "Transcript" },
    { href: `/production/final-review/${item.source_video_id}`, label: "Final review" }
  ];
  if (exportPackageId) links.push({ href: `/publishing/export-packages/${exportPackageId}`, label: "Export package" });
  if (publishHandoffId) links.push({ href: `/publishing/publish-handoffs/${publishHandoffId}`, label: "Handoff" });
  if (sourceUrl) links.push({ href: sourceUrl, label: "Source", external: true });
  return links;
}

export function isTerminalQueueItem(item: ReupQueueItem): boolean {
  return item.status === "COMPLETED" || item.status === "CANCELLED";
}

export function resolveInitialReupQueueFilter(summary: ReupQueueStudioSummary): ReupQueueOperatorFilter {
  if (summary.needs_start > 0) return "needs_start";
  if (summary.in_production > 0) return "in_production";
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
  const failed = item.status === "FAILED_NEEDS_ATTENTION";
  return [
    pipelineStage("download", "Download", downloadStageState(item, failed)),
    pipelineStage("transcript", "Transcript", transcriptStageState(item, failed)),
    pipelineStage("render", "Render", renderStageState(item, failed)),
    pipelineStage("export", "Export", exportStageState(item, exportPackageId, failed))
  ];
}

export function isAnalyzeAudioJob(item: ReupQueueItem): boolean {
  const type = (item.job_type ?? "").toUpperCase();
  if (type === "ANALYZE_AUDIO") return true;
  // After Confirm, linked job is audio analysis even if older payloads omit job_type.
  return item.status === "WAITING_FOR_METADATA" && Boolean(item.job_id);
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
  if (!item.job_id || !isAnalyzeAudioJob(item)) return false;
  const status = (item.job_status ?? "").toUpperCase();
  return status === "COMPLETED" || status === "SUCCEEDED";
}

/** ANALYZE_AUDIO finished with zero DialogueBeats (skip dubbing / caption-only video). */
export function isNoDialogueAnalyzeResult(item: ReupQueueItem): boolean {
  if (!isAudioAnalysisCompleted(item)) return false;
  if (item.dialogue_phase === "no_dialogue") return true;
  if (item.has_speech === false) return true;
  if (typeof item.transcript_count === "number" && item.transcript_count <= 0) return true;
  return false;
}

/** Worklist deep-link to Checkpoint #1 only when analyze produced spoken beats. */
export function worklistTranscriptHref(item: ReupQueueItem): string | null {
  if (!item.source_video_id || !isAudioAnalysisCompleted(item)) return null;
  if (isNoDialogueAnalyzeResult(item)) return null;
  return `/production/transcript-editor/${item.source_video_id}`;
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
  // Stage chip already says "Confirm media ready" once download finished.
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
  if (item.media_ready_at || item.status === "WAITING_FOR_METADATA" || isPastProduction(item.status)) return "done";
  if (item.status === "WAITING_FOR_MEDIA" || item.status === "PROCESSING" || item.job_id) return "active";
  return "pending";
}

function transcriptStageState(item: ReupQueueItem, failed: boolean): PipelineStageState {
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
    if (isDownloadReadyForConfirm(item)) return "Confirm media ready";
    const jobStatus = (item.job_status ?? "").toUpperCase();
    if (jobStatus === "RUNNING" || jobStatus === "IN_PROGRESS" || jobStatus === "PROCESSING") return "Downloading";
    if (jobStatus === "QUEUED") return "Queued";
    if (jobStatus === "RETRYABLE") return "Retrying";
    return "Waiting for media";
  }
  if (item.status === "WAITING_FOR_METADATA") return "Waiting for metadata";
  if (item.status === "PROCESSING") return "Processing";
  if (item.status === "FAILED_NEEDS_ATTENTION") {
    return isDownloadFailureAttention(item) ? "Download failed" : "Needs attention";
  }
  if (item.status === "COMPLETED") return "Completed";
  if (item.status === "CANCELLED") return "Cancelled";
  return operatorStatusLabel(item.status);
}

/** Short labels for dense Worklist rail — keep Gallery wording unchanged. */
export function worklistStageLabel(item: ReupQueueItem): string {
  if (isProgressPaused(item)) return "Paused";
  if (item.status === "WAITING_FOR_MEDIA") {
    if (isDownloadReadyForConfirm(item)) return "Ready";
    const jobStatus = (item.job_status ?? "").toUpperCase();
    if (jobStatus === "RUNNING" || jobStatus === "IN_PROGRESS" || jobStatus === "PROCESSING") return "Downloading";
    if (jobStatus === "QUEUED") return "Queued";
    if (jobStatus === "RETRYABLE") return "Retrying";
    return "Waiting";
  }
  if (item.status === "READY_FOR_PROCESSING") return "Needs start";
  if (item.status === "WAITING_FOR_METADATA") {
    return linkedJobActivityLabel(item) ?? "Metadata";
  }
  if (item.status === "FAILED_NEEDS_ATTENTION") {
    return isDownloadFailureAttention(item) ? "Failed" : "Attention";
  }
  if (item.status === "READY_TO_EXPORT") return "Export";
  if (item.status === "READY_TO_PUBLISH") return "Handoff";
  if (item.status === "COMPLETED") return "Done";
  if (item.status === "CANCELLED") return "Cancelled";
  return queueStageLabel(item);
}

/** Worklist status color: active=blue download, good=ready, muted=paused. Gallery keeps queueStageTone. */
export type WorklistStageTone = "active" | "good" | "muted" | "danger" | "warn";

export function worklistStageTone(item: ReupQueueItem): WorklistStageTone {
  if (isProgressPaused(item)) return "muted";
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
  if (item.status === "WAITING_FOR_MEDIA" || item.status === "WAITING_FOR_METADATA" || item.status === "PROCESSING") return "warn";
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

export function primaryQueueAction(item: ReupQueueItem): ReupQueueAction | ReupQueueBatchAction | "inspect" | null {
  if (item.available_actions.some((entry) => entry.action === "START_PROCESSING")) return "START_PROCESSING";
  if (item.status === "READY_TO_EXPORT" && item.media_prep_status === "READY_FOR_EXPORT") return "CREATE_EXPORT_PACKAGE";
  if (item.status === "READY_TO_PUBLISH") return "CREATE_PUBLISH_HANDOFF";
  if (item.available_actions.some((entry) => entry.action === "RETRY")) return "RETRY";
  if (item.status === "FAILED_NEEDS_ATTENTION") return "inspect";
  if (isDownloadReadyForConfirm(item) && item.available_actions.some((entry) => entry.action === "MARK_MEDIA_READY")) {
    return "MARK_MEDIA_READY";
  }
  if (isProgressPaused(item) && item.available_actions.some((entry) => entry.action === "RESUME")) {
    return "RESUME";
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

export function primaryQueueActionLabel(item: ReupQueueItem): string {
  const action = primaryQueueAction(item);
  if (action === "inspect") return "Details";
  if (action === "CREATE_EXPORT_PACKAGE") return "Create export package";
  if (action === "CREATE_PUBLISH_HANDOFF") return "Create publish handoff";
  if (action === "START_PROCESSING") return "Start processing";
  if (action === "MARK_MEDIA_READY") return "Mark media ready";
  if (action === "RETRY") return "Retry";
  if (action === "HOLD") return "Pause";
  if (action === "RESUME") return "Resume";
  if (action === "DISMISS") return "Dismiss";
  return action ? actionLabel(action) : "Details";
}

export function worklistPrimaryActionLabel(item: ReupQueueItem): string {
  return primaryQueueActionLabel(item);
}

export function shouldShowQueueTileDetailsButton(item: ReupQueueItem): boolean {
  const action = primaryQueueAction(item);
  return action !== "inspect" && action !== null;
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
  if (!isTerminalQueueItem(item)) {
    links.push({ href: `/production/transcript-editor/${item.source_video_id}`, label: "Transcript" });
  }
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
