import type {
  FullModalHarvestLastItemSummary,
  FullModalHarvestPhase,
  FullModalHarvestProgress,
  FullModalHarvestProbeResult,
  FullModalHarvestStatus,
  HarvestRuntimeV2PauseReason
} from "./types.js";

export const HARVEST_LOOP_HEARTBEAT_STALE_MS = 5_000;
const ALLOWED_PAUSE_REASONS = new Set<Exclude<HarvestRuntimeV2PauseReason, null>>([
  "operator_stop",
  "backend_flush_failed",
  "content_script_unavailable",
  "captcha_required",
  "calibration_invalid",
  "consecutive_failures",
  "harvest_loop_inactive"
]);

export type HarvestProgressPhaseView = {
  label: string;
  tone: "running" | "paused" | "complete" | "failed";
};

export type HarvestProgressViewModel = {
  visible: boolean;
  title: string;
  mainProgress: string;
  currentAweme: string;
  currentVideoUrl: string;
  phase: HarvestProgressPhaseView;
  progressPercent: number;
  metrics: Record<"Duration" | "Likes" | "Comments" | "Favorites" | "Shares", string>;
  counts: Record<"Mode" | "Target index" | "Harvested" | "Processed" | "Updated" | "Failed" | "Skipped" | "Remaining" | "Pending" | "Flushed" | "Flush attempts" | "Duplicates", string>;
  time: Record<"Elapsed" | "Avg/video" | "ETA", string>;
  navigation: Record<"Previous aweme" | "Current aweme" | "Navigation retries" | "Last navigation result" | "Failed stage" | "Pause reason", string>;
  recentItems: string[];
  errorLines: string[];
  running: boolean;
};

export function buildHarvestProgressViewModel(progress: FullModalHarvestProgress | null): HarvestProgressViewModel {
  if (!progress) return emptyHarvestProgressViewModel();
  const displayProgress = normalizeHarvestProgressForDisplay(progress);
  const metrics = displayProgress.last_extracted_metrics ?? displayProgress.last_harvested_item ?? null;
  const visible =
    displayProgress.running ||
    displayProgress.current_state === "harvesting" ||
    displayProgress.current_state === "paused" ||
    displayProgress.current_state === "completed" ||
    displayProgress.current_state === "completed_with_warnings" ||
    displayProgress.current_state === "failed" ||
    displayProgress.phase === "loading_next_video" ||
    displayProgress.phase === "waiting_modal_change" ||
    displayProgress.phase === "flushing" ||
    Boolean(displayProgress.stopped_reason) ||
    (displayProgress.target_count ?? 0) > 0;
  return {
    visible,
    title: `Runtime: Safe Runner · ${harvestProgressTitle(displayProgress)}`,
    mainProgress: `Target index ${displayProgress.current_index ?? displayProgress.processed_count ?? displayProgress.harvested_count} / ${displayProgress.target_count}`,
    currentAweme: displayProgress.current_aweme_id ? `Current: ${displayProgress.current_aweme_id}` : "Current: not detected",
    currentVideoUrl: displayProgress.current_video_url ?? "",
    phase: phaseView(displayProgress.phase, displayProgress.stopped_reason, displayProgress.item_stage),
    progressPercent: harvestProgressPercent(displayProgress.processed_count ?? displayProgress.harvested_count, displayProgress.target_count),
    metrics: {
      Duration: formatDurationSeconds(metricDuration(metrics)),
      Likes: formatCount(metricNumber(metrics, "like_count")),
      Comments: formatCount(metricNumber(metrics, "comment_count")),
      Favorites: formatCount(metricNumber(metrics, "favorite_count")),
      Shares: formatCount(metricNumber(metrics, "share_count"))
    },
    counts: {
      Mode: displayProgress.mode === "retry_failed" ? "Retry failed" : "Full harvest",
      "Target index": `${displayProgress.current_index ?? displayProgress.processed_count ?? displayProgress.harvested_count} / ${displayProgress.target_count}`,
      Harvested: String(displayProgress.harvested_count),
      Processed: String(displayProgress.processed_count ?? displayProgress.harvested_count + displayProgress.failed_count + (displayProgress.skipped_count ?? 0)),
      Updated: String(displayProgress.updated_count),
      Failed: String(displayProgress.failed_count),
      Skipped: String(displayProgress.skipped_count ?? 0),
      Remaining: String(displayProgress.remaining_count ?? Math.max(0, displayProgress.target_count - (displayProgress.processed_count ?? displayProgress.harvested_count))),
      Pending: String(displayProgress.pending_count ?? 0),
      Flushed: String(displayProgress.flushed_count),
      "Flush attempts": String(displayProgress.flush_attempt_count ?? 0),
      Duplicates: String(displayProgress.duplicate_count)
    },
    time: {
      Elapsed: formatClockSeconds(displayProgress.elapsed_seconds),
      "Avg/video": displayProgress.average_seconds_per_item != null ? `${displayProgress.average_seconds_per_item.toFixed(1)}s` : "none",
      ETA: formatClockSeconds(displayProgress.eta_seconds)
    },
    navigation: {
      "Previous aweme": displayProgress.previous_aweme_id ?? "none",
      "Current aweme": displayProgress.current_aweme_id ?? "none",
      "Navigation retries": String(displayProgress.navigation_retries ?? 0),
      "Last navigation result": displayProgress.last_navigation_result ?? "none",
      "Failed stage": displayProgress.failed_stage ?? "none",
      "Pause reason": displayProgress.stopped_reason ?? "none"
    },
    recentItems: recentHarvestItems(displayProgress.recent_items),
    errorLines: errorLines(displayProgress),
    running: isHarvestDisplayRunning(displayProgress)
  };
}

export function harvestProgressPercent(harvestedCount: number, targetCount: number): number {
  if (!Number.isFinite(harvestedCount) || !Number.isFinite(targetCount) || targetCount <= 0) return 0;
  return Math.max(0, Math.min(100, Math.round((harvestedCount / targetCount) * 100)));
}

export function normalizeHarvestState(progress: FullModalHarvestProgress, _nowMs = Date.now()): FullModalHarvestProgress {
  const status = canonicalHarvestStatus(progress);
  if (status === "running") {
    const runningPhase =
      progress.phase === "completed" ||
      progress.phase === "completed_with_warnings" ||
      progress.phase === "failed" ||
      progress.phase === "paused" ||
      progress.phase === "stopped" ||
      !progress.phase
        ? "harvesting"
        : progress.phase;
    return {
      ...progress,
      harvest_status: "running",
      running: true,
      current_state: "harvesting",
      phase: runningPhase,
      stopped_reason: null,
      can_resume: false
    };
  }
  if (status === "completed") {
    return { ...progress, harvest_status: "completed", running: false, current_state: "completed", phase: "completed", stopped_reason: null, can_resume: false };
  }
  if (status === "completed_with_warnings") {
    return { ...progress, harvest_status: "completed_with_warnings", running: false, current_state: "completed_with_warnings", phase: "completed_with_warnings", stopped_reason: null, can_resume: false };
  }
  if (status === "failed") {
    return { ...progress, harvest_status: "failed", running: false, current_state: "failed", phase: "failed", can_resume: progress.can_resume ?? false };
  }
  if (status === "paused") {
    return {
      ...progress,
      harvest_status: "paused",
      running: false,
      current_state: "paused",
      phase: "paused",
      can_resume: true
    };
  }
  return {
    ...progress,
    harvest_status: "idle",
    running: false,
    current_state: "stopped",
    phase: progress.phase === "failed" ? "failed" : "stopped",
    can_resume: false,
    stopped_reason: null
  };
}

export function normalizeHarvestProgressForDisplay(progress: FullModalHarvestProgress): FullModalHarvestProgress {
  return normalizeHarvestState(progress);
}

export function isHarvestDisplayRunning(progress: FullModalHarvestProgress | null): boolean {
  if (!progress) return false;
  const displayProgress = normalizeHarvestProgressForDisplay(progress);
  return displayProgress.harvest_status === "running";
}

export function phaseView(phase: FullModalHarvestPhase | null | undefined, stoppedReason?: string | null, itemStage?: FullModalHarvestProgress["item_stage"]): HarvestProgressPhaseView {
  if (phase === "paused") return { label: stoppedReason ? `Paused · ${stoppedReason}` : "Paused", tone: "paused" };
  if (phase === "completed_with_warnings") return { label: "Completed with warnings", tone: "complete" };
  if (phase === "completed") return { label: "Completed", tone: "complete" };
  if (phase === "failed") return { label: stoppedReason ? `Failed · ${stoppedReason}` : "Failed", tone: "failed" };
  if (phase === "starting") return { label: "Starting Safe Runner...", tone: "running" };
  if (phase === "capturing_profile") return { label: "Capturing profile...", tone: "running" };
  if (phase === "harvesting") return { label: itemStage === "navigating" ? "Opening target modal..." : "Safe Runner advancing queue...", tone: "running" };
  if (phase === "loading_next_video") return { label: "Opening target modal...", tone: "running" };
  if (phase === "waiting_modal_change") return { label: "Waiting for target modal...", tone: "running" };
  if (phase === "extracting_metrics") {
    if (itemStage === "extracted") return { label: "Validating extracted metrics...", tone: "running" };
    if (itemStage === "committing") return { label: "Marking target updated after backend commit...", tone: "running" };
    return { label: "Extracting target metrics...", tone: "running" };
  }
  if (phase === "queued_item") return { label: "Validated item queued for backend flush...", tone: "running" };
  if (phase === "flushing") return { label: "Flushing target to backend...", tone: "running" };
  return { label: "Safe Runner active...", tone: "running" };
}

export function formatDurationSeconds(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value) || value < 0) return "none";
  const total = Math.round(value);
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const seconds = total % 60;
  if (hours > 0) return `${pad2(hours)}:${pad2(minutes)}:${pad2(seconds)}`;
  return `${pad2(minutes)}:${pad2(seconds)}`;
}

export function formatClockSeconds(value: number | null | undefined): string {
  return formatDurationSeconds(value);
}

export function formatCount(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return "none";
  const abs = Math.abs(value);
  if (abs >= 1_000_000) return `${trimDecimal(value / 1_000_000)}M`;
  if (abs >= 1_000) return `${trimDecimal(value / 1_000)}K`;
  return String(value);
}

export function recentHarvestItems(items: FullModalHarvestLastItemSummary[] | null | undefined): string[] {
  return (items ?? []).slice(-5).map((item, offset) => {
    const index = item.index ?? offset + 1;
    const status = item.status === "failed" ? "FAIL" : "OK";
    if (item.status === "failed") {
      return `#${index} ${status} · aweme ${item.aweme_id ?? "unknown"} · ${item.reason ?? item.extraction_warning ?? "unknown failure"}`;
    }
    const integritySuffix = item.data_integrity_status === "mismatch" ? ` · MISMATCH ${item.data_integrity_reason ?? "integrity_failed"}` : "";
    const duplicateSuffix = item.duplicate_signature_warning ? ` · ${item.duplicate_signature_warning}` : "";
    return `#${index} ${status} · aweme ${item.aweme_id ?? "unknown"} · Likes ${formatCount(item.like_count)} · Comments ${formatCount(item.comment_count)} · Shares ${formatCount(item.share_count)}${integritySuffix}${duplicateSuffix}`;
  });
}

function emptyHarvestProgressViewModel(): HarvestProgressViewModel {
  return {
    visible: false,
    title: "Runtime: Safe Runner",
    mainProgress: "Video 0 / 0",
    currentAweme: "Current: not detected",
    currentVideoUrl: "",
    phase: { label: "Safe Runner idle", tone: "running" },
    progressPercent: 0,
    metrics: { Duration: "none", Likes: "none", Comments: "none", Favorites: "none", Shares: "none" },
    counts: { Mode: "Full harvest", "Target index": "0 / 0", Harvested: "0", Processed: "0", Updated: "0", Failed: "0", Skipped: "0", Remaining: "0", Pending: "0", Flushed: "0", "Flush attempts": "0", Duplicates: "0" },
    time: { Elapsed: "none", "Avg/video": "none", ETA: "none" },
    navigation: { "Previous aweme": "none", "Current aweme": "none", "Navigation retries": "0", "Last navigation result": "none", "Failed stage": "none", "Pause reason": "none" },
    recentItems: [],
    errorLines: [],
    running: false
  };
}

function canonicalHarvestStatus(progress: FullModalHarvestProgress): FullModalHarvestStatus {
  if (progress.harvest_status === "completed" || progress.current_state === "completed" || progress.phase === "completed") return "completed";
  if (progress.harvest_status === "completed_with_warnings" || progress.current_state === "completed_with_warnings" || progress.phase === "completed_with_warnings") return "completed_with_warnings";
  if (progress.harvest_status === "failed" || progress.current_state === "failed" || progress.phase === "failed") return "failed";
  if (progress.harvest_status === "paused" || progress.current_state === "paused" || progress.phase === "paused") {
    return isAllowedPauseReason(progress.stopped_reason) ? "paused" : "running";
  }
  if (
    progress.running
    || progress.harvest_status === "running"
    || progress.current_state === "harvesting"
    || progress.phase === "loading_next_video"
    || progress.phase === "waiting_modal_change"
    || progress.phase === "flushing"
  ) return "running";
  if (isAllowedPauseReason(progress.stopped_reason)) return "paused";
  return "idle";
}

function errorLines(progress: FullModalHarvestProgress): string[] {
  const hasFlushFailure = Boolean(progress.flush_error_code || progress.flush_error_message || progress.stopped_reason === "backend_flush_failed");
  if (hasFlushFailure) {
    const pendingCount = progress.pending_count ?? progress.pending_count_after_flush ?? progress.pending_count_before_flush ?? 0;
    return [
      `Flush failed: ${progress.flush_error_code ?? "network_failed"}`,
      progress.flush_error_message ? `Flush detail: ${progress.flush_error_message}` : progress.last_error ? `Flush detail: ${progress.last_error}` : null,
      progress.flush_url ? `Flush URL: ${progress.flush_url}` : null,
      progress.flush_status_code != null ? `HTTP status: ${progress.flush_status_code}` : null,
      `Pending preserved: ${pendingCount}`,
      progress.flush_retryable != null ? `Retryable: ${progress.flush_retryable ? "yes" : "no"}` : null,
      progress.flush_next_action ? `Next action: ${progress.flush_next_action}` : pendingCount > 0 ? "Next action: Click Retry Flush Pending after backend is healthy." : null
    ].filter((value): value is string => Boolean(value));
  }
  if (progress.current_state === "completed_with_warnings") {
    return [
      progress.last_error ? `Warning: ${progress.last_error}` : "Completed with warnings.",
      ...(progress.failed_targets ?? []).map((item) => `Failed target #${item.index}: ${item.aweme_id} · ${item.reason ?? "unknown failure"}`)
    ];
  }
  if (progress.harvest_status === "paused" && isAllowedPauseReason(progress.stopped_reason)) {
    return [
      `Pause reason: ${progress.stopped_reason}`,
      progress.integrity_mismatch_count ? `Integrity mismatches: ${progress.integrity_mismatch_count}` : null,
      progress.last_integrity_error ? `Last integrity error: ${progress.last_integrity_error}` : null,
      progress.last_integrity_expected_aweme_id ? `Expected aweme: ${progress.last_integrity_expected_aweme_id}` : null,
      progress.last_integrity_observed_aweme_id ? `Observed aweme: ${progress.last_integrity_observed_aweme_id}` : null,
      (progress.pending_count ?? 0) > 0 ? "Next actions: Flush Pending or Resume Harvest." : "Next action: Resume Harvest."
    ].filter((value): value is string => Boolean(value));
  }
  if (progress.current_state !== "failed" && progress.phase !== "failed" && !progress.last_error) return [];
  return [
    progress.stopped_reason ? `Stopped reason: ${progress.stopped_reason}` : null,
    progress.failed_at_index != null ? `Failed at index: ${progress.failed_at_index}` : null,
    progress.failed_aweme_id ? `Failed aweme: ${progress.failed_aweme_id}` : null,
    progress.last_error ? `Last error: ${progress.last_error}` : null,
    progress.failed_stage === "no_next_point_calibrated" ? "Next action: Press ArrowDown manually or click next video, then Resume Harvest." : null,
    progress.failed_stage === "modal_id_change_timeout" ? "Next action: Press ArrowDown manually or click next video, then Resume Harvest." : null,
    progress.failed_stage ? null : "Next actions: Retry Resume Harvest · Recalibrate · Flush Pending · Open modal again"
  ].filter((value): value is string => Boolean(value));
}

function harvestProgressTitle(progress: FullModalHarvestProgress): string {
  if (progress.harvest_status === "completed_with_warnings") return "Harvest completed with warnings";
  if (progress.harvest_status === "completed") return "Harvest completed";
  if (progress.harvest_status === "failed") return "Harvest failed";
  if (progress.harvest_status === "paused" && isAllowedPauseReason(progress.stopped_reason)) return "Harvest paused";
  return "Harvest running";
}

function metricDuration(metrics: FullModalHarvestProbeResult | FullModalHarvestLastItemSummary | null): number | null | undefined {
  return metrics?.duration_seconds;
}

function metricNumber(metrics: FullModalHarvestProbeResult | FullModalHarvestLastItemSummary | null, key: "like_count" | "comment_count" | "favorite_count" | "share_count"): number | null | undefined {
  return metrics?.[key];
}

function isAllowedPauseReason(reason: string | null | undefined): reason is Exclude<HarvestRuntimeV2PauseReason, null> {
  return typeof reason === "string" && ALLOWED_PAUSE_REASONS.has(reason as Exclude<HarvestRuntimeV2PauseReason, null>);
}

function trimDecimal(value: number): string {
  return value.toFixed(1).replace(/\.0$/, "");
}

function pad2(value: number): string {
  return String(value).padStart(2, "0");
}
