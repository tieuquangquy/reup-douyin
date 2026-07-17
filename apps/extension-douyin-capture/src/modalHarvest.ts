import { buildPendingFlushItem, isRetryableFlushError, markQueueFailed, markQueueFlushed, markQueueFlushing, upsertPendingFlushItem } from "./flushQueue.js";
import { parseDouyinEngagementCount, parseDouyinEngagementText } from "./douyinEngagementZeroSentinels.js";
import { normalizeDouyinNetworkPayload } from "./networkCache.js";
import { buildFullModalHarvestRequestPayload } from "./requestPayloads.js";
import {
  applyCalibratedPointMetricsToRawDomDetail,
  calibrationViewport,
  currentViewport,
  parseCompactCount,
  parseCompactCountFromOcr,
  pointCalibrationWarning,
  readCalibratedPointMetrics
} from "./calibratedPoint.js";
import type {
  CalibratedMetricName,
  CalibratedPointMetricResult,
  ActionRailBlockDiagnostic,
  ActionRailCompactCountCandidateDiagnostic,
  ActionRailCompactCountClusterDiagnostic,
  ActionRailIconAnchoredMetricDiagnostic,
  ActionRailIconCandidateDiagnostic,
  ActionRailMissingReason,
  ActionRailNumericLabelDiagnostic,
  ActionRailRailRegionDiagnostic,
  ActionRailAssignedMetricDiagnostic,
  ActionRailExtractionMode,
  ActionRailRectDiagnostic,
  ActionRailRejectedCandidateDiagnostic,
  ActionRailXBandDiagnostic,
  CaptureContext,
  CdpAwemeEvidence,
  CdpAwemeStatus,
  CdpDomSnapshotPayload,
  CdpDomSnapshotRailLabel,
  CdpDomSnapshotRightRailResult,
  VisualRightRailDiagnostics,
  VisualRightRailLabel,
  VisualRightRailPayload,
  FullModalHarvestControlOptions,
  FullModalHarvestDetectorDiagnostics,
  ExtensionBackendErrorCode,
  FullModalHarvestFailedItem,
  FullModalHarvestItemPayload,
  FullModalHarvestPendingFlushItem,
  FullModalHarvestLastItemSummary,
  FullModalHarvestPhase,
  FullModalHarvestStatus,
  FullModalHarvestProbeResult,
  FullModalHarvestProgress,
  FullModalHarvestFlushStatus,
  FullModalHarvestCurrentState,
  FullModalHarvestMode,
  FullModalHarvestTargetStatus,
  FullModalHarvestFailedStage,
  FullModalHarvestNavigationResult,
  FullModalHarvestNextPointStatus,
  FullModalHarvestRequestPayload,
  PageSnapshot,
  RawAwemeEvidence,
  RawDomDetailMetrics,
  RawEvidenceSummary,
  RightRailCalibration,
  StoredFullModalHarvestState
} from "./types.js";
import { detectPageFromDocument } from "./extractor.js";

export const PRODUCTION_EVIDENCE_COLLECTION_VERSION = "phase11a_production_stabilized_calibrated_harvest" as const;

const DEFAULT_OPTIONS = {
  target_count: 49,
  delay_between_items_ms: 150,
  per_item_timeout_ms: 15_000,
  flush_every_n_items: 5,
  stop_on_captcha: true,
  stop_on_no_next: true,
  allow_probe_warnings: false,
  capture_session_id: null,
  capture_id: null,
  target_aweme_ids: [],
  retry_failed_only: false,
  profile_card_evidence_by_aweme_id: {}
} satisfies Required<FullModalHarvestControlOptions>;

const CAPTCHA_MARKERS = [
  "captcha",
  "verification",
  "security check",
  "challenge",
  "login required",
  "验证",
  "安全验证",
  "请完成验证",
  "抖音安全中心"
];

export type ModalHarvestRuntimeConfig = Required<FullModalHarvestControlOptions> & {
  apiBaseUrl: string;
  captureSessionId?: string | null;
};

const DEBUG_PREFIX = "[reup-douyin][full-modal-harvest]";

export type ModalHarvestCallbacks = {
  flushBatch(payload: FullModalHarvestRequestPayload, options?: { keepalive?: boolean }): Promise<Record<string, unknown> | null>;
  saveState(state: StoredFullModalHarvestState): Promise<void>;
  clearState(): Promise<void>;
  getCalibration?(): Promise<RightRailCalibration | null>;
  captureVisibleTab?(): Promise<string | null>;
};

type FlushResult = {
  success: boolean;
  updated_count: number;
  flushed_aweme_ids: string[];
  failed_count: number;
  failure_summaries: FullModalHarvestFailedItem[];
  unchanged_count: number;
  flush_url?: string | null;
  flush_status_code?: number | null;
  flush_error_code?: ExtensionBackendErrorCode | null;
  flush_error_message?: string | null;
  flush_retryable?: boolean | null;
  backend_response_summary?: Record<string, string | number | boolean | null> | null;
};

type NavigationResult = {
  moved: boolean;
  reason: "aweme_changed" | "no_next_control" | "navigation_timeout" | "duplicate_loop_detected";
  retries?: number;
  last_result?: FullModalHarvestNavigationResult;
  failed_stage?: FullModalHarvestFailedStage;
  target_aweme_id?: string | null;
};

type ActionKind = "like" | "comment" | "favorite" | "share";

type MetricMatch = { value: number | null; text: string | null };

type ActionBlockCandidate = {
  semantic_kind: ActionKind | null;
  icon_kind: ActionKind | null;
  countNode: HTMLElement;
  marker: HTMLElement;
  blockElements: HTMLElement[];
  blockText: string | null;
  metricText: string | null;
  value: number | null;
  confidence: "high" | "low";
  order_index: number;
  block_descriptor: string;
  rect: { x: number; y: number; width: number; height: number };
  hints: string | null;
};

type RuntimeAwemePriority = "exact_aweme_runtime_object" | "exact_aweme_script_hydration_object" | "exact_aweme_network_cache_object";

type RuntimeAwemeObjectSource = "react_fiber_aweme_object" | "react_props_aweme_object" | "vue_state_aweme_object" | "script_hydration_aweme_object" | "network_cache_aweme_object";

type RuntimeAwemeResult = {
  aweme: Record<string, unknown>;
  raw_aweme: RawAwemeEvidence;
  priority: RuntimeAwemePriority;
  source_used: RuntimeAwemeObjectSource;
  exact_aweme_source: "react_fiber" | "react_props" | "vue_state" | "script_hydration" | "network_cache";
  raw_aweme_keys: string[];
};

type RuntimeAwemeMappedMetrics = {
  duration_seconds: number | null;
  duration_text: string | null;
  duration_raw: number | null;
  duration_validation_result: "accepted_exact_aweme" | "rejected_missing" | "rejected_non_positive" | "rejected_too_large";
  duration_candidate_list: Array<{ source: string; raw_value: number | null; normalized_seconds: number | null; accepted: boolean; reason: string }>;
  view_count: number | null;
  like_count: number | null;
  comment_count: number | null;
  favorite_count: number | null;
  share_count: number | null;
  posted_text: string | null;
  posted_at: string | null;
  posted_source: "aweme_create_time" | "none";
  posted_parse_confidence: "parsed" | "none";
};

type CdpDomSnapshotMetricSelection = {
  result: CdpDomSnapshotRightRailResult | null;
  warning_reason: string | null;
};

type VisualRightRailMetricSelection = {
  source: "accessibility_tree_right_rail" | "screenshot_ocr_right_rail" | null;
  labels: VisualRightRailLabel[];
  diagnostics: VisualRightRailDiagnostics;
  warning_reason: string | null;
};

type CombinedModalActionTextResult = {
  extraction_source: "combined_modal_text_fallback";
  like_count: number;
  comment_count: number;
  favorite_count: number;
  share_count: number;
  combined_text_segment: string;
  combined_count_tokens: string[];
  confidence: "high";
};

type BoundedAwemeSearchOptions = {
  maxDepth: number;
  maxObjects: number;
  maxArrayLength: number;
  maxKeysPerObject: number;
  timeoutMs: number;
};

const RUNTIME_WALKER_DEFAULTS: BoundedAwemeSearchOptions = {
  maxDepth: 8,
  maxObjects: 30_000,
  maxArrayLength: 100,
  maxKeysPerObject: 80,
  timeoutMs: 650
};

const REACT_RUNTIME_KEYS = ["memoizedProps", "pendingProps", "memoizedState", "return", "child", "sibling", "stateNode", "props"];
const VUE_RUNTIME_KEYS = ["__vue__", "__vueParentComponent", "vnode", "props", "setupState", "ctx"];
const WINDOW_RUNTIME_KEY_PATTERN = /state|store|router|app|douyin|aweme|detail|video/i;
const SECRET_LIKE_KEY_PATTERN = /cookie|authorization|auth|token|secret|credential|password|passwd|session|header|csrf/i;

type CandidateDetectionResult = {
  accepted: ActionBlockCandidate[];
  rejected: ActionRailRejectedCandidateDiagnostic[];
  rail_x_band: ActionRailXBandDiagnostic | null;
  computed_rail_x_band: ActionRailXBandDiagnostic | null;
  viewport_width: number;
  viewport_height: number;
  active_video_rect: ActionRailRectDiagnostic | null;
  modal_candidate_rect: ActionRailRectDiagnostic | null;
  icon_candidates: ActionRailIconCandidateDiagnostic[];
  selected_action_icons: ActionRailIconCandidateDiagnostic[];
  icon_anchored_metrics: ActionRailIconAnchoredMetricDiagnostic[];
  rejected_number_examples: ActionRailRejectedCandidateDiagnostic[];
  rejected_icon_examples: ActionRailRejectedCandidateDiagnostic[];
  compact_count_candidates: ActionRailCompactCountCandidateDiagnostic[];
  compact_text_node_candidates_count: number;
  compact_count_clusters: ActionRailCompactCountClusterDiagnostic[];
  selected_compact_count_cluster: ActionRailCompactCountClusterDiagnostic | null;
  selected_cluster_texts: string[] | null;
  selected_cluster_rects: ActionRailRectDiagnostic[] | null;
  rail_region: ActionRailRailRegionDiagnostic | null;
  numeric_labels_found: ActionRailNumericLabelDiagnostic[];
  selected_rail_labels: string[] | null;
  selected_rail_labels_with_rect: ActionRailNumericLabelDiagnostic[] | null;
  assigned_metrics: ActionRailAssignedMetricDiagnostic[] | null;
  rejected_examples: ActionRailRejectedCandidateDiagnostic[];
  extraction_mode: ActionRailExtractionMode | null;
  action_blocks_missing_reason: ActionRailMissingReason | null;
  warning_reason: string | null;
};

type RightRailRegion = {
  minX: number;
  maxX: number;
  minY: number;
  maxY: number;
  source: "viewport_right_band" | "active_video_geometry";
};

type NumericRailLabelCandidate = {
  node: HTMLElement;
  text: string;
  value: number | null;
  rect: { x: number; y: number; width: number; height: number };
  source: "element" | "element_from_point";
  accepted: boolean;
  reason: string | null;
  nearestTag: string | null;
  nearestClass: string | null;
  nearestAriaLabel: string | null;
  nearestTitle: string | null;
};

type CompactCountCandidate = {
  node: HTMLElement;
  text: string;
  value: number | null;
  rect: { x: number; y: number; width: number; height: number };
  rejectionReason: string | null;
  source: "text_node" | "element" | "element_from_point";
  nearestTag: string | null;
  nearestClass: string | null;
  nearestAriaLabel: string | null;
  nearestTitle: string | null;
};

type ScoredCompactCountCluster = {
  id: string;
  centerX: number;
  candidates: CompactCountCandidate[];
  score: number;
  reason: string | null;
  xBand: ActionRailXBandDiagnostic;
};

type TextNodeRectCandidate = {
  text: string;
  rect: { x: number; y: number; width: number; height: number };
  nearestElement: HTMLElement;
  nearestTag: string | null;
  nearestClass: string | null;
  nearestAriaLabel: string | null;
  nearestTitle: string | null;
};

type ActionIconCandidate = {
  node: HTMLElement;
  kind: ActionKind | null;
  rect: { x: number; y: number; width: number; height: number };
  hints: string | null;
  rejectionReason: string | null;
};

type IconAnchoredMetric = {
  kind: ActionKind;
  icon: ActionIconCandidate;
  count: CompactCountCandidate | null;
  distance: number | null;
};

type ActionMetricSelection = {
  value: number | null;
  text: string | null;
  block_text: string | null;
  confidence: "high" | "low";
  rejected_reason: string | null;
  source?: "dom_detail_modal" | "dom_profile_card_fallback" | "dom_zero_sentinel" | null;
  node_descriptor?: string | null;
};

export class FullModalHarvestController {
  private readonly document: Document;
  private readonly location: Location;
  private readonly callbacks: ModalHarvestCallbacks;
  private readonly context: CaptureContext;
  private readonly page: PageSnapshot;
  private readonly config: ModalHarvestRuntimeConfig;
  private readonly harvestId: string;
  private readonly startedAt: string;
  private readonly harvestedAwemeIds = new Set<string>();
  private readonly flushedAwemeIds = new Set<string>();
  private readonly pendingById = new Map<string, FullModalHarvestItemPayload>();
  private pendingFlushQueue: FullModalHarvestPendingFlushItem[] = [];
  private readonly failedById = new Map<string, FullModalHarvestFailedItem>();
  private readonly targetAwemeIds: string[];
  private readonly targetStatusById = new Map<string, FullModalHarvestTargetStatus>();
  private readonly mode: FullModalHarvestMode;
  private consecutiveFailures = 0;
  private stopRequested = false;
  private updatedCount = 0;
  private duplicateCount = 0;
  private lastError: string | null = null;
  private stoppedReason: string | null = null;
  private running = false;
  private currentAwemeId: string | null = null;
  private detectorDiagnostics: FullModalHarvestDetectorDiagnostics | null = null;
  private flushUrl: string | null = null;
  private flushStatusCode: number | null = null;
  private flushErrorCode: ExtensionBackendErrorCode | null = null;
  private flushErrorMessage: string | null = null;
  private flushRetryable: boolean | null = null;
  private flushNextAction: string | null = null;
  private pendingCountBeforeFlush: number | null = null;
  private pendingCountAfterFlush: number | null = null;
  private backendResponseSummary: Record<string, string | number | boolean | null> | null = null;
  private lastHarvestedItem: FullModalHarvestLastItemSummary | null = null;
  private lastExtractedMetrics: FullModalHarvestProbeResult | null = null;
  private readonly recentItems: FullModalHarvestLastItemSummary[] = [];
  private phase: FullModalHarvestPhase = "starting";
  private lastFlushStatus: FullModalHarvestFlushStatus = "none";
  private failedAtIndex: number | null = null;
  private failedAwemeId: string | null = null;
  private previousAwemeId: string | null = null;
  private navigationRetries = 0;
  private lastNavigationResult: FullModalHarvestNavigationResult | null = null;
  private failedStage: FullModalHarvestFailedStage = null;
  private nextPointStatus: FullModalHarvestNextPointStatus = "missing";
  private consecutiveDuplicateCount = 0;
  private lastNavigationAttemptFromAwemeId: string | null = null;
  private harvestLoopHeartbeatAt: string | null = null;
  private itemStage: NonNullable<FullModalHarvestProgress["item_stage"]> = "idle";
  private phaseStartedAtMs: number = Date.now();
  private extractedAtMs: number | null = null;
  private lastCommitResult: Exclude<FullModalHarvestProgress["last_commit_result"], undefined> = null;
  private repairExtractedNotCommittedCount = 0;
  private integrityMismatchCount = 0;
  private lastIntegrityError: string | null = null;
  private lastIntegrityExpectedAwemeId: string | null = null;
  private lastIntegrityObservedAwemeId: string | null = null;
  private lastIntegrityCheckedAt: string | null = null;
  private readonly metricSignatureByAwemeId = new Map<string, string>();

  constructor(
    document: Document,
    location: Location,
    context: CaptureContext,
    config: ModalHarvestRuntimeConfig,
    callbacks: ModalHarvestCallbacks,
    initialState?: StoredFullModalHarvestState | null
  ) {
    this.document = document;
    this.location = location;
    this.context = context;
    this.page = detectPageFromDocument(document, location.href);
    this.config = config;
    this.callbacks = callbacks;
    this.harvestId = initialState?.harvest_id ?? crypto.randomUUID();
    this.startedAt = initialState?.started_at ?? new Date().toISOString();
    this.currentAwemeId = initialState?.current_aweme_id ?? null;
    this.updatedCount = initialState?.updated_count ?? 0;
    this.duplicateCount = initialState?.duplicate_count ?? 0;
    this.lastError = initialState?.last_error ?? null;
    this.stoppedReason = initialState?.stopped_reason ?? null;
    this.detectorDiagnostics = initialState?.detector_diagnostics ?? null;
    this.flushUrl = initialState?.flush_url ?? null;
    this.flushStatusCode = initialState?.flush_status_code ?? null;
    this.flushErrorCode = initialState?.flush_error_code ?? null;
    this.flushErrorMessage = initialState?.flush_error_message ?? null;
    this.flushRetryable = initialState?.flush_retryable ?? null;
    this.flushNextAction = initialState?.flush_next_action ?? null;
    this.pendingCountBeforeFlush = initialState?.pending_count_before_flush ?? null;
    this.pendingCountAfterFlush = initialState?.pending_count_after_flush ?? null;
    this.backendResponseSummary = initialState?.backend_response_summary ?? null;
    this.lastHarvestedItem = initialState?.last_harvested_item ?? null;
    this.lastExtractedMetrics = initialState?.last_extracted_metrics ?? null;
    this.phase = initialState?.phase ?? (initialState?.stopped_reason === "completed" ? "completed" : initialState?.stopped_reason ? "failed" : "starting");
    this.lastFlushStatus = initialState?.last_flush_status ?? "none";
    this.failedAtIndex = initialState?.failed_at_index ?? null;
    this.failedAwemeId = initialState?.failed_aweme_id ?? null;
    this.previousAwemeId = initialState?.previous_aweme_id ?? null;
    this.navigationRetries = initialState?.navigation_retries ?? 0;
    this.lastNavigationResult = initialState?.last_navigation_result ?? null;
    this.failedStage = initialState?.failed_stage ?? null;
    this.nextPointStatus = initialState?.next_point_status ?? "missing";
    this.consecutiveDuplicateCount = initialState?.consecutive_duplicate_count ?? 0;
    this.harvestLoopHeartbeatAt = initialState?.harvest_loop_heartbeat_at ?? null;
    this.itemStage = initialState?.item_stage ?? "idle";
    this.lastCommitResult = initialState?.last_commit_result ?? null;
    this.repairExtractedNotCommittedCount = initialState?.repair_extracted_not_committed_count ?? 0;
    this.integrityMismatchCount = initialState?.integrity_mismatch_count ?? 0;
    this.lastIntegrityError = initialState?.last_integrity_error ?? null;
    this.lastIntegrityExpectedAwemeId = initialState?.last_integrity_expected_aweme_id ?? null;
    this.lastIntegrityObservedAwemeId = initialState?.last_integrity_observed_aweme_id ?? null;
    this.lastIntegrityCheckedAt = initialState?.last_integrity_checked_at ?? null;
    this.extractedAtMs = initialState?.item_stage === "extracted" ? Date.now() : null;
    for (const item of initialState?.recent_items ?? []) this.recentItems.push(item);
    for (const awemeId of initialState?.harvested_aweme_ids ?? []) this.harvestedAwemeIds.add(awemeId);
    for (const awemeId of initialState?.flushed_aweme_ids ?? []) this.flushedAwemeIds.add(awemeId);
    for (const item of initialState?.pending_items ?? []) this.pendingById.set(item.aweme_id, item);
    this.pendingFlushQueue = initialState?.pending_flush_queue ?? Array.from(this.pendingById.values()).map((item) => buildPendingFlushItem(item, this.config.captureSessionId ?? null));
    for (const item of initialState?.failed_items ?? []) this.failedById.set(item.aweme_id, item);
    this.targetAwemeIds = normalizeTargetAwemeIds(initialState?.target_aweme_ids ?? config.target_aweme_ids ?? []);
    this.mode = config.retry_failed_only ? "retry_failed" : (initialState?.mode ?? "full_harvest");
    this.consecutiveFailures = initialState?.consecutive_failures ?? 0;
    this.initializeTargetStatuses(initialState);
    this.clampFailureIndex();
  }

  get progress(): FullModalHarvestProgress {
    const elapsedSeconds = Math.max(0, Math.round((Date.now() - new Date(this.startedAt).getTime()) / 1000));
    const harvestedCount = this.harvestedAwemeIds.size;
    const targetCount = this.effectiveTargetCount();
    const processedCount = this.processedTargetCount();
    const updatedCount = this.updatedTargetCount();
    const failedCount = this.failedTargetCount();
    const skippedCount = this.skippedTargetCount();
    const averageSecondsPerItem = processedCount > 0 ? Math.round((elapsedSeconds / processedCount) * 10) / 10 : null;
    const etaSeconds = averageSecondsPerItem !== null ? Math.max(0, Math.round((targetCount - processedCount) * averageSecondsPerItem)) : null;
    const currentIndex = this.currentTargetIndex();
    const failedTargets = this.failedTargetStatuses();
    return {
      running: this.running,
      harvest_status: this.harvestStatus(),
      harvest_loop_heartbeat_at: this.harvestLoopHeartbeatAt,
      current_state: this.progressCurrentState(),
      phase: this.phase,
      item_stage: this.itemStage,
      phase_elapsed_ms: this.phaseElapsedMs(),
      extracted_not_committed_ms: this.extractedNotCommittedMs(),
      last_commit_result: this.lastCommitResult,
      repair_extracted_not_committed_count: this.repairExtractedNotCommittedCount,
      integrity_mismatch_count: this.integrityMismatchCount,
      last_integrity_error: this.lastIntegrityError,
      last_integrity_expected_aweme_id: this.lastIntegrityExpectedAwemeId,
      last_integrity_observed_aweme_id: this.lastIntegrityObservedAwemeId,
      last_integrity_checked_at: this.lastIntegrityCheckedAt,
      target_count: targetCount,
      current_index: currentIndex,
      current_aweme_id: this.currentAwemeId,
      current_video_url: this.location.href,
      current_caption_snippet: this.lastExtractedMetrics?.posted_text ?? this.lastHarvestedItem?.posted_text ?? null,
      harvested_count: harvestedCount,
      processed_count: processedCount,
      updated_count: updatedCount,
      skipped_count: skippedCount,
      remaining_count: Math.max(0, targetCount - processedCount),
      pending_count: this.pendingById.size,
      duplicate_count: this.duplicateCount,
      consecutive_duplicate_count: this.consecutiveDuplicateCount,
      failed_count: failedCount,
      flushed_count: this.flushedAwemeIds.size,
      elapsed_seconds: elapsedSeconds,
      average_seconds_per_item: averageSecondsPerItem,
      eta_seconds: etaSeconds,
      last_error: this.lastError,
      stopped_reason: this.stoppedReason,
      failed_at_index: this.clampedIndex(this.failedAtIndex),
      failed_aweme_id: this.failedAwemeId,
      can_resume: this.canResume(),
      detector_diagnostics: this.detectorDiagnostics,
      flush_url: this.flushUrl,
      flush_status_code: this.flushStatusCode,
      flush_error_code: this.flushErrorCode,
      flush_error_message: this.flushErrorMessage,
      flush_retryable: this.flushRetryable,
      flush_next_action: this.flushNextAction,
      pending_count_before_flush: this.pendingCountBeforeFlush,
      pending_count_after_flush: this.pendingCountAfterFlush,
      last_flush_status: this.lastFlushStatus,
      next_flush_in_items: Math.max(0, this.config.flush_every_n_items - this.pendingById.size),
      backend_response_summary: this.backendResponseSummary,
      last_harvested_item: this.lastHarvestedItem,
      last_extracted_metrics: this.lastExtractedMetrics,
      recent_items: this.recentItems.slice(-5),
      calibration_status: this.lastExtractedMetrics?.calibration_status ?? "missing",
      calibrated_viewport: this.lastExtractedMetrics?.calibrated_viewport ?? null,
      current_viewport: this.lastExtractedMetrics?.current_viewport ?? null,
      next_point_status: this.nextPointStatus,
      previous_aweme_id: this.previousAwemeId,
      navigation_retries: this.navigationRetries,
      last_navigation_result: this.lastNavigationResult,
      failed_stage: this.failedStage,
      mode: this.mode,
      target_status_map: this.targetStatusMapObject(),
      failed_targets: failedTargets,
      retry_failed_current: this.mode === "retry_failed" ? processedCount : 0,
      retry_failed_total: this.mode === "retry_failed" ? targetCount : 0
    };
  }

  stop(reason = "operator_stopped"): void {
    this.stopRequested = true;
    this.stoppedReason = reason;
    if (reason === "operator_stopped") {
      this.running = false;
      this.phase = this.canResume() || this.processedTargetCount() < this.effectiveTargetCount() ? "paused" : "stopped";
      this.lastError = null;
    }
  }

  async start(): Promise<FullModalHarvestProgress> {
    if (this.running) return this.progress;
    this.running = true;
    this.refreshHeartbeat(true);
    this.stopRequested = false;
    this.setPhase("harvesting", "navigating");
    this.lastError = null;
    if (this.isHarvestComplete()) {
      await this.completeBatch();
      this.running = false;
      return this.progress;
    }
    if (["operator_stopped", "backend_flush_failed", "navigation_timeout", "captcha_or_login_wall_detected", "no_next_video", "target_count_reached", "completed"].includes(this.stoppedReason ?? "")) {
      this.stoppedReason = null;
      this.failedStage = null;
    }
    await this.persistState();
    try {
      let firstTarget = this.nextTargetAwemeId(null);
      if (this.targetAwemeIds.length && (!firstTarget || this.isHarvestComplete())) {
        await this.completeBatch();
        return this.progress;
      }
      const currentResumeAwemeId = detectCurrentAwemeId(this.location.href, this.document);
      if (firstTarget && currentResumeAwemeId !== firstTarget) {
        this.prepareForTargetChange(firstTarget, "initial_target_navigation");
        await navigateDirectlyToTargetModal(this.location, this.document, currentResumeAwemeId ?? "", firstTarget, Math.min(12_000, Math.max(1, this.config.per_item_timeout_ms)));
      }
      while (!this.stopRequested && this.processedTargetCount() < this.effectiveTargetCount()) {
        this.refreshHeartbeat();
        if (this.config.stop_on_captcha && detectCaptchaOrLoginWall(this.document, this.location.href)) {
          this.stoppedReason = "captcha_or_login_wall_detected";
          break;
        }
        let awemeId = detectCurrentAwemeId(this.location.href, this.document);
        const expectedTargetAwemeId = this.targetAwemeIds.length ? this.nextTargetAwemeId(this.currentAwemeId) : awemeId;
        if (!expectedTargetAwemeId) break;
        this.prepareForTargetChange(expectedTargetAwemeId, "target_selected");
        awemeId = detectCurrentAwemeId(this.location.href, this.document);
        if (awemeId !== expectedTargetAwemeId) {
          const navigation = await navigateDirectlyToTargetModal(this.location, this.document, awemeId ?? "", expectedTargetAwemeId, Math.min(12_000, Math.max(1, this.config.per_item_timeout_ms)));
          this.lastNavigationResult = navigation.last_result ?? null;
          this.failedStage = navigation.failed_stage ?? null;
          awemeId = detectCurrentAwemeId(this.location.href, this.document);
          if (!navigation.moved || awemeId !== expectedTargetAwemeId) {
            this.handleIntegrityMismatch(expectedTargetAwemeId, awemeId, "modal_target_mismatch");
            this.recordFailedItem(expectedTargetAwemeId, "data_integrity_mismatch");
            await this.persistState();
            continue;
          }
        }
        this.currentAwemeId = awemeId;
        this.detectorDiagnostics = getCurrentAwemeDetectorDiagnostics(this.location, this.document);
        this.setPhase("extracting_metrics", "extracting");
        await this.persistState();
        if (!awemeId) {
          this.lastError = "current_aweme_id_missing";
          this.stoppedReason = "navigation_timeout";
          this.debug("current_aweme_id_missing", {
            harvested_count: this.harvestedAwemeIds.size,
            pending_count: this.pendingById.size,
            location_href: this.location.href,
            detector_diagnostics: this.detectorDiagnostics
          });
          await this.persistState();
          break;
        }
        const integrityMatch = this.assertCurrentModalMatchesTarget(expectedTargetAwemeId);
        if (!integrityMatch.ok) {
          this.handleIntegrityMismatch(expectedTargetAwemeId, integrityMatch.observedAwemeId, integrityMatch.reason);
          this.recordFailedItem(expectedTargetAwemeId, "data_integrity_mismatch");
          const nextTargetAfterIntegrityFailure = this.nextTargetAwemeId(expectedTargetAwemeId);
          if (nextTargetAfterIntegrityFailure) {
            await navigateDirectlyToTargetModal(this.location, this.document, awemeId, nextTargetAfterIntegrityFailure, Math.min(12_000, Math.max(1, this.config.per_item_timeout_ms)));
            continue;
          }
        }
        const settleReady = await this.waitForModalMetricsReady(expectedTargetAwemeId);
        if (!settleReady) {
          this.handleIntegrityMismatch(expectedTargetAwemeId, detectCurrentAwemeId(this.location.href, this.document), "modal_metrics_timeout");
          this.recordFailedItem(expectedTargetAwemeId, "modal_metrics_timeout");
          const nextTargetAfterSettleFailure = this.nextTargetAwemeId(expectedTargetAwemeId);
          if (nextTargetAfterSettleFailure) {
            await navigateDirectlyToTargetModal(this.location, this.document, awemeId, nextTargetAfterSettleFailure, Math.min(12_000, Math.max(1, this.config.per_item_timeout_ms)));
            continue;
          }
        }
        const extracted = await waitForCurrentModalMetrics(
          this.document,
          this.location,
          expectedTargetAwemeId,
          this.config.per_item_timeout_ms,
          await this.callbacks.getCalibration?.()
        );
        if (!extracted) {
          const reason = detectCaptchaOrLoginWall(this.document, this.location.href) ? "captcha_or_login_wall_detected" : "modal_metrics_timeout";
          this.recordFailedItem(expectedTargetAwemeId, reason);
          if (await this.completeIfHarvestComplete()) break;
          this.consecutiveFailures += 1;
          this.lastError = reason;
          if (reason === "captcha_or_login_wall_detected" || this.consecutiveFailures >= 3) {
            this.stoppedReason = reason === "captcha_or_login_wall_detected" ? reason : "navigation_timeout";
            this.phase = "failed";
            await this.persistState();
            break;
          }
          await this.persistState();
          if (await this.completeIfHarvestComplete()) break;
          const nextAfterFailure = this.nextTargetAwemeId(awemeId);
          if (nextAfterFailure) await navigateDirectlyToTargetModal(this.location, this.document, awemeId, nextAfterFailure, Math.min(12_000, Math.max(1, this.config.per_item_timeout_ms)));
          continue;
        }
        const extractedProbe = probeFromHarvestedItem(extracted);
        this.rememberExtractedMetrics(extractedProbe);
        this.itemStage = "extracted";
        this.extractedAtMs = Date.now();
        this.lastCommitResult = null;
        this.debug("modal_metrics_extracted", {
          current_aweme_id: awemeId,
          raw_dom_detail_metrics: extracted.raw_dom_detail_metrics,
          harvested_count: this.harvestedAwemeIds.size,
          pending_count: this.pendingById.size
        });
        if (this.targetAwemeIds.length && !this.targetStatusById.has(awemeId)) {
          this.lastError = "out_of_queue";
          await this.persistState();
          const nextInQueue = this.nextTargetAwemeId(awemeId);
          if (nextInQueue) await navigateDirectlyToTargetModal(this.location, this.document, awemeId, nextInQueue, Math.min(12_000, Math.max(1, this.config.per_item_timeout_ms)));
          continue;
        }
        const currentTargetStatus = this.targetStatusById.get(awemeId);
        const alreadyProcessedQueueTarget = Boolean(currentTargetStatus && currentTargetStatus.status !== "pending");
        if (alreadyProcessedQueueTarget || this.harvestedAwemeIds.has(awemeId)) {
          if (this.lastNavigationAttemptFromAwemeId) {
            this.duplicateCount += 1;
            this.consecutiveDuplicateCount += 1;
          }
          this.debug("duplicate_aweme_id_skipped", {
            current_aweme_id: awemeId,
            harvested_count: this.harvestedAwemeIds.size,
            pending_count: this.pendingById.size,
            duplicate_count: this.duplicateCount,
            consecutive_duplicate_count: this.consecutiveDuplicateCount
          });
          if (alreadyProcessedQueueTarget && this.consecutiveDuplicateCount >= 3) this.recordFailedItem(awemeId, "duplicate_loop");
          await this.persistState();
          const nextAfterDuplicate = this.nextTargetAwemeId(awemeId);
          if (nextAfterDuplicate) await navigateDirectlyToTargetModal(this.location, this.document, awemeId, nextAfterDuplicate, Math.min(12_000, Math.max(1, this.config.per_item_timeout_ms)));
          continue;
        } else {
          const strictExtracted = this.buildIntegrityBoundItem(expectedTargetAwemeId, extracted);
          const integrity = this.validateItemDataIntegrity(expectedTargetAwemeId, strictExtracted, extractedProbe);
          if (!integrity.ok) {
            this.handleIntegrityMismatch(awemeId, integrity.observedAwemeId, integrity.reason);
            if (this.consecutiveFailures >= 3) {
              this.recordFailedItem(awemeId, "data_integrity_mismatch");
            }
            await this.persistState();
            const nextAfterIntegrityMismatch = this.nextTargetAwemeId(awemeId);
            if (nextAfterIntegrityMismatch) await navigateDirectlyToTargetModal(this.location, this.document, awemeId, nextAfterIntegrityMismatch, Math.min(12_000, Math.max(1, this.config.per_item_timeout_ms)));
            continue;
          }
          this.commitValidatedModalMetrics(expectedTargetAwemeId, strictExtracted);
          this.refreshHeartbeat(true);
          this.debug("harvest_state_updated", {
            current_aweme_id: awemeId,
            harvested_count: this.harvestedAwemeIds.size,
            pending_count: this.pendingById.size,
            last_harvested_item: this.lastHarvestedItem
          });
          await this.persistState();
          if (await this.completeIfHarvestComplete()) break;
        }
        this.consecutiveFailures = 0;
        if (this.pendingById.size >= this.config.flush_every_n_items) {
          const flushResult = await this.flushInternal();
          if (!flushResult.success) {
            this.stoppedReason = "backend_flush_failed";
            break;
          }
          if (await this.completeIfHarvestComplete()) break;
        }
        if (await this.completeIfHarvestComplete()) break;
        const navigation = await this.navigateAfterItem(awemeId);
        if (!navigation.moved) {
          if (await this.skipFailedTargetAndContinue(navigation, awemeId)) continue;
          this.applyNavigationFailure(navigation);
          await this.persistState();
          break;
        }
      }
      if (!this.stoppedReason && this.stopRequested) this.stoppedReason = "operator_stopped";
      if (!this.stoppedReason) await this.completeBatch();
      else if (this.stoppedReason !== "backend_flush_failed" && this.pendingById.size > 0) {
        const flushResult = await this.flushInternal();
        if (!flushResult.success) this.stoppedReason = "backend_flush_failed";
      }
      if (this.stoppedReason === "operator_stopped") {
        this.setPhase(this.canResume() || this.processedTargetCount() < this.effectiveTargetCount() ? "paused" : "stopped", "navigating");
        this.lastError = null;
      } else if (this.stoppedReason) this.setPhase("failed", "navigating");
      return this.progress;
    } finally {
      this.running = false;
      this.refreshHeartbeat(false);
      await this.persistState();
      if (!this.canResume() && this.pendingById.size === 0) await this.callbacks.clearState();
    }
  }

  async flush(options?: { keepalive?: boolean }): Promise<FullModalHarvestProgress> {
    await this.flushInternal(options);
    return this.progress;
  }

  async persistState(): Promise<void> {
    await this.callbacks.saveState(this.snapshotState());
  }

  snapshotState(): StoredFullModalHarvestState {
    return {
      harvest_id: this.harvestId,
      harvest_status: this.harvestStatus(),
      harvest_loop_heartbeat_at: this.harvestLoopHeartbeatAt,
      session_id: this.config.captureSessionId ?? null,
      target_count: this.effectiveTargetCount(),
      started_at: this.startedAt,
      updated_at: new Date().toISOString(),
      current_aweme_id: this.currentAwemeId,
      current_video_url: this.location.href,
      phase: this.phase,
      current_state: this.progressCurrentState(),
      item_stage: this.itemStage,
      phase_elapsed_ms: this.phaseElapsedMs(),
      extracted_not_committed_ms: this.extractedNotCommittedMs(),
      last_commit_result: this.lastCommitResult,
      repair_extracted_not_committed_count: this.repairExtractedNotCommittedCount,
      integrity_mismatch_count: this.integrityMismatchCount,
      last_integrity_error: this.lastIntegrityError,
      last_integrity_expected_aweme_id: this.lastIntegrityExpectedAwemeId,
      last_integrity_observed_aweme_id: this.lastIntegrityObservedAwemeId,
      last_integrity_checked_at: this.lastIntegrityCheckedAt,
      harvested_aweme_ids: Array.from(this.harvestedAwemeIds),
      pending_items: Array.from(this.pendingById.values()),
      pending_flush_queue: this.pendingFlushQueue,
      flushed_aweme_ids: Array.from(this.flushedAwemeIds),
      failed_items: Array.from(this.failedById.values()),
      target_status_map: this.targetStatusMapObject(),
      mode: this.mode,
      consecutive_failures: this.consecutiveFailures,
      duplicate_count: this.duplicateCount,
      consecutive_duplicate_count: this.consecutiveDuplicateCount,
      updated_count: this.updatedCount,
      stopped_reason: this.stoppedReason,
      last_error: this.lastError,
      failed_at_index: this.clampedIndex(this.failedAtIndex),
      failed_aweme_id: this.failedAwemeId,
      last_flush_status: this.lastFlushStatus,
      detector_diagnostics: this.detectorDiagnostics,
      flush_url: this.flushUrl,
      flush_status_code: this.flushStatusCode,
      flush_error_code: this.flushErrorCode,
      flush_error_message: this.flushErrorMessage,
      flush_retryable: this.flushRetryable,
      flush_next_action: this.flushNextAction,
      pending_count_before_flush: this.pendingCountBeforeFlush,
      pending_count_after_flush: this.pendingCountAfterFlush,
      backend_response_summary: this.backendResponseSummary,
      last_harvested_item: this.lastHarvestedItem,
      last_extracted_metrics: this.lastExtractedMetrics,
      recent_items: this.recentItems.slice(-5),
      calibration: null,
      next_point_status: this.nextPointStatus,
      previous_aweme_id: this.previousAwemeId,
      navigation_retries: this.navigationRetries,
      last_navigation_result: this.lastNavigationResult,
      failed_stage: this.failedStage,
      target_aweme_ids: this.targetAwemeIds,
      config: {
        target_count: this.effectiveTargetCount(),
        delay_between_items_ms: this.config.delay_between_items_ms,
        per_item_timeout_ms: this.config.per_item_timeout_ms,
        flush_every_n_items: this.config.flush_every_n_items,
        stop_on_captcha: this.config.stop_on_captcha,
        stop_on_no_next: this.config.stop_on_no_next,
        allow_probe_warnings: this.config.allow_probe_warnings,
        target_aweme_ids: this.targetAwemeIds,
        retry_failed_only: this.mode === "retry_failed"
      }
    };
  }

  async bootstrapCurrentItem(): Promise<string | null> {
    this.setPhase("extracting_metrics", "extracting");
    this.currentAwemeId = detectCurrentAwemeId(this.location.href, this.document);
    this.detectorDiagnostics = getCurrentAwemeDetectorDiagnostics(this.location, this.document);
    if (!this.currentAwemeId) {
      this.lastError = "current_aweme_id_missing";
      this.debug("bootstrap_current_aweme_missing", {
        detector_diagnostics: this.detectorDiagnostics
      });
      await this.persistState();
      return null;
    }
    const extracted = await waitForCurrentModalMetrics(
      this.document,
      this.location,
      this.currentAwemeId,
      this.config.per_item_timeout_ms,
      await this.callbacks.getCalibration?.()
    );
    if (!extracted) {
      this.lastError = detectCaptchaOrLoginWall(this.document, this.location.href) ? "captcha_or_login_wall_detected" : "modal_metrics_timeout";
      this.debug("bootstrap_modal_metrics_not_extracted", {
        current_aweme_id: this.currentAwemeId,
        detector_diagnostics: this.detectorDiagnostics,
        last_error: this.lastError
      });
      await this.persistState();
      return this.currentAwemeId;
    }
    if (!this.harvestedAwemeIds.has(this.currentAwemeId)) {
      const bootstrapProbe = probeFromHarvestedItem(extracted);
      const strictBootstrapExtracted = this.buildIntegrityBoundItem(this.currentAwemeId, extracted);
      const integrity = this.validateItemDataIntegrity(this.currentAwemeId, strictBootstrapExtracted, bootstrapProbe);
      if (!integrity.ok) {
        this.handleIntegrityMismatch(this.currentAwemeId, integrity.observedAwemeId, integrity.reason);
        if (this.consecutiveFailures >= 3) this.recordFailedItem(this.currentAwemeId, "data_integrity_mismatch");
        await this.persistState();
        return this.currentAwemeId;
      }
      this.rememberExtractedMetrics(bootstrapProbe);
      this.commitValidatedModalMetrics(this.currentAwemeId, strictBootstrapExtracted);
      this.debug("bootstrap_modal_metrics_extracted", {
        current_aweme_id: this.currentAwemeId,
        raw_dom_detail_metrics: extracted.raw_dom_detail_metrics,
        harvested_count: this.harvestedAwemeIds.size,
        pending_count: this.pendingById.size,
        last_harvested_item: this.lastHarvestedItem,
        detector_diagnostics: this.detectorDiagnostics
      });
      await this.persistState();
    }
    return this.currentAwemeId;
  }

  private initializeTargetStatuses(initialState?: StoredFullModalHarvestState | null): void {
    const now = new Date().toISOString();
    for (const [offset, awemeId] of this.targetAwemeIds.entries()) {
      const stored = initialState?.target_status_map?.[awemeId];
      this.targetStatusById.set(awemeId, {
        aweme_id: awemeId,
        index: offset + 1,
        status: stored?.status ?? "pending",
        reason: stored?.reason ?? null,
        attempts: stored?.attempts ?? 0,
        updated_at: stored?.updated_at ?? now
      });
    }
    for (const awemeId of this.harvestedAwemeIds) this.markTargetStatus(awemeId, "updated", null, false);
    for (const item of this.failedById.values()) this.markTargetStatus(item.aweme_id, "failed", item.reason, false);
    if (this.mode === "retry_failed") {
      for (const awemeId of this.targetAwemeIds) this.markTargetStatus(awemeId, "pending", null, false);
    }
  }

  private effectiveTargetCount(): number {
    return this.targetAwemeIds.length > 0 ? this.targetAwemeIds.length : this.config.target_count;
  }

  private targetStatusMapObject(): Record<string, FullModalHarvestTargetStatus> {
    return Object.fromEntries(Array.from(this.targetStatusById.entries()).map(([awemeId, status]) => [awemeId, { ...status }]));
  }

  private processedTargetCount(): number {
    if (!this.targetStatusById.size) return this.harvestedAwemeIds.size;
    return Array.from(this.targetStatusById.values()).filter((item) => item.status === "updated" || item.status === "failed" || item.status === "skipped").length;
  }

  private isHarvestComplete(): boolean {
    const targetCount = this.effectiveTargetCount();
    if (targetCount <= 0) return false;
    if (this.targetAwemeIds.length > 0) {
      return this.targetAwemeIds.every((awemeId) => {
        const status = this.targetStatusById.get(awemeId)?.status;
        return status === "updated" || status === "failed" || status === "skipped";
      });
    }
    return this.processedTargetCount() >= targetCount;
  }

  private async completeIfHarvestComplete(): Promise<boolean> {
    if (!this.isHarvestComplete()) return false;
    await this.completeBatch();
    return true;
  }

  private updatedTargetCount(): number {
    return this.targetStatusById.size ? Array.from(this.targetStatusById.values()).filter((item) => item.status === "updated").length : this.updatedCount;
  }

  private failedTargetCount(): number {
    return this.targetStatusById.size ? Array.from(this.targetStatusById.values()).filter((item) => item.status === "failed").length : this.failedById.size;
  }

  private skippedTargetCount(): number {
    return Array.from(this.targetStatusById.values()).filter((item) => item.status === "skipped").length;
  }

  private failedTargetStatuses(): FullModalHarvestTargetStatus[] {
    return Array.from(this.targetStatusById.values()).filter((item) => item.status === "failed").sort((a, b) => a.index - b.index);
  }

  private currentTargetIndex(): number {
    const targetCount = this.effectiveTargetCount();
    if (targetCount <= 0) return 0;
    if (this.currentAwemeId && this.targetStatusById.has(this.currentAwemeId)) return this.clampedIndex(this.targetStatusById.get(this.currentAwemeId)?.index ?? null) ?? 0;
    return Math.min(targetCount, this.processedTargetCount() + 1);
  }

  private clampedIndex(index: number | null | undefined): number | null {
    if (index == null) return null;
    return Math.min(Math.max(1, index), Math.max(1, this.effectiveTargetCount()));
  }

  private clampFailureIndex(): void {
    this.failedAtIndex = this.clampedIndex(this.failedAtIndex);
  }

  private markTargetStatus(awemeId: string, status: FullModalHarvestTargetStatus["status"], reason: string | null, incrementAttempt = true): FullModalHarvestTargetStatus | null {
    const existing = this.targetStatusById.get(awemeId);
    if (!existing) return null;
    const next = { ...existing, status, reason, attempts: existing.attempts + (incrementAttempt ? 1 : 0), updated_at: new Date().toISOString() };
    this.targetStatusById.set(awemeId, next);
    return next;
  }

  private canResume(): boolean {
    return !this.isHarvestComplete() && this.stoppedReason !== "completed" && this.progressCurrentState() !== "completed_with_warnings";
  }

  private async navigateAfterItem(awemeId: string): Promise<NavigationResult> {
    if (this.isHarvestComplete() || (this.targetAwemeIds.length > 0 && !this.nextTargetAwemeId(awemeId))) return { moved: false, retries: 0, last_result: "next_point_missing", reason: "no_next_control" };
    this.previousAwemeId = awemeId;
    this.setPhase("loading_next_video", "navigating");
    this.lastNavigationResult = null;
    await this.persistState();
    this.nextPointStatus = "missing";
    this.setPhase("waiting_modal_change", "navigating");
    this.lastNavigationAttemptFromAwemeId = awemeId;
    await this.persistState();
    const navigationTimeoutMs = Math.min(12_000, Math.max(1, this.config.per_item_timeout_ms));
    const targetAwemeId = this.nextTargetAwemeId(awemeId);
    const navigation = targetAwemeId
      ? await navigateDirectlyToTargetModal(this.location, this.document, awemeId, targetAwemeId, navigationTimeoutMs)
      : await navigateNextModalAutomatically(this.document, this.location, awemeId, navigationTimeoutMs);
    const finalNavigation = navigation.moved ? navigation : await navigateNextModalAutomatically(this.document, this.location, awemeId, navigationTimeoutMs);
    this.navigationRetries += (navigation.retries ?? 0) + (navigation.moved ? 0 : finalNavigation.retries ?? 0);
    this.lastNavigationResult = finalNavigation.last_result ?? (finalNavigation.moved ? "modal_changed" : "timeout");
    if (finalNavigation.moved) {
      this.setPhase("extracting_metrics", "extracting");
      this.currentAwemeId = detectCurrentAwemeId(this.location.href, this.document);
      this.consecutiveDuplicateCount = 0;
      // Metrics readiness below replaces the old fixed multi-second settle delay.
      const navigationSettleMs = Math.min(this.config.delay_between_items_ms, 150);
      if (navigationSettleMs > 0) await wait(navigationSettleMs);
      await this.persistState();
    }
    return { ...finalNavigation, target_aweme_id: targetAwemeId };
  }

  private nextTargetAwemeId(currentAwemeId: string | null): string | null {
    if (!this.targetAwemeIds.length) return null;
    const currentIndex = currentAwemeId ? this.targetAwemeIds.indexOf(currentAwemeId) : -1;
    const candidates = currentIndex >= 0 ? this.targetAwemeIds.slice(currentIndex + 1) : this.targetAwemeIds;
    return candidates.find((awemeId) => this.targetStatusById.get(awemeId)?.status === "pending") ?? this.targetAwemeIds.find((awemeId) => this.targetStatusById.get(awemeId)?.status === "pending") ?? null;
  }

  private async skipFailedTargetAndContinue(navigation: NavigationResult, currentAwemeId: string): Promise<boolean> {
    if (await this.completeIfHarvestComplete()) return true;
    if (!this.targetAwemeIds.length) return false;
    const failedTarget = navigation.target_aweme_id ?? this.nextTargetAwemeId(currentAwemeId);
    if (!failedTarget) return false;
    this.recordFailedItem(failedTarget, "modal_navigation_stuck");
    this.lastNavigationResult = navigation.last_result ?? "timeout";
    this.failedStage = navigation.failed_stage ?? "modal_id_change_timeout";
    this.lastError = `Skipped stuck video ${failedTarget}; continuing batch.`;
    await this.persistState();
    await this.completeIfHarvestComplete();
    return true;
  }

  private async completeBatch(): Promise<void> {
    if (this.pendingById.size > 0) {
      const flushResult = await this.flushInternal();
      if (!flushResult.success) {
        this.stoppedReason = "backend_flush_failed";
        this.phase = "failed";
        return;
      }
    }
    this.phase = this.failedTargetCount() > 0 ? "completed_with_warnings" : "completed";
    this.stoppedReason = null;
    this.lastError = this.failedTargetCount() > 0 ? `Harvest completed with warnings. Updated ${this.updatedTargetCount()}/${this.effectiveTargetCount()}. Failed ${this.failedTargetCount()}.` : null;
    await this.persistState();
  }

  private applyNavigationFailure(navigation: NavigationResult): void {
    this.lastNavigationResult = navigation.last_result ?? "timeout";
    this.failedStage = navigation.failed_stage ?? (navigation.reason === "duplicate_loop_detected" ? "duplicate_loop_detected" : "modal_id_change_timeout");
    this.lastError = this.failedStage === "duplicate_loop_detected" ? "duplicate_loop_detected" : "Press ArrowDown manually or click next video, then Resume Harvest.";
    this.stoppedReason = "navigation_timeout";
  }

  private harvestStatus(): FullModalHarvestStatus {
    if (this.phase === "completed_with_warnings" || (this.phase === "completed" && this.failedTargetCount() > 0)) return "completed_with_warnings";
    if (this.phase === "completed") return "completed";
    if (this.stoppedReason === "backend_flush_failed" && this.pendingById.size > 0) return "paused";
    if (this.running) return "running";
    if (this.phase === "failed" || (this.stoppedReason && this.stoppedReason !== "operator_stopped")) return "failed";
    if (this.phase === "paused" || this.phase === "stopped" || this.stoppedReason === "operator_stopped" || this.canResume()) return "paused";
    return "idle";
  }

  private setPhase(phase: FullModalHarvestPhase, itemStage?: NonNullable<FullModalHarvestProgress["item_stage"]>): void {
    this.phase = phase;
    this.phaseStartedAtMs = Date.now();
    if (itemStage) this.itemStage = itemStage;
  }

  private phaseElapsedMs(): number {
    return Math.max(0, Date.now() - this.phaseStartedAtMs);
  }

  private extractedNotCommittedMs(): number | null {
    if (this.itemStage !== "extracted" || this.extractedAtMs == null) return null;
    return Math.max(0, Date.now() - this.extractedAtMs);
  }

  private refreshHeartbeat(force = false): void {
    if (!this.running && !force) return;
    const now = Date.now();
    const previous = this.harvestLoopHeartbeatAt ? new Date(this.harvestLoopHeartbeatAt).getTime() : 0;
    if (force || !Number.isFinite(previous) || now - previous >= 1_000) this.harvestLoopHeartbeatAt = new Date(now).toISOString();
  }

  private progressCurrentState(): FullModalHarvestCurrentState {
    if (this.phase === "completed_with_warnings") return "completed_with_warnings";
    if (this.phase === "completed" && this.failedTargetCount() > 0) return "completed_with_warnings";
    if (this.phase === "completed") return "completed";
    if (this.phase === "failed") return "failed";
    if (this.phase === "paused") return "paused";
    if (this.phase === "stopped") return "stopped";
    if (this.stoppedReason === "operator_stopped") return this.canResume() || this.processedTargetCount() < this.effectiveTargetCount() ? "paused" : "stopped";
    if (this.running || this.phase !== "starting") return "harvesting";
    return "starting";
  }

  private recordFailedItem(awemeId: string, reason: string): void {
    const targetStatus = this.markTargetStatus(awemeId, "failed", reason);
    const index = targetStatus?.index ?? this.clampedIndex(this.harvestedAwemeIds.size + this.failedById.size + 1) ?? 1;
    this.failedById.set(awemeId, { aweme_id: awemeId, reason });
    this.failedAtIndex = this.clampedIndex(index);
    this.failedAwemeId = awemeId;
    this.recentItems.push({
      index,
      aweme_id: awemeId,
      duration_seconds: null,
      duration_text: null,
      like_count: null,
      comment_count: null,
      favorite_count: null,
      share_count: null,
      posted_text: null,
      extraction_warning: reason,
      status: "failed",
      reason
    });
    while (this.recentItems.length > 5) this.recentItems.shift();
  }

  private rememberExtractedMetrics(probe: FullModalHarvestProbeResult): void {
    this.lastExtractedMetrics = probe;
    this.itemStage = "extracted";
    this.extractedAtMs = Date.now();
  }

  private clearStaleExtractedMetrics(reason: string): void {
    if (this.itemStage === "extracted") this.repairExtractedNotCommittedCount += 1;
    this.lastExtractedMetrics = null;
    this.lastHarvestedItem = null;
    this.extractedAtMs = null;
    this.lastCommitResult = "retryable_failed";
    this.lastIntegrityError = reason;
  }

  private prepareForTargetChange(targetAwemeId: string, reason: string): void {
    this.clearStaleExtractedMetrics(reason);
    const pending = this.pendingById.get(targetAwemeId);
    if (pending && pending.data_integrity_status !== "passed") {
      this.pendingById.delete(targetAwemeId);
      this.pendingFlushQueue = this.pendingFlushQueue.filter((item) => item.aweme_id !== targetAwemeId);
    }
    this.currentAwemeId = targetAwemeId;
    this.itemStage = "navigating";
    this.lastIntegrityExpectedAwemeId = targetAwemeId;
  }

  private assertCurrentModalMatchesTarget(targetAwemeId: string): { ok: true } | { ok: false; observedAwemeId: string | null; reason: string } {
    const observedAwemeId = detectCurrentAwemeId(this.location.href, this.document);
    if (observedAwemeId === targetAwemeId) return { ok: true };
    return { ok: false, observedAwemeId, reason: "modal_target_mismatch" };
  }

  private metricSignature(item: FullModalHarvestItemPayload): string {
    const d = item.raw_dom_detail_metrics;
    return [d.duration_seconds ?? "-", d.like_count ?? "-", d.comment_count ?? "-", d.favorite_count ?? "-", d.share_count ?? "-"].join("|");
  }

  private buildIntegrityBoundItem(targetAwemeId: string, extracted: FullModalHarvestItemPayload): FullModalHarvestItemPayload {
    const beforeAwemeId = detectCurrentAwemeId(this.location.href, this.document);
    const afterAwemeId = detectCurrentAwemeId(this.location.href, this.document);
    const signature = this.metricSignature(extracted);
    const duplicateWarning = this.duplicateWarningForSignature(targetAwemeId, signature);
    return {
      ...extracted,
      aweme_id: targetAwemeId,
      target_aweme_id: targetAwemeId,
      source_video_external_id: targetAwemeId,
      page_url: this.location.href,
      modal_id: afterAwemeId,
      modal_aweme_id_before_extract: beforeAwemeId,
      modal_aweme_id_after_extract: afterAwemeId,
      extracted_aweme_id: extracted.aweme_id,
      raw_dom_detail_metrics: {
        ...extracted.raw_dom_detail_metrics,
        aweme_id: extracted.aweme_id,
        target_aweme_id: targetAwemeId
      },
      data_integrity_status: "pending",
      data_integrity_reason: null,
      metric_signature: signature,
      duplicate_signature_warning: duplicateWarning
    };
  }

  private duplicateWarningForSignature(targetAwemeId: string, signature: string): string | null {
    for (const [awemeId, existingSignature] of this.metricSignatureByAwemeId.entries()) {
      if (awemeId !== targetAwemeId && existingSignature === signature) return this.lastNavigationAttemptFromAwemeId ? "possible_stale_metrics_reuse_high_severity" : "possible_stale_metrics_reuse";
    }
    return null;
  }

  private async waitForModalMetricsReady(targetAwemeId: string): Promise<boolean> {
    const matched = await waitForModalIdMatch(() => detectCurrentAwemeId(this.location.href, this.document), targetAwemeId, Math.min(2_500, Math.max(500, Math.floor(this.config.per_item_timeout_ms / 4))));
    if (!matched) return false;

    const calibration = await this.callbacks.getCalibration?.();
    const deadline = Date.now() + Math.min(this.config.per_item_timeout_ms, 2_500);
    let lastReadySignature: string | null = null;
    let lastReadyAt = 0;
    while (Date.now() < deadline) {
      if (detectCurrentAwemeId(this.location.href, this.document) !== targetAwemeId) return false;
      const probe = probeCurrentModalMetrics(this.document, this.location, calibration);
      if (this.probeReadyForCommit(targetAwemeId, probe)) {
        const signature = this.metricProbeSignature(probe);
        const nowMs = Date.now();
        if (signature === lastReadySignature && nowMs - lastReadyAt >= 150) return true;
        lastReadySignature = signature;
        lastReadyAt = nowMs;
      } else {
        lastReadySignature = null;
        lastReadyAt = 0;
      }
      await wait(75);
    }
    return false;
  }

  private probeReadyForCommit(targetAwemeId: string, probe: FullModalHarvestProbeResult): boolean {
    return probe.aweme_id === targetAwemeId && typeof probe.duration_seconds === "number" && Number.isFinite(probe.duration_seconds) && probe.duration_seconds > 0 && [probe.like_count, probe.comment_count, probe.favorite_count, probe.share_count].every((value) => typeof value === "number" && Number.isFinite(value));
  }

  private metricProbeSignature(probe: FullModalHarvestProbeResult): string {
    return [probe.duration_seconds ?? "-", probe.like_count ?? "-", probe.comment_count ?? "-", probe.favorite_count ?? "-", probe.share_count ?? "-"].join("|");
  }

  private validateItemDataIntegrity(targetAwemeId: string, item: FullModalHarvestItemPayload, probe: FullModalHarvestProbeResult): { ok: true } | { ok: false; observedAwemeId: string | null; reason: string } {
    if (item.target_aweme_id !== targetAwemeId) return { ok: false, observedAwemeId: item.target_aweme_id ?? null, reason: "data_integrity_mismatch" };
    if (item.modal_aweme_id_before_extract !== targetAwemeId) return { ok: false, observedAwemeId: item.modal_aweme_id_before_extract ?? null, reason: "data_integrity_mismatch" };
    if (item.modal_aweme_id_after_extract !== targetAwemeId) return { ok: false, observedAwemeId: item.modal_aweme_id_after_extract ?? null, reason: "data_integrity_mismatch" };
    if (item.extracted_aweme_id !== targetAwemeId) return { ok: false, observedAwemeId: item.extracted_aweme_id ?? null, reason: "data_integrity_mismatch" };
    if (item.aweme_id !== targetAwemeId) return { ok: false, observedAwemeId: item.aweme_id, reason: "data_integrity_mismatch" };
    if (item.source_video_external_id !== targetAwemeId) return { ok: false, observedAwemeId: item.source_video_external_id ?? null, reason: "data_integrity_mismatch" };
    if (item.raw_dom_detail_metrics.target_aweme_id !== targetAwemeId) return { ok: false, observedAwemeId: item.raw_dom_detail_metrics.target_aweme_id ?? null, reason: "data_integrity_mismatch" };
    if (item.raw_dom_detail_metrics.aweme_id && item.raw_dom_detail_metrics.aweme_id !== targetAwemeId) return { ok: false, observedAwemeId: item.raw_dom_detail_metrics.aweme_id, reason: "data_integrity_mismatch" };
    if (probe.aweme_id !== targetAwemeId) return { ok: false, observedAwemeId: probe.aweme_id, reason: "data_integrity_mismatch" };
    if (!this.probeReadyForCommit(targetAwemeId, probe)) return { ok: false, observedAwemeId: item.aweme_id ?? null, reason: "metric_numeric_invalid" };
    return { ok: true };
  }

  private handleIntegrityMismatch(expectedAwemeId: string, observedAwemeId: string | null, reason: string): void {
    this.integrityMismatchCount += 1;
    this.consecutiveFailures += 1;
    this.lastIntegrityError = reason;
    this.lastIntegrityExpectedAwemeId = expectedAwemeId;
    this.lastIntegrityObservedAwemeId = observedAwemeId;
    this.lastIntegrityCheckedAt = new Date().toISOString();
    this.lastError = reason;
    this.clearStaleExtractedMetrics(reason);
  }

  private commitValidatedModalMetrics(awemeId: string, item: FullModalHarvestItemPayload): void {
    const probe = probeFromHarvestedItem(item);
    const integrity = this.validateItemDataIntegrity(awemeId, item, probe);
    if (!integrity.ok) {
      this.handleIntegrityMismatch(awemeId, integrity.observedAwemeId, integrity.reason);
      this.recordFailedItem(awemeId, "data_integrity_mismatch");
      return;
    }
    const committedItem: FullModalHarvestItemPayload = { ...item, data_integrity_status: "passed", data_integrity_reason: null };
    this.itemStage = "committing";
    this.harvestedAwemeIds.add(awemeId);
    this.pendingById.set(awemeId, committedItem);
    this.pendingFlushQueue = upsertPendingFlushItem(this.pendingFlushQueue, buildPendingFlushItem(committedItem, this.config.captureSessionId ?? null));
    this.metricSignatureByAwemeId.set(awemeId, committedItem.metric_signature ?? this.metricSignature(committedItem));
    this.lastFlushStatus = "queued";
    this.setPhase("queued_item", "queued");
    this.consecutiveDuplicateCount = 0;
    this.lastNavigationAttemptFromAwemeId = null;
    this.lastCommitResult = null;
    this.extractedAtMs = null;
  }

  private rememberHarvestedItem(item: FullModalHarvestItemPayload, status: string): void {
    this.markTargetStatus(item.aweme_id, "updated", null);
    const targetIndex = this.targetStatusById.get(item.aweme_id)?.index ?? this.clampedIndex(this.harvestedAwemeIds.size);
    const summary = summarizeHarvestedItem(item, status, targetIndex);
    this.lastHarvestedItem = summary;
    this.recentItems.push(summary);
    while (this.recentItems.length > 5) this.recentItems.shift();
  }

  private async flushInternal(options?: { keepalive?: boolean }): Promise<FlushResult> {
    const pendingItems = Array.from(this.pendingById.values());
    if (!pendingItems.length) {
      return { success: true, updated_count: 0, flushed_aweme_ids: [], failed_count: 0, failure_summaries: [], unchanged_count: 0 };
    }
    this.setPhase("flushing", "flushing");
    this.pendingCountBeforeFlush = pendingItems.length;
    await this.persistState();
    const payload = buildFullModalHarvestRequestPayload({
      capture_session_id: this.config.captureSessionId ?? null,
      started_at: this.startedAt,
      page: this.page,
      capture_context: this.context,
      items: pendingItems,
      progress: this.progress,
      commit_policy: "finalized_only",
      diagnostics: {
        extension_source: "full_modal_auto_harvest",
        target_count: this.effectiveTargetCount(),
        flush_every_n_items: this.config.flush_every_n_items,
        harvest_id: this.harvestId
      }
    });
    this.debug("flush_payload_sample", {
      current_aweme_id: this.currentAwemeId,
      harvested_count: this.harvestedAwemeIds.size,
      pending_count: this.pendingById.size,
      flush_item_count: pendingItems.length,
      payload_sample: {
        capture_session_id: payload.capture_session_id,
        progress: payload.progress,
        first_item: payload.items[0] ?? null,
        diagnostics: payload.diagnostics
      }
    });
    const pendingAwemeIds = pendingItems.map((item) => item.aweme_id);
    this.pendingFlushQueue = markQueueFlushing(this.pendingFlushQueue, pendingAwemeIds);
    await this.persistState();
    try {
      let raw: Record<string, unknown> | null = null;
      let result: FlushResult | null = null;
      for (let attempt = 0; attempt < 3; attempt += 1) {
        raw = await this.callbacks.flushBatch(payload, options);
        result = normalizeFlushResult(raw, pendingAwemeIds);
        if (result.success || !result.flush_retryable) break;
        if (attempt < 2) {
          this.lastFlushStatus = "retrying";
          await wait(250 * 2 ** attempt);
        }
      }
      result = result ?? normalizeFlushResult(raw, pendingAwemeIds);
      this.flushUrl = result.flush_url ?? this.flushUrl;
      this.flushStatusCode = result.flush_status_code ?? null;
      this.flushErrorCode = result.flush_error_code ?? null;
      this.flushErrorMessage = result.flush_error_message ?? null;
      this.flushRetryable = result.flush_retryable ?? null;
      this.flushNextAction = flushNextActionForError(result.flush_error_code ?? null, result.flush_retryable ?? false, this.pendingById.size);
      this.backendResponseSummary = result.backend_response_summary ?? null;
      this.debug("flush_response_summary", {
        current_aweme_id: this.currentAwemeId,
        harvested_count: this.harvestedAwemeIds.size,
        pending_count: this.pendingById.size,
        flush_response_summary: {
          updated_count: result.updated_count,
          unchanged_count: result.unchanged_count,
          failed_count: result.failed_count,
          flushed_aweme_ids: result.flushed_aweme_ids,
          failure_summaries: result.failure_summaries
        }
      });
      const failedAwemeIds = new Set(result.failure_summaries.map((failure) => failure.aweme_id));
      for (const awemeId of result.flushed_aweme_ids) {
        const flushedItem = this.pendingById.get(awemeId);
        this.pendingById.delete(awemeId);
        this.flushedAwemeIds.add(awemeId);
        if (flushedItem && !failedAwemeIds.has(awemeId)) {
          this.markTargetStatus(awemeId, "updated", null, false);
          this.lastCommitResult = "success";
          this.rememberHarvestedItem(flushedItem, "ok");
        }
      }
      this.pendingFlushQueue = markQueueFlushed(this.pendingFlushQueue, result.flushed_aweme_ids);
      if (!result.success) this.pendingFlushQueue = markQueueFailed(this.pendingFlushQueue, pendingAwemeIds, { code: result.flush_error_code ?? null, message: result.flush_error_message ?? "backend_flush_failed", retryable: result.flush_retryable ?? true });
      this.pendingCountAfterFlush = this.pendingById.size;
      this.updatedCount = Math.max(this.updatedCount + result.updated_count, this.updatedTargetCount());
      this.lastFlushStatus = result.success ? "success" : result.flush_retryable ? "queued" : "failed";
      for (const failure of result.failure_summaries) {
        this.failedById.set(failure.aweme_id, failure);
        this.markTargetStatus(failure.aweme_id, "failed", failure.reason);
      }
      this.lastError = result.success && !this.stoppedReason ? null : result.success ? this.lastError : (result.flush_error_message ?? result.failure_summaries[0]?.reason ?? this.lastError);
      if (!result.success) {
        this.phase = "paused";
        this.stoppedReason = "backend_flush_failed";
      }
      await this.persistState();
      return result;
    } catch (error) {
      const backendPost = backendPostFromError(error);
      this.phase = "paused";
      this.lastFlushStatus = "queued";
      this.lastError = error instanceof Error ? error.message : "backend_flush_failed";
      this.flushUrl = typeof backendPost?.url === "string" ? backendPost.url : this.flushUrl;
      this.flushStatusCode = typeof backendPost?.status_code === "number" ? backendPost.status_code : null;
      this.flushErrorCode = typeof backendPost?.error_code === "string" ? (backendPost.error_code as ExtensionBackendErrorCode) : "network_failed";
      this.flushErrorMessage = typeof backendPost?.error_message === "string" ? backendPost.error_message : this.lastError;
      this.flushRetryable = isRetryableFlushError(this.flushErrorCode, this.flushStatusCode);
      this.flushNextAction = flushNextActionForError(this.flushErrorCode, this.flushRetryable, this.pendingById.size);
      this.pendingFlushQueue = markQueueFailed(this.pendingFlushQueue, pendingAwemeIds, { code: this.flushErrorCode, message: this.flushErrorMessage, retryable: this.flushRetryable });
      this.pendingCountAfterFlush = this.pendingById.size;
      this.backendResponseSummary = backendPost?.body && typeof backendPost.body === "object" ? summarizeBackendBody(backendPost.body as Record<string, unknown>) : null;
      this.debug("flush_failed", {
        current_aweme_id: this.currentAwemeId,
        harvested_count: this.harvestedAwemeIds.size,
        pending_count: this.pendingById.size,
        last_error: this.lastError
      });
      await this.persistState();
      return {
        success: false,
        updated_count: 0,
        flushed_aweme_ids: [],
        failed_count: 0,
        failure_summaries: [],
        unchanged_count: 0,
        flush_url: this.flushUrl,
        flush_status_code: this.flushStatusCode,
        flush_error_code: this.flushErrorCode,
        flush_error_message: this.flushErrorMessage,
        flush_retryable: this.flushRetryable,
        backend_response_summary: this.backendResponseSummary
      };
    }
  }

  private debug(event: string, payload: Record<string, unknown>): void {
    console.info(DEBUG_PREFIX, event, payload);
  }
}

function backendPostFromError(error: unknown): Record<string, unknown> | null {
  if (!error || typeof error !== "object" || !("backend_post" in error)) return null;
  const backendPost = (error as { backend_post?: unknown }).backend_post;
  return backendPost && typeof backendPost === "object" ? (backendPost as Record<string, unknown>) : null;
}

function summarizeBackendBody(body: Record<string, unknown>): Record<string, string | number | boolean | null> {
  return {
    ok: typeof body.ok === "boolean" ? body.ok : null,
    error: typeof body.error === "string" ? body.error : null,
    detail: typeof body.detail === "string" ? body.detail : body.detail ? JSON.stringify(body.detail) : null
  };
}

function flushNextActionForError(code: ExtensionBackendErrorCode | null | undefined, retryable: boolean, pendingCount: number): string | null {
  if (pendingCount <= 0) return null;
  if (code === "backend_unreachable") return "Start backend, then click Retry Flush Pending.";
  if (code === "request_timeout" || code === "network_failed" || code === "cors_or_permission_blocked") return "Fix backend/permission issue, then click Retry Flush Pending.";
  if (code === "http_422_schema_error" || !retryable) return "Review payload/schema diagnostics; item is preserved but will not auto-retry.";
  if (code === "http_500_server_error") return "Backend server error; restart backend if needed, then click Retry Flush Pending.";
  return "Click Retry Flush Pending.";
}

function normalizeFlushResult(raw: Record<string, unknown> | null, fallbackIds: string[]): FlushResult {
  const backendPost = raw?.backend_post && typeof raw.backend_post === "object" ? (raw.backend_post as Record<string, unknown>) : null;
  const harvestResponse = raw?.harvest_response && typeof raw.harvest_response === "object" ? (raw.harvest_response as Record<string, unknown>) : raw;
  const flushed_aweme_ids = Array.isArray(raw?.flushed_aweme_ids) ? raw.flushed_aweme_ids.filter((value): value is string => typeof value === "string" && value.trim().length > 0) : fallbackIds;
  const failure_summaries = Array.isArray(harvestResponse?.failure_summaries)
    ? harvestResponse.failure_summaries
        .filter((value): value is { aweme_id?: unknown; reason?: unknown } => Boolean(value && typeof value === "object"))
        .map((value) => ({
          aweme_id: typeof value.aweme_id === "string" ? value.aweme_id : "",
          reason: typeof value.reason === "string" ? value.reason : "batch_flush_failed"
        }))
        .filter((value) => value.aweme_id)
    : [];
  const ok = typeof backendPost?.ok === "boolean" ? backendPost.ok : typeof raw?.ok === "boolean" ? raw.ok : true;
  const responseFlushedIds = Array.isArray(harvestResponse?.flushed_aweme_ids)
    ? harvestResponse.flushed_aweme_ids.filter((value): value is string => typeof value === "string" && value.trim().length > 0)
    : [];
  const summary = harvestResponse
    ? {
        updated_count: typeof harvestResponse.updated_count === "number" ? harvestResponse.updated_count : 0,
        unchanged_count: typeof harvestResponse.unchanged_count === "number" ? harvestResponse.unchanged_count : 0,
        failed_count: typeof harvestResponse.failed_count === "number" ? harvestResponse.failed_count : failure_summaries.length,
        matched_count: typeof harvestResponse.matched_count === "number" ? harvestResponse.matched_count : 0,
        unmatched_count: typeof harvestResponse.unmatched_count === "number" ? harvestResponse.unmatched_count : 0
      }
    : null;
  return {
    success: ok,
    updated_count: typeof harvestResponse?.updated_count === "number" ? harvestResponse.updated_count : 0,
    unchanged_count: typeof harvestResponse?.unchanged_count === "number" ? harvestResponse.unchanged_count : 0,
    failed_count: typeof harvestResponse?.failed_count === "number" ? harvestResponse.failed_count : failure_summaries.length,
    flushed_aweme_ids: responseFlushedIds.length ? responseFlushedIds : ok ? flushed_aweme_ids : [],
    failure_summaries,
    flush_url: typeof backendPost?.url === "string" ? backendPost.url : null,
    flush_status_code: typeof backendPost?.status_code === "number" ? backendPost.status_code : null,
    flush_error_code: typeof backendPost?.error_code === "string" ? (backendPost.error_code as ExtensionBackendErrorCode) : null,
    flush_error_message: typeof backendPost?.error_message === "string" ? backendPost.error_message : typeof raw?.error === "string" ? raw.error : null,
    flush_retryable: typeof backendPost?.retryable === "boolean" ? backendPost.retryable : null,
    backend_response_summary: summary
  };
}

export function normalizeHarvestOptions(options?: FullModalHarvestControlOptions | null): Required<FullModalHarvestControlOptions> {
  return {
    target_count: clampInteger(options?.target_count, DEFAULT_OPTIONS.target_count, 1, 200),
    delay_between_items_ms: clampInteger(options?.delay_between_items_ms, DEFAULT_OPTIONS.delay_between_items_ms, 0, 20_000),
    per_item_timeout_ms: clampInteger(options?.per_item_timeout_ms, DEFAULT_OPTIONS.per_item_timeout_ms, 3_000, 30_000),
    flush_every_n_items: clampInteger(options?.flush_every_n_items, DEFAULT_OPTIONS.flush_every_n_items, 1, 50),
    stop_on_captcha: options?.stop_on_captcha ?? DEFAULT_OPTIONS.stop_on_captcha,
    stop_on_no_next: options?.stop_on_no_next ?? DEFAULT_OPTIONS.stop_on_no_next,
    allow_probe_warnings: options?.allow_probe_warnings ?? DEFAULT_OPTIONS.allow_probe_warnings,
    capture_session_id: options?.capture_session_id?.trim() || null,
    capture_id: options?.capture_id?.trim() || null,
    target_aweme_ids: normalizeTargetAwemeIds(options?.target_aweme_ids ?? []),
    retry_failed_only: options?.retry_failed_only ?? DEFAULT_OPTIONS.retry_failed_only,
    profile_card_evidence_by_aweme_id: options?.profile_card_evidence_by_aweme_id ?? {}
  };
}

export function detectCurrentAwemeId(locationHref: string, document: Document): string | null {
  let detectorError: string | null = null;
  try {
    const url = new URL(locationHref);
    const modalId = url.searchParams.get("modal_id");
    if (modalId?.trim()) return String(modalId).trim();
    const pathMatch = /\/video\/([^/?#]+)/.exec(url.pathname);
    if (pathMatch?.[1]?.trim()) return String(pathMatch[1]).trim();
  } catch (error) {
    detectorError = error instanceof Error ? error.message : "invalid_location_href";
  }
  const activeLink = document.querySelector<HTMLAnchorElement>('a[href*="/video/"][aria-current="true"], a[href*="/video/"][data-active="true"], a[href*="/video/"]');
  const href = activeLink?.href ?? activeLink?.getAttribute?.("href") ?? null;
  if (href) {
    const match = /\/video\/([^/?#]+)/.exec(href);
    if (match?.[1]?.trim()) return String(match[1]).trim();
  }
  void detectorError;
  return null;
}

export function getCurrentAwemeDetectorDiagnostics(location: Location, document: Document): FullModalHarvestDetectorDiagnostics {
  const currentUrl = location.href ?? "";
  let locationSearch = "";
  let modalIdFromUrl: string | null = null;
  let pathVideoId: string | null = null;
  let detectorError: string | null = null;
  try {
    const parsed = new URL(currentUrl);
    locationSearch = parsed.search;
    modalIdFromUrl = parsed.searchParams.get("modal_id");
    const pathMatch = /\/video\/([^/?#]+)/.exec(parsed.pathname);
    pathVideoId = pathMatch?.[1] ? String(pathMatch[1]).trim() : null;
  } catch (error) {
    detectorError = error instanceof Error ? error.message : "invalid_location_href";
  }
  const videos = Array.from(document.querySelectorAll<HTMLVideoElement>("video"));
  const activeVideo = selectActiveModalVideo(document);
  return {
    current_url: currentUrl,
    location_search: locationSearch,
    modal_id_from_url: modalIdFromUrl ? String(modalIdFromUrl).trim() : null,
    path_video_id: pathVideoId,
    video_element_count: videos.length,
    active_video_duration: extractDurationFromVideo(activeVideo),
    detector_error: detectorError
  };
}

export function detectCaptchaOrLoginWall(document: Document, locationHref: string): boolean {
  const title = document.title || "";
  const bodyText = (document.body?.innerText || "").slice(0, 4000);
  const combined = `${locationHref}\n${title}\n${bodyText}`.toLowerCase();
  return CAPTCHA_MARKERS.some((marker) => combined.includes(marker.toLowerCase()));
}

export function extractCurrentModalMetrics(document: Document): RawDomDetailMetrics | null {
  const currentAwemeId = detectCurrentAwemeId(window.location.href, document);
  return extractCurrentModalMetricsForAweme(document, currentAwemeId, null);
}

function isCalibratedPointPassSource(source: RawDomDetailMetrics["source_used"] | FullModalHarvestProbeResult["source_used"] | null | undefined): boolean {
  return source === "calibrated_point_dom" || source === "calibrated_point_ocr" || source === "mixed_calibrated_point";
}

export function probeCurrentModalMetrics(document: Document, location: Location, calibrationOrLegacy?: RightRailCalibration | null | unknown, ..._legacy: unknown[]): FullModalHarvestProbeResult {
  const calibration = calibrationOrLegacy && typeof calibrationOrLegacy === "object" && "version" in (calibrationOrLegacy as Record<string, unknown>)
    ? (calibrationOrLegacy as RightRailCalibration)
    : null;
  const awemeId = detectCurrentAwemeId(location.href, document);
  const viewport = currentViewport(document);
  const metrics = extractCurrentModalMetricsForAweme(document, awemeId, null, null, null, null, calibration ?? null);
  const hasDuration = (metrics?.duration_seconds ?? null) !== null;
  const hasCompleteActionMetrics = metrics != null && ["like_count", "comment_count", "favorite_count", "share_count"].every((key) => metrics[key as keyof RawDomDetailMetrics] != null);
  let blockingReason: string | null = null;
  if (!calibration) blockingReason = "calibration_missing";
  else if (!awemeId) blockingReason = "current_aweme_id_missing";
  else if (!hasDuration) blockingReason = "duration_seconds_missing";
  const probeStatus = blockingReason ? "FAIL" : isCalibratedPointPassSource(metrics?.source_used) && hasCompleteActionMetrics ? "PASS" : "WARN";
  return {
    aweme_id: awemeId,
    calibration_status: calibration ? "calibrated" : "missing",
    calibrated_viewport: calibrationViewport(calibration ?? null),
    current_viewport: viewport,
    source_priority_used: metrics?.source_priority_used ?? "video_element_duration",
    source_used: metrics?.source_used ?? null,
    exact_aweme_runtime_found: false,
    exact_aweme_found: false,
    exact_aweme_source: "none",
    raw_aweme_keys: null,
    fallback_used: null,
    rejected_reason: metrics?.rejected_reason ?? null,
    duration_seconds: metrics?.duration_seconds ?? null,
    duration_text: metrics?.duration_text ?? null,
    like_count: metrics?.like_count ?? null,
    comment_count: metrics?.comment_count ?? null,
    favorite_count: metrics?.favorite_count ?? null,
    share_count: metrics?.share_count ?? null,
    view_count: null,
    posted_text: metrics?.posted_text ?? null,
    posted_at: metrics?.posted_at ?? null,
    point_results: metrics?.point_results ?? null,
    confidence_by_field: metrics?.metric_confidence_by_field ?? null,
    cdp_attached: false,
    cdp_response_count: 0,
    cdp_json_response_count: 0,
    cdp_candidate_aweme_count: 0,
    cdp_exact_match_count: 0,
    runtime_exact_match_count: 0,
    last_matching_aweme_id: null,
    last_matching_response_url: null,
    cdp_last_error: null,
    rejected_metric_reasons: metrics?.rejected_metric_reasons ?? null,
    action_blocks_found: metrics?.action_blocks_found ?? 0,
    modal_action_blocks_found: metrics?.modal_action_blocks_found ?? null,
    action_block_diagnostics: metrics?.action_block_diagnostics ?? null,
    accepted_action_blocks: metrics?.action_block_diagnostics ?? null,
    rejected_candidates_count: metrics?.rejected_candidates_count ?? null,
    rejected_candidate_examples: metrics?.rejected_candidate_examples ?? null,
    rail_region: null,
    numeric_labels_found: null,
    selected_rail_labels: null,
    selected_rail_labels_with_rect: null,
    assigned_metrics: metrics?.assigned_metrics ?? null,
    rejected_examples: metrics?.rejected_examples ?? null,
    extraction_mode: metrics?.extraction_mode ?? null,
    snapshot_text_count: null,
    compact_labels_found: null,
    accessibility_node_count: null,
    accessibility_compact_labels: null,
    ocr_used: metrics?.ocr_used ?? null,
    ocr_raw_text: metrics?.ocr_raw_text ?? null,
    ocr_selected_lines: metrics?.ocr_selected_lines ?? null,
    visual_extractor_diagnostics: null,
    right_rail_region: null,
    selected_snapshot_rail_labels: null,
    combined_text_segment: null,
    combined_count_tokens: null,
    icon_candidates: null,
    selected_action_icons: null,
    icon_anchored_metrics: null,
    rejected_number_examples: null,
    rejected_icon_examples: null,
    rail_x_band: null,
    computed_rail_x_band: null,
    viewport_width: viewport.width,
    viewport_height: viewport.height,
    active_video_rect: metrics?.active_video_rect ?? null,
    modal_candidate_rect: null,
    compact_count_candidates: null,
    compact_text_node_candidates_count: 0,
    compact_count_clusters: null,
    selected_compact_count_cluster: null,
    selected_cluster_texts: null,
    selected_cluster_rects: null,
    action_blocks_missing_reason: metrics?.action_blocks_found ? null : "no_compact_counts",
    extraction_warning: metrics?.extraction_warning ?? null,
    warning_reason: metrics?.warning_reason ?? pointCalibrationWarning(calibration ?? null, viewport),
    probe_status: probeStatus,
    ready_for_full_harvest: probeStatus === "PASS",
    blocking_reason: blockingReason
  };
}

export function shouldRequireProbeOverride(probe: FullModalHarvestProbeResult): boolean {
  void probe;
  return false;
}

export function auditHarvestRecentItemsIntegrity(
  items: FullModalHarvestLastItemSummary[] | null | undefined,
  expectedAwemeId: string
): { ok: true } | { ok: false; observedAwemeId: string | null; reason: string } {
  const list = Array.isArray(items) ? items : [];
  if (!list.length) return { ok: false, observedAwemeId: null, reason: "recent_items_empty" };
  const latest = list[list.length - 1] ?? null;
  if (!latest?.aweme_id) return { ok: false, observedAwemeId: null, reason: "recent_item_aweme_id_missing" };
  if (latest.aweme_id !== expectedAwemeId) {
    return { ok: false, observedAwemeId: latest.aweme_id, reason: "recent_item_aweme_id_mismatch" };
  }
  return { ok: true };
}

export function extractCurrentModalMetricsForAweme(
  document: Document,
  currentAwemeId: string | null,
  cdpAweme?: CdpAwemeEvidence | null,
  cdpStatus?: CdpAwemeStatus | null,
  cdpSnapshot?: CdpDomSnapshotPayload | null,
  visualRightRail?: VisualRightRailPayload | null,
  calibration?: RightRailCalibration | null
): RawDomDetailMetrics | null {
  void currentAwemeId;
  void cdpAweme;
  void cdpStatus;
  void cdpSnapshot;
  void visualRightRail;
  const activeVideo = selectActiveModalVideo(document);
  const durationFromVideo = extractDurationFromVideo(activeVideo);
  const activeVideoRect = activeVideo ? roundRect(activeVideo.getBoundingClientRect()) : null;
  const viewport = currentViewport(document);
  if (calibration) {
    const extraction = readCalibratedPointMetrics(document, calibration);
    const metrics = applyCalibratedPointMetricsToRawDomDetail(
      {
        duration_seconds: durationFromVideo,
        duration_text: typeof durationFromVideo === "number" ? formatDuration(durationFromVideo) : null,
        selected_duration_source: durationFromVideo != null ? "video_element_modal" : null,
        duration_text_source: durationFromVideo != null ? "video_element_format" : null,
        active_video_rect: activeVideoRect,
        viewport_width: viewport.width,
        viewport_height: viewport.height
      },
      extraction
    );
    return metrics;
  }
  return {
    duration_seconds: durationFromVideo,
    duration_text: typeof durationFromVideo === "number" ? formatDuration(durationFromVideo) : null,
    selected_duration_source: durationFromVideo != null ? "video_element_modal" : null,
    duration_text_source: durationFromVideo != null ? "video_element_format" : null,
    source_priority_used: "video_element_duration",
    source_used: null,
    rejected_reason: "calibration_missing",
    action_blocks_found: 0,
    modal_action_blocks_found: 0,
    active_video_rect: activeVideoRect,
    viewport_width: viewport.width,
    viewport_height: viewport.height,
    extraction_warning: "calibration_missing",
    warning_reason: "calibration_missing",
    extraction_source: "dom_detail_modal",
    confidence: "high"
  };
  /*
  const visualSelection = extractVisualRightRailMetrics(visualRightRail ?? null);
  if (visualSelection.source) {
    const selected = visualSelection.labels;
    const source = visualSelection.source;
    return {
      duration_seconds: durationFromVideo,
      duration_text: typeof durationFromVideo === "number" ? formatDuration(durationFromVideo) : null,
      like_count: selected[0]?.value ?? null,
      like_count_text: selected[0]?.text ?? null,
      like_count_source: source,
      comment_count: selected[1]?.value ?? null,
      comment_count_text: selected[1]?.text ?? null,
      comment_count_source: source,
      favorite_count: selected[2]?.value ?? null,
      favorite_count_text: selected[2]?.text ?? null,
      favorite_count_source: source,
      share_count: selected[3]?.value ?? null,
      share_count_text: selected[3]?.text ?? null,
      share_count_source: source,
      selected_duration_source: durationFromVideo != null ? "video_element_modal" : null,
      duration_text_source: durationFromVideo != null ? "video_element_format" : null,
      source_priority_used: source,
      source_used: source,
      fallback_used: null,
      exact_aweme_runtime_found: Boolean(cdpAweme),
      exact_aweme_found: Boolean(cdpAweme),
      exact_aweme_source: cdpAweme?.source_used === "cdp_network_aweme" ? "cdp_network" : cdpAweme?.source_used === "cdp_runtime_aweme" ? "cdp_runtime" : "none",
      raw_aweme_keys: cdpAweme?.raw_aweme_keys ?? null,
      cdp_attached: cdpStatus?.attached ?? false,
      cdp_response_count: cdpStatus?.response_count ?? 0,
      cdp_json_response_count: cdpStatus?.json_response_count ?? 0,
      cdp_candidate_aweme_count: cdpStatus?.candidate_aweme_count ?? 0,
      cdp_exact_match_count: cdpStatus?.exact_match_count ?? 0,
      runtime_exact_match_count: cdpStatus?.runtime_exact_match_count ?? 0,
      last_matching_aweme_id: cdpAweme?.aweme_id ?? cdpStatus?.last_matching_aweme_id ?? null,
      last_matching_response_url: cdpAweme?.response_url ?? cdpStatus?.last_matching_response_url ?? null,
      cdp_last_error: cdpStatus?.last_error ?? null,
      action_blocks_found: 0,
      modal_action_blocks_found: 0,
      rail_region: visualSelection.diagnostics.crop_region,
      right_rail_region: visualSelection.diagnostics.crop_region,
      selected_rail_labels: selected.map((label: VisualRightRailLabel) => label.text),
      assigned_metrics: selected.map((label: VisualRightRailLabel, index: number) => ({ metric: (["like", "comment", "favorite", "share"] as ActionKind[])[index] ?? "like", visible_text: label.text, value: label.value, rect: label.rect ?? null, source })),
      extraction_mode: source,
      compact_labels_found: visualSelection.diagnostics.accessibility_compact_labels.length,
      viewport_width: visualRightRail?.accessibility_tree?.viewport_width ?? visualRightRail?.screenshot_ocr?.viewport_width ?? null,
      viewport_height: visualRightRail?.accessibility_tree?.viewport_height ?? visualRightRail?.screenshot_ocr?.viewport_height ?? null,
      active_video_rect: activeVideoRect,
      warning_reason: visualSelection.warning_reason,
      accessibility_node_count: visualSelection.diagnostics.accessibility_node_count,
      accessibility_compact_labels: visualSelection.diagnostics.accessibility_compact_labels,
      ocr_used: visualSelection.diagnostics.ocr_used,
      ocr_raw_text: visualSelection.diagnostics.ocr_raw_text,
      ocr_selected_lines: visualSelection.diagnostics.ocr_selected_lines,
      visual_extractor_diagnostics: visualSelection.diagnostics,
      metric_confidence_by_field: { duration_seconds: durationFromVideo != null ? "high" : "none", like_count: "high", comment_count: "high", favorite_count: "high", share_count: "high" },
      extraction_source: source,
      confidence: "high"
    };
  }
  const snapshotResult = extractCdpDomSnapshotRightRail(cdpSnapshot, activeVideoRect);
  if (snapshotResult.result) {
    const selected = snapshotResult.result.selected_rail_labels;
    const metrics: RawDomDetailMetrics = {
      duration_seconds: durationFromVideo,
      duration_text: typeof durationFromVideo === "number" ? formatDuration(durationFromVideo) : null,
      like_count: snapshotResult.result.like_count,
      like_count_text: selected[0]?.text ?? null,
      like_count_source: "cdp_dom_snapshot_right_rail",
      comment_count: snapshotResult.result.comment_count,
      comment_count_text: selected[1]?.text ?? null,
      comment_count_source: "cdp_dom_snapshot_right_rail",
      favorite_count: snapshotResult.result.favorite_count,
      favorite_count_text: selected[2]?.text ?? null,
      favorite_count_source: "cdp_dom_snapshot_right_rail",
      share_count: snapshotResult.result.share_count,
      share_count_text: selected[3]?.text ?? null,
      share_count_source: "cdp_dom_snapshot_right_rail",
      selected_duration_source: durationFromVideo != null ? "video_element_modal" : null,
      duration_text_source: durationFromVideo != null ? "video_element_format" : null,
      source_priority_used: "cdp_dom_snapshot_right_rail",
      source_used: "cdp_dom_snapshot_right_rail",
      fallback_used: null,
      exact_aweme_runtime_found: Boolean(cdpAweme),
      exact_aweme_found: Boolean(cdpAweme),
      exact_aweme_source: cdpAweme?.source_used === "cdp_network_aweme" ? "cdp_network" : cdpAweme?.source_used === "cdp_runtime_aweme" ? "cdp_runtime" : "none",
      raw_aweme_keys: cdpAweme?.raw_aweme_keys ?? null,
      rejected_reason: null,
      cdp_attached: cdpStatus?.attached ?? false,
      cdp_response_count: cdpStatus?.response_count ?? 0,
      cdp_json_response_count: cdpStatus?.json_response_count ?? 0,
      cdp_candidate_aweme_count: cdpStatus?.candidate_aweme_count ?? 0,
      cdp_exact_match_count: cdpStatus?.exact_match_count ?? 0,
      runtime_exact_match_count: cdpStatus?.runtime_exact_match_count ?? 0,
      last_matching_aweme_id: cdpAweme?.aweme_id ?? cdpStatus?.last_matching_aweme_id ?? null,
      last_matching_response_url: cdpAweme?.response_url ?? cdpStatus?.last_matching_response_url ?? null,
      cdp_last_error: cdpStatus?.last_error ?? null,
      action_blocks_found: 0,
      modal_action_blocks_found: 0,
      rail_region: snapshotResult.result.right_rail_region,
      right_rail_region: snapshotResult.result.right_rail_region,
      numeric_labels_found: snapshotResult.result.selected_rail_labels.map(snapshotLabelToNumericDiagnostic),
      selected_rail_labels: snapshotResult.result.selected_rail_labels.map((label: CdpDomSnapshotRailLabel) => label.text),
      selected_snapshot_rail_labels: snapshotResult.result.selected_rail_labels,
      assigned_metrics: snapshotResult.result.selected_rail_labels.map((label: CdpDomSnapshotRailLabel) => ({ metric: label.assigned_metric ?? "like", visible_text: label.text, value: label.value, rect: label.rect, source: "cdp_dom_snapshot_right_rail" as const })),
      rejected_examples: snapshotResult.result.rejected_examples,
      extraction_mode: "cdp_dom_snapshot_right_rail",
      snapshot_text_count: snapshotResult.result.snapshot_text_count,
      compact_labels_found: snapshotResult.result.compact_labels_found,
      viewport_width: snapshotResult.result.viewport_width,
      viewport_height: snapshotResult.result.viewport_height,
      active_video_rect: activeVideoRect,
      action_blocks_missing_reason: null,
      warning_reason: snapshotResult.result.warning_reason,
      metric_confidence_by_field: { duration_seconds: durationFromVideo != null ? "high" : "none", like_count: "high", comment_count: "high", favorite_count: "high", share_count: "high" },
      extraction_source: "cdp_dom_snapshot_right_rail",
      confidence: "high"
    };
    return metrics;
  }
  if (visualRightRail !== undefined || cdpSnapshot !== undefined || cdpStatus) {
    const region = cdpSnapshot ? computeSnapshotRightRailRegion(cdpSnapshot.viewport_width, cdpSnapshot.viewport_height, activeVideoRect) : null;
    return {
      duration_seconds: durationFromVideo,
      duration_text: durationFromVideo != null ? formatDuration(durationFromVideo) : null,
      selected_duration_source: durationFromVideo != null ? "video_element_modal" : null,
      source_priority_used: "missing",
      source_used: null,
      fallback_used: null,
      cdp_attached: cdpStatus?.attached ?? false,
      cdp_response_count: cdpStatus?.response_count ?? 0,
      cdp_json_response_count: cdpStatus?.json_response_count ?? 0,
      cdp_candidate_aweme_count: cdpStatus?.candidate_aweme_count ?? 0,
      cdp_exact_match_count: cdpStatus?.exact_match_count ?? 0,
      runtime_exact_match_count: cdpStatus?.runtime_exact_match_count ?? 0,
      cdp_last_error: cdpStatus?.last_error ?? null,
      action_blocks_found: 0,
      modal_action_blocks_found: 0,
      rail_region: region,
      right_rail_region: region,
      rejected_examples: [],
      extraction_mode: null,
      snapshot_text_count: cdpSnapshot?.text_entries.length ?? 0,
      compact_labels_found: 0,
      viewport_width: cdpSnapshot?.viewport_width ?? null,
      viewport_height: cdpSnapshot?.viewport_height ?? null,
      active_video_rect: activeVideoRect,
      accessibility_node_count: visualSelection.diagnostics.accessibility_node_count,
      accessibility_compact_labels: visualSelection.diagnostics.accessibility_compact_labels,
      ocr_used: visualSelection.diagnostics.ocr_used,
      ocr_raw_text: visualSelection.diagnostics.ocr_raw_text,
      ocr_selected_lines: visualSelection.diagnostics.ocr_selected_lines,
      visual_extractor_diagnostics: visualSelection.diagnostics,
      warning_reason: visualSelection.warning_reason ?? snapshotResult.warning_reason ?? "visual_right_rail_missing",
      extraction_source: "dom_detail_modal",
      confidence: "high"
    };
  }
  const runtime = extractExactAwemeRuntimeState(document, currentAwemeId);
  const runtimeMetrics = cdpAweme ? {
    duration_seconds: cdpAweme.duration_seconds,
    duration_text: cdpAweme.duration_text,
    duration_raw: cdpAweme.duration_seconds,
    duration_validation_result: cdpAweme.duration_seconds != null ? "accepted_exact_aweme" as const : "rejected_missing" as const,
    duration_candidate_list: [{
      source: cdpAweme.source_used,
      raw_value: cdpAweme.duration_seconds,
      normalized_seconds: cdpAweme.duration_seconds,
      accepted: cdpAweme.duration_seconds != null,
      reason: cdpAweme.duration_seconds != null ? "selected_exact_aweme" : "missing"
    }],
    view_count: cdpAweme.view_count,
    like_count: cdpAweme.like_count,
    comment_count: cdpAweme.comment_count,
    favorite_count: cdpAweme.favorite_count,
    share_count: cdpAweme.share_count,
    posted_text: cdpAweme.posted_text,
    posted_at: cdpAweme.posted_at,
    posted_source: cdpAweme.posted_at ? "aweme_create_time" : "none",
    posted_parse_confidence: cdpAweme.posted_at ? "parsed" : "none"
  } : runtime ? mapRuntimeAwemeMetrics(runtime.aweme) : null;
  const timeline = findTimelineDurationText(document);
  const timelineDurationSeconds = parseTimelineDurationSeconds(timeline?.duration_text ?? null);
  const metricConfidenceByField: Record<string, string> = {};
  const rejectedMetricReasons: Record<string, string> = {};
  const assignedMetricNodeIds: string[] = [];
  let durationSeconds: number | null = null;
  let durationText: string | null = null;
  let selectedDurationSource: string | null = null;
  let durationTextSource: string | null = null;
  let durationTextConflict: string | null = null;
  let durationValidationResult: string = "rejected_missing";
  const durationCandidateList: Array<{ source: string; raw_value: number | null; normalized_seconds: number | null; accepted: boolean; reason: string }> = [];
  durationCandidateList.push({
    source: "video_element.duration",
    raw_value: durationFromVideo,
    normalized_seconds: typeof durationFromVideo === "number" ? durationFromVideo : null,
    accepted: false,
    reason: typeof durationFromVideo === "number" ? "fallback_not_allowed_when_aweme_missing" : "missing"
  });
  durationCandidateList.push({
    source: "timeline.duration_text",
    raw_value: timelineDurationSeconds,
    normalized_seconds: typeof timelineDurationSeconds === "number" ? timelineDurationSeconds : null,
    accepted: false,
    reason: typeof timelineDurationSeconds === "number" ? "fallback_not_allowed_when_aweme_missing" : "missing"
  });
  if (runtimeMetrics?.duration_seconds != null) {
    durationSeconds = runtimeMetrics.duration_seconds;
    selectedDurationSource = cdpAweme?.source_used ?? runtime?.priority ?? "exact_aweme_runtime_object";
    metricConfidenceByField.duration_seconds = "exact_aweme_runtime";
    durationText = runtimeMetrics.duration_text;
    durationTextSource = cdpAweme?.source_used ?? runtime?.priority ?? "exact_aweme_runtime_object";
    if (durationText) metricConfidenceByField.duration_text = "exact_aweme_runtime";
    durationTextConflict = null;
    durationValidationResult = runtimeMetrics.duration_validation_result;
    durationCandidateList.push(...runtimeMetrics.duration_candidate_list);
  } else {
    durationValidationResult = "rejected_missing_exact_aweme_duration";
    rejectedMetricReasons.duration_seconds = currentAwemeId ? "exact_aweme_duration_missing" : "current_aweme_id_missing";
    if (typeof timelineDurationSeconds === "number" && timeline?.duration_text && typeof durationFromVideo === "number" && Math.abs(timelineDurationSeconds - durationFromVideo) > 3) {
      durationTextConflict = timeline.duration_text;
      rejectedMetricReasons.duration_text = `timeline_conflict:${timeline.duration_text}`;
    }
  }
  const actionDetection = detectActionBlockCandidates(document);
  const actionBlocks = actionDetection.accepted;
  const claimedBlocks = new Set<string>();
  const like = selectActionMetric(actionBlocks, "like", claimedBlocks);
  const comment = selectActionMetric(actionBlocks, "comment", claimedBlocks);
  const favorite = selectActionMetric(actionBlocks, "favorite", claimedBlocks);
  const share = selectActionMetric(actionBlocks, "share", claimedBlocks);
  let resolvedLike = like;
  if (resolvedLike.value === null && currentAwemeId) {
    const profileFallback = findProfileCardLikeMetric(document, currentAwemeId);
    if (profileFallback.value !== null) {
      resolvedLike = profileFallback;
    } else if (profileFallback.rejected_reason && !rejectedMetricReasons.like_count) {
      rejectedMetricReasons.like_count = profileFallback.rejected_reason;
    }
  }
  for (const selection of [resolvedLike, comment, favorite, share]) {
    if (selection.node_descriptor) assignedMetricNodeIds.push(selection.node_descriptor);
  }
  const combinedModalText = runtimeMetrics ? null : extractCombinedModalActionText(document);
  const finalLike = runtimeMetrics?.like_count ?? combinedModalText?.like_count ?? resolvedLike.value;
  const finalComment = runtimeMetrics?.comment_count ?? combinedModalText?.comment_count ?? comment.value;
  const finalFavorite = runtimeMetrics?.favorite_count ?? combinedModalText?.favorite_count ?? favorite.value;
  const finalShare = runtimeMetrics?.share_count ?? combinedModalText?.share_count ?? share.value;
  const finalPostedText = runtimeMetrics?.posted_text ?? findPostedText(document);
  const fallbackUsed = runtime
    ? [
        runtimeMetrics?.like_count == null && combinedModalText == null && resolvedLike.value != null,
        runtimeMetrics?.comment_count == null && combinedModalText == null && comment.value != null,
        runtimeMetrics?.favorite_count == null && combinedModalText == null && favorite.value != null,
        runtimeMetrics?.share_count == null && combinedModalText == null && share.value != null
      ].some(Boolean)
      ? "visible_right_rail_fallback"
      : null
    : combinedModalText
      ? "combined_modal_text_fallback"
      : [resolvedLike.value, comment.value, favorite.value, share.value].some((value) => value != null)
        ? "visible_right_rail_fallback"
        : null;
  if (finalLike !== null) metricConfidenceByField.like_count = runtimeMetrics?.like_count != null ? "exact_aweme_runtime" : combinedModalText ? "high" : resolvedLike.confidence;
  else if (resolvedLike.rejected_reason) rejectedMetricReasons.like_count = runtime ? "runtime_like_count_missing" : resolvedLike.rejected_reason;
  if (finalComment !== null) metricConfidenceByField.comment_count = runtimeMetrics?.comment_count != null ? "exact_aweme_runtime" : combinedModalText ? "high" : comment.confidence;
  else if (comment.rejected_reason) rejectedMetricReasons.comment_count = runtime ? "runtime_comment_count_missing" : comment.rejected_reason;
  if (finalFavorite !== null) metricConfidenceByField.favorite_count = runtimeMetrics?.favorite_count != null ? "exact_aweme_runtime" : combinedModalText ? "high" : favorite.confidence;
  else if (favorite.rejected_reason) rejectedMetricReasons.favorite_count = runtime ? "runtime_favorite_count_missing" : favorite.rejected_reason;
  if (finalShare !== null) metricConfidenceByField.share_count = runtimeMetrics?.share_count != null ? "exact_aweme_runtime" : combinedModalText ? "high" : share.confidence;
  else if (share.rejected_reason) rejectedMetricReasons.share_count = runtime ? "runtime_share_count_missing" : share.rejected_reason;
  const actionBlockDiagnostics = buildActionBlockDiagnostics(actionBlocks, {
    like: resolvedLike.node_descriptor ?? null,
    comment: comment.node_descriptor ?? null,
    favorite: favorite.node_descriptor ?? null,
    share: share.node_descriptor ?? null
  });
  const postedText = finalPostedText;
  const extractionWarning = summarizeExtractionWarning(rejectedMetricReasons);
  const hasAny = [durationSeconds, finalLike, finalComment, finalFavorite, finalShare, postedText, runtimeMetrics?.posted_at].some((value) => value !== null && value !== undefined);
  if (!hasAny) return null;
  return {
    duration_seconds: typeof durationSeconds === "number" ? durationSeconds : null,
    duration_text: durationText,
    duration_raw: runtimeMetrics?.duration_raw ?? null,
    duration_validation_result: durationValidationResult,
    duration_candidate_list: durationCandidateList,
    duration_text_conflict: durationTextConflict,
    like_count: finalLike,
    like_count_text: runtimeMetrics?.like_count != null ? String(runtimeMetrics.like_count) : combinedModalText ? combinedModalText.combined_count_tokens[0] ?? null : resolvedLike.text,
    like_count_source: finalLike !== null ? (runtimeMetrics?.like_count != null ? runtime?.priority ?? "exact_aweme_runtime_object" : combinedModalText ? "combined_modal_text_fallback" : (resolvedLike.source ?? "dom_detail_modal")) : null,
    comment_count: finalComment,
    comment_count_text: runtimeMetrics?.comment_count != null ? String(runtimeMetrics.comment_count) : combinedModalText ? combinedModalText.combined_count_tokens[1] ?? null : comment.text,
    comment_count_source: finalComment !== null ? (runtimeMetrics?.comment_count != null ? runtime?.priority ?? "exact_aweme_runtime_object" : combinedModalText ? "combined_modal_text_fallback" : "dom_detail_modal") : null,
    favorite_count: finalFavorite,
    favorite_count_text: runtimeMetrics?.favorite_count != null ? String(runtimeMetrics.favorite_count) : combinedModalText ? combinedModalText.combined_count_tokens[2] ?? null : favorite.text,
    favorite_count_source: finalFavorite !== null ? (runtimeMetrics?.favorite_count != null ? runtime?.priority ?? "exact_aweme_runtime_object" : combinedModalText ? "combined_modal_text_fallback" : "dom_detail_modal") : null,
    share_count: finalShare,
    share_count_text: runtimeMetrics?.share_count != null ? String(runtimeMetrics.share_count) : combinedModalText ? combinedModalText.combined_count_tokens[3] ?? null : share.text,
    share_count_source: finalShare !== null ? (runtimeMetrics?.share_count != null ? runtime?.priority ?? "exact_aweme_runtime_object" : combinedModalText ? "combined_modal_text_fallback" : "dom_detail_modal") : null,
    view_count: runtimeMetrics?.view_count ?? null,
    view_count_source: runtimeMetrics?.view_count != null ? runtime?.priority ?? null : null,
    posted_text: postedText,
    posted_at: runtimeMetrics?.posted_at ?? null,
    posted_source: runtimeMetrics?.posted_source ?? (postedText ? "modal_author_row" : null),
    posted_parse_confidence: runtimeMetrics?.posted_parse_confidence ?? (runtimeMetrics?.posted_at ? "parsed" : postedText ? "raw_only" : "none"),
    selected_duration_source: selectedDurationSource,
    duration_text_source: durationTextSource,
    action_blocks_found: actionBlocks.length,
    modal_action_blocks_found: actionBlocks.length,
    like_block_text: resolvedLike.block_text,
    comment_block_text: comment.block_text,
    favorite_block_text: favorite.block_text,
    share_block_text: share.block_text,
    profile_card_like_text: resolvedLike.source === "dom_profile_card_fallback" ? resolvedLike.text : null,
    action_block_diagnostics: actionBlockDiagnostics.length ? actionBlockDiagnostics : null,
    rail_region: actionDetection.rail_region,
    numeric_labels_found: actionDetection.numeric_labels_found,
    selected_rail_labels: actionDetection.selected_rail_labels,
    selected_rail_labels_with_rect: actionDetection.selected_rail_labels_with_rect,
    assigned_metrics: actionDetection.assigned_metrics,
    rejected_examples: actionDetection.rejected_examples,
    extraction_mode: combinedModalText ? "combined_modal_text_fallback" : actionDetection.extraction_mode,
    combined_text_segment: combinedModalText?.combined_text_segment ?? null,
    combined_count_tokens: combinedModalText?.combined_count_tokens ?? null,
    icon_candidates: actionDetection.icon_candidates,
    selected_action_icons: actionDetection.selected_action_icons,
    icon_anchored_metrics: actionDetection.icon_anchored_metrics,
    rejected_number_examples: actionDetection.rejected_number_examples,
    rejected_icon_examples: actionDetection.rejected_icon_examples,
    rejected_candidates_count: actionDetection.rejected.length,
    rejected_candidate_examples: actionDetection.rejected.slice(0, 5),
    rail_x_band: actionDetection.rail_x_band,
    computed_rail_x_band: actionDetection.computed_rail_x_band,
    viewport_width: actionDetection.viewport_width,
    viewport_height: actionDetection.viewport_height,
    active_video_rect: actionDetection.active_video_rect,
    modal_candidate_rect: actionDetection.modal_candidate_rect,
    compact_count_candidates: actionDetection.compact_count_candidates,
    compact_text_node_candidates_count: actionDetection.compact_text_node_candidates_count,
    compact_count_clusters: actionDetection.compact_count_clusters,
    selected_compact_count_cluster: actionDetection.selected_compact_count_cluster,
    selected_cluster_texts: actionDetection.selected_cluster_texts,
    selected_cluster_rects: actionDetection.selected_cluster_rects,
    action_blocks_missing_reason: actionDetection.action_blocks_missing_reason,
    warning_reason: actionDetection.warning_reason,
    source_priority_used: cdpAweme?.source_used ?? runtime?.priority ?? fallbackUsed ?? "missing",
    source_used: cdpAweme?.source_used ?? runtime?.source_used ?? (fallbackUsed === "visible_right_rail_fallback" ? "visible_right_rail_fallback" : fallbackUsed),
    exact_aweme_runtime_found: Boolean(runtime || cdpAweme),
    exact_aweme_found: Boolean(runtime || cdpAweme),
    exact_aweme_source: cdpAweme?.source_used === "cdp_network_aweme" ? "cdp_network" : cdpAweme?.source_used === "cdp_runtime_aweme" ? "cdp_runtime" : runtime?.exact_aweme_source ?? "none",
    raw_aweme_keys: cdpAweme?.raw_aweme_keys ?? runtime?.raw_aweme_keys ?? null,
    fallback_used: fallbackUsed,
    rejected_reason: runtime || cdpAweme ? null : currentAwemeId ? "exact_runtime_aweme_not_found" : "current_aweme_id_missing",
    cdp_attached: false,
    cdp_response_count: 0,
    cdp_json_response_count: 0,
    cdp_candidate_aweme_count: 0,
    cdp_exact_match_count: 0,
    runtime_exact_match_count: 0,
    last_matching_aweme_id: null,
    last_matching_response_url: null,
    cdp_last_error: null,
    assigned_metric_node_ids: assignedMetricNodeIds.length ? assignedMetricNodeIds : null,
    metric_confidence_by_field: Object.keys(metricConfidenceByField).length ? metricConfidenceByField : null,
    rejected_metric_reasons: Object.keys(rejectedMetricReasons).length ? rejectedMetricReasons : null,
    extraction_warning: extractionWarning,
    extraction_source: cdpAweme?.source_used ?? runtime?.priority ?? combinedModalText?.extraction_source ?? "dom_detail_modal",
    confidence: "high"
  };
*/
}

export async function waitForCurrentModalMetrics(
  document: Document,
  location: Location,
  expectedAwemeId: string,
  timeoutMs: number,
  calibration?: RightRailCalibration | null
): Promise<FullModalHarvestItemPayload | null> {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (detectCaptchaOrLoginWall(document, location.href)) return null;
    const currentAwemeId = detectCurrentAwemeId(location.href, document);
    if (currentAwemeId === expectedAwemeId) {
      const metrics = extractCurrentModalMetricsForAweme(document, expectedAwemeId, null, null, null, null, calibration ?? null);
      if ((metrics?.source_used === "calibrated_point_dom" || metrics?.source_used === "calibrated_point_ocr" || metrics?.source_used === "mixed_calibrated_point") && metrics.duration_seconds != null && metrics.like_count != null && metrics.comment_count != null && metrics.favorite_count != null && metrics.share_count != null) {
        return {
          aweme_id: expectedAwemeId,
          target_aweme_id: expectedAwemeId,
          source_video_external_id: expectedAwemeId,
          source_url: location.href,
          page_url: location.href,
          modal_id: detectCurrentAwemeId(location.href, document),
          raw_dom_detail_metrics: { ...metrics, aweme_id: expectedAwemeId, target_aweme_id: expectedAwemeId },
          raw_detail_aweme: null,
          raw_evidence_summary: buildDomDetailEvidenceSummary(metrics)
        };
      }
    }
    await wait(100);
  }
  return null;
}

export async function navigateToNextModalVideo(document: Document, previousAwemeId: string, timeoutMs: number, delayMs: number, retryCount = 1): Promise<NavigationResult> {
  let attempts = 0;
  while (attempts <= retryCount) {
    const clicked = clickNextControl(document);
    if (!clicked) triggerNextKeyboardNavigation(document);
    const changed = await waitForAwemeIdChange(() => detectCurrentAwemeId(window.location.href, document), previousAwemeId, timeoutMs);
    if (changed) {
      const navigationSettleMs = Math.min(delayMs, 150);
      if (navigationSettleMs > 0) await wait(navigationSettleMs);
      return { moved: true, reason: "aweme_changed" };
    }
    attempts += 1;
    if (attempts > retryCount) return { moved: false, reason: clicked ? "navigation_timeout" : "no_next_control" };
  }
  return { moved: false, reason: "navigation_timeout" };
}

export async function waitForAwemeIdChange(getAwemeId: () => string | null, previousAwemeId: string, timeoutMs: number): Promise<boolean> {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const current = getAwemeId();
    if (current && current !== previousAwemeId) return true;
    await wait(250);
  }
  return false;
}

export async function navigateNextModalAutomatically(
  document: Document,
  location: Location,
  previousAwemeId: string,
  timeoutMs = 12_000
): Promise<NavigationResult> {
  const attempts: Array<() => void> = [
    () => {
      clickNextControl(document);
    },
    () => {
      focusPageForNavigation(document);
      dispatchKeyboardNavigation(document, "ArrowDown");
    },
    () => {
      dispatchKeyboardNavigation(document, "PageDown");
    },
    () => {
      dispatchWheelNavigation(document);
    },
    () => {
      focusPageForNavigation(document);
      dispatchKeyboardNavigation(document, "ArrowDown");
    }
  ];
  const deadline = Date.now() + Math.max(1, timeoutMs);
  let retries = 0;

  for (const attempt of attempts) {
    retries += 1;
    attempt();
    const remainingAttempts = attempts.length - retries;
    const remainingTime = Math.max(1, deadline - Date.now());
    const waitWindowMs = Math.max(1, Math.min(3_000, Math.floor(remainingTime / Math.max(1, remainingAttempts + 1))));
    const changed = await waitForModalIdChange(() => detectCurrentAwemeId(location.href, document), previousAwemeId, waitWindowMs);
    if (changed) return { moved: true, reason: "aweme_changed", retries, last_result: "modal_changed", failed_stage: null };
  }

  const changed = await waitForModalIdChange(() => detectCurrentAwemeId(location.href, document), previousAwemeId, Math.max(1, deadline - Date.now()));
  if (changed) return { moved: true, reason: "aweme_changed", retries, last_result: "modal_changed", failed_stage: null };

  return { moved: false, reason: "navigation_timeout", retries, last_result: "timeout", failed_stage: "modal_id_change_timeout" };
}

export async function navigateDirectlyToTargetModal(
  location: Location,
  document: Document,
  previousAwemeId: string,
  targetAwemeId: string,
  timeoutMs = 12_000
): Promise<NavigationResult> {
  routeLocationToModalId(location, targetAwemeId);
  const changed = await waitForModalIdMatch(() => detectCurrentAwemeId(location.href, document), targetAwemeId, Math.max(1, timeoutMs));
  return changed
    ? { moved: true, reason: "aweme_changed", retries: 1, last_result: "modal_changed", failed_stage: null, target_aweme_id: targetAwemeId }
    : { moved: false, reason: "navigation_timeout", retries: 1, last_result: "timeout", failed_stage: "modal_id_change_timeout", target_aweme_id: targetAwemeId };
}

export function routeLocationToModalId(location: Location, targetAwemeId: string): void {
  const nextUrl = new URL(location.href);
  nextUrl.searchParams.set("modal_id", targetAwemeId);
  try {
    window.history?.pushState?.(null, "", nextUrl.toString());
  } catch {
    // Best effort: tests and browser pages may expose immutable history.
  }
  try {
    Object.assign(location, { href: nextUrl.toString(), search: nextUrl.search });
  } catch {
    location.href = nextUrl.toString();
  }
}

export async function waitForModalIdMatch(getAwemeId: () => string | null, targetAwemeId: string, timeoutMs: number): Promise<boolean> {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const current = getAwemeId();
    if (current === targetAwemeId) return true;
    await wait(300);
  }
  return false;
}

export async function navigateNextByCalibratedPoint(
  document: Document,
  location: Location,
  _calibration: RightRailCalibration | null | undefined,
  previousAwemeId: string,
  timeoutMs = 12_000
): Promise<NavigationResult> {
  return navigateNextModalAutomatically(document, location, previousAwemeId, timeoutMs);
}

export const navigateNextVideoByCalibratedPoint = navigateNextByCalibratedPoint;

export async function waitForModalIdChange(getAwemeId: () => string | null, previousAwemeId: string, timeoutMs: number): Promise<boolean> {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const current = getAwemeId();
    if (current && current !== previousAwemeId) return true;
    await wait(300);
  }
  return false;
}

export function clickCalibratedNextPoint(document: Document, calibration: RightRailCalibration): { x: number; y: number; clicked: boolean } {
  const point = calibration.points.next_video_button;
  if (!point) return { x: 0, y: 0, clicked: false };
  const viewport = currentViewport(document);
  const x = Math.max(0, Math.min(Math.max(0, viewport.width - 1), Math.round(point.x_ratio * viewport.width)));
  const y = Math.max(0, Math.min(Math.max(0, viewport.height - 1), Math.round(point.y_ratio * viewport.height)));
  const target = document.elementFromPoint?.(x, y) ?? document.body ?? document.documentElement;
  if (!target) return { x, y, clicked: false };
  for (const type of ["pointerdown", "mousedown", "pointerup", "mouseup", "click"] as const) {
    const event = (type === "pointerdown" || type === "pointerup") && typeof PointerEvent !== "undefined" ? new PointerEvent(type, mouseEventInit(x, y)) : new MouseEvent(type, mouseEventInit(x, y));
    target.dispatchEvent(event);
  }
  return { x, y, clicked: true };
}

function mouseEventInit(x: number, y: number): MouseEventInit {
  return { bubbles: true, cancelable: true, composed: true, clientX: x, clientY: y, button: 0, buttons: 1, view: window };
}

function normalizeTargetAwemeIds(values: readonly string[]): string[] {
  const output: string[] = [];
  for (const value of values) {
    const awemeId = typeof value === "string" ? value.trim() : "";
    if (awemeId && !output.includes(awemeId)) output.push(awemeId);
  }
  return output.slice(0, 200);
}

function focusPageForNavigation(document: Document): void {
  const targets = navigationEventTargets(document);
  for (const target of targets) {
    if ("focus" in target && typeof target.focus === "function") {
      target.focus();
      return;
    }
  }
}

function dispatchKeyboardNavigation(document: Document, key = "ArrowDown"): void {
  const eventInit = { key, code: key, bubbles: true, cancelable: true, composed: true };
  for (const target of navigationEventTargets(document)) {
    target.dispatchEvent(new KeyboardEvent("keydown", eventInit));
  }
  for (const target of navigationEventTargets(document)) {
    target.dispatchEvent(new KeyboardEvent("keyup", eventInit));
  }
}

function dispatchWheelNavigation(document: Document): void {
  for (const target of navigationEventTargets(document)) {
    target.dispatchEvent(new WheelEvent("wheel", { deltaY: 900, bubbles: true, cancelable: true, composed: true }));
  }
}

function navigationEventTargets(document: Document): EventTarget[] {
  const targets: EventTarget[] = [];
  const add = (target: EventTarget | null | undefined): void => {
    if (target && !targets.includes(target)) targets.push(target);
  };
  add(window);
  add(document);
  add(document.activeElement);
  add(selectActiveModalVideo(document));
  add(document.body);
  add(document.documentElement);
  return targets;
}

export function buildDomDetailEvidenceSummary(metrics: RawDomDetailMetrics): RawEvidenceSummary {
  const diagnosticKeys = new Set([
    "selected_duration_source",
    "duration_text_source",
    "duration_text_conflict",
    "action_blocks_found",
    "modal_action_blocks_found",
    "like_block_text",
    "comment_block_text",
    "favorite_block_text",
    "share_block_text",
    "profile_card_like_text",
    "action_block_diagnostics",
    "rejected_candidates_count",
    "rejected_candidate_examples",
    "rail_region",
    "numeric_labels_found",
    "selected_rail_labels",
    "selected_rail_labels_with_rect",
    "assigned_metrics",
    "rejected_examples",
    "extraction_mode",
    "icon_candidates",
    "selected_action_icons",
    "icon_anchored_metrics",
    "rejected_number_examples",
    "rejected_icon_examples",
    "like_count_source",
    "comment_count_source",
    "share_count_source",
    "assigned_metric_node_ids",
    "metric_confidence_by_field",
    "rejected_metric_reasons",
    "extraction_warning",
    "compact_text_node_candidates_count",
    "compact_count_candidates",
    "compact_count_clusters",
    "selected_compact_count_cluster",
    "selected_cluster_texts",
    "selected_cluster_rects",
    "warning_reason",
    "combined_text_segment",
    "combined_count_tokens",
    "snapshot_text_count",
    "compact_labels_found",
    "right_rail_region",
    "selected_snapshot_rail_labels",
    "accessibility_node_count",
    "accessibility_compact_labels",
    "ocr_used",
    "ocr_raw_text",
    "ocr_selected_lines",
    "visual_extractor_diagnostics",
    "point_results"
  ]);
  const keys = Object.keys(metrics).filter(
    (key) => key !== "extraction_source" && key !== "confidence" && !diagnosticKeys.has(key) && metrics[key as keyof RawDomDetailMetrics] != null
  );
  return {
    has_network_aweme: false,
    has_detail_aweme: false,
    has_dom_snapshot: false,
    has_dom_detail_metrics: true,
    has_runtime_aweme: false,
    network_keys: [],
    detail_keys: [],
    dom_detail_metric_keys: keys,
    evidence_sources: ["calibrated_point_modal_counts", "smart_capture_harvest"],
    evidence_collection_version: PRODUCTION_EVIDENCE_COLLECTION_VERSION
  };
}

export function extractExactAwemeRuntimeState(document: Document, currentAwemeId: string | null): RuntimeAwemeResult | null {
  const targetId = normalizeRuntimeAwemeId(currentAwemeId);
  if (!targetId) return null;
  const results: RuntimeAwemeResult[] = [];
  for (const node of Array.from(document.querySelectorAll<HTMLElement>("*"))) {
    const record = node as unknown as Record<string, unknown>;
    for (const key of Object.getOwnPropertyNames(record)) {
      const value = record[key];
      if (key.startsWith("__reactFiber$") || key.startsWith("__reactInternalInstance$")) {
        const found = boundedFindExactAweme(value, targetId, RUNTIME_WALKER_DEFAULTS);
        if (found) results.push(buildRuntimeAwemeResult(found, "exact_aweme_runtime_object", "react_fiber_aweme_object", "react_fiber"));
      } else if (key.startsWith("__reactProps$")) {
        const found = boundedFindExactAweme(value, targetId, RUNTIME_WALKER_DEFAULTS);
        if (found) results.push(buildRuntimeAwemeResult(found, "exact_aweme_runtime_object", "react_props_aweme_object", "react_props"));
      }
    }
    for (const key of VUE_RUNTIME_KEYS) {
      const found = boundedFindExactAweme(record[key], targetId, RUNTIME_WALKER_DEFAULTS);
      if (found) results.push(buildRuntimeAwemeResult(found, "exact_aweme_runtime_object", "vue_state_aweme_object", "vue_state"));
    }
  }
  const global = scanSelectedWindowGlobals(targetId);
  if (global) results.push(global);
  const script = scanScriptHydrationAweme(document, targetId);
  if (script) results.push(script);
  const cache = scanNetworkCacheAweme(targetId);
  if (cache) results.push(cache);
  return results[0] ?? null;
}

function buildRuntimeAwemeResult(aweme: Record<string, unknown>, priority: RuntimeAwemePriority, source_used: RuntimeAwemeObjectSource, exact_aweme_source: RuntimeAwemeResult["exact_aweme_source"]): RuntimeAwemeResult {
  const raw_aweme = sanitizeRuntimeAwemeEvidence(aweme);
  return { aweme, raw_aweme, priority, source_used, exact_aweme_source, raw_aweme_keys: Object.keys(raw_aweme) };
}

function boundedFindExactAweme(root: unknown, targetId: string, options: BoundedAwemeSearchOptions): Record<string, unknown> | null {
  const visited = new WeakSet<object>();
  const startedAt = Date.now();
  let objectCount = 0;
  const stack: Array<{ value: unknown; depth: number }> = [{ value: root, depth: 0 }];
  while (stack.length) {
    if (Date.now() - startedAt > options.timeoutMs || objectCount >= options.maxObjects) return null;
    const current = stack.pop();
    if (!current || current.depth > options.maxDepth) continue;
    const value = current.value;
    if (!value || typeof value !== "object" || visited.has(value)) continue;
    visited.add(value);
    objectCount += 1;
    if (isWindowLikeObject(value)) continue;
    const record = value as Record<string, unknown>;
    if (normalizeRuntimeAwemeId(record.aweme_id) === targetId && looksLikeRuntimeAweme(record)) return record;
    for (const key of priorityRuntimeKeys(record).slice(0, options.maxKeysPerObject)) {
      if (SECRET_LIKE_KEY_PATTERN.test(key)) continue;
      const child = safeReadRuntimeChild(record, key);
      if (!child || typeof child === "function") continue;
      if (Array.isArray(child)) for (const entry of child.slice(0, options.maxArrayLength)) stack.push({ value: entry, depth: current.depth + 1 });
      else if (typeof child === "object") stack.push({ value: child, depth: current.depth + 1 });
    }
  }
  return null;
}

function scanScriptHydrationAweme(document: Document, targetId: string): RuntimeAwemeResult | null {
  for (const script of Array.from(document.querySelectorAll<HTMLScriptElement>("script"))) {
    const text = script.textContent ?? "";
    if (!text.includes("aweme_id")) continue;
    for (const root of extractRuntimeJsonRoots(text)) {
      const found = boundedFindExactAweme(root, targetId, RUNTIME_WALKER_DEFAULTS);
      if (found) return buildRuntimeAwemeResult(found, "exact_aweme_script_hydration_object", "script_hydration_aweme_object", "script_hydration");
    }
  }
  return null;
}

function scanNetworkCacheAweme(targetId: string): RuntimeAwemeResult | null {
  if (typeof window === "undefined") return null;
  const win = window as unknown as Record<string, unknown>;
  for (const root of [win.__REUP_DOUYIN_NETWORK_CACHE__, win.__DOUYIN_AWEME_CACHE__]) {
    for (const item of normalizeDouyinNetworkPayload(root, "phase6j_network_cache")) {
      if (normalizeRuntimeAwemeId(item.aweme_id) === targetId) {
        const raw = item.raw_detail_aweme ?? item.raw_network_aweme;
        if (raw) return buildRuntimeAwemeResult(raw as Record<string, unknown>, "exact_aweme_network_cache_object", "network_cache_aweme_object", "network_cache");
      }
    }
    const found = boundedFindExactAweme(root, targetId, RUNTIME_WALKER_DEFAULTS);
    if (found) return buildRuntimeAwemeResult(found, "exact_aweme_network_cache_object", "network_cache_aweme_object", "network_cache");
  }
  return null;
}

function scanSelectedWindowGlobals(targetId: string): RuntimeAwemeResult | null {
  if (typeof window === "undefined") return null;
  const win = window as unknown as Record<string, unknown>;
  for (const key of Object.keys(win).filter((name) => WINDOW_RUNTIME_KEY_PATTERN.test(name)).slice(0, 80)) {
    if (SECRET_LIKE_KEY_PATTERN.test(key)) continue;
    const found = boundedFindExactAweme(win[key], targetId, { ...RUNTIME_WALKER_DEFAULTS, maxObjects: 5_000, timeoutMs: 250 });
    if (found) return buildRuntimeAwemeResult(found, "exact_aweme_runtime_object", "react_props_aweme_object", "react_props");
  }
  return null;
}

function mapRuntimeAwemeMetrics(aweme: Record<string, unknown>): RuntimeAwemeMappedMetrics {
  const video = objectRecord(aweme.video) ?? objectRecord(aweme.video_info) ?? objectRecord(aweme.videoInfo);
  const statistics = objectRecord(aweme.statistics) ?? objectRecord(aweme.stats) ?? objectRecord(aweme.statistics_info) ?? objectRecord(aweme.statisticsInfo);
  const durationCandidates = [
    { source: "aweme.video.duration", raw_value: numberRuntimeValue(video?.duration) },
    { source: "aweme.video.duration_millis", raw_value: numberRuntimeValue(video?.duration_millis) },
    { source: "aweme.video.duration_ms", raw_value: numberRuntimeValue(video?.duration_ms) },
    { source: "aweme.duration", raw_value: numberRuntimeValue(aweme.duration) },
    { source: "aweme.duration_millis", raw_value: numberRuntimeValue(aweme.duration_millis) }
  ];
  const selectedDurationCandidate = durationCandidates.find((candidate) => candidate.raw_value != null) ?? null;
  const durationRaw = selectedDurationCandidate?.raw_value ?? null;
  const duration_seconds = normalizeRuntimeDurationSeconds(durationRaw);
  const duration_validation_result = durationRaw == null
    ? "rejected_missing"
    : durationRaw <= 0
      ? "rejected_non_positive"
      : duration_seconds == null
        ? "rejected_too_large"
        : "accepted_exact_aweme";
  const createTime = numberRuntimeValue(aweme.create_time) ?? numberRuntimeValue(aweme.createTime);
  return {
    duration_seconds,
    duration_text: duration_seconds != null ? formatDuration(duration_seconds) : null,
    duration_raw: durationRaw,
    duration_validation_result,
    duration_candidate_list: durationCandidates.map((candidate) => {
      const normalizedSeconds = normalizeRuntimeDurationSeconds(candidate.raw_value);
      return {
        source: candidate.source,
        raw_value: candidate.raw_value,
        normalized_seconds: normalizedSeconds,
        accepted: candidate === selectedDurationCandidate && normalizedSeconds != null,
        reason: candidate.raw_value == null
          ? "missing"
          : normalizedSeconds == null
            ? "invalid"
            : candidate === selectedDurationCandidate
              ? "selected_exact_aweme"
              : "not_selected"
      };
    }),
    view_count: numberRuntimeValue(statistics?.play_count) ?? null,
    like_count: numberRuntimeValue(statistics?.digg_count) ?? null,
    comment_count: numberRuntimeValue(statistics?.comment_count) ?? null,
    favorite_count: numberRuntimeValue(statistics?.collect_count) ?? null,
    share_count: numberRuntimeValue(statistics?.share_count) ?? numberRuntimeValue(statistics?.forward_count),
    posted_text: null,
    posted_at: createTime ? new Date(createTime * 1000).toISOString() : null,
    posted_source: createTime ? "aweme_create_time" : "none",
    posted_parse_confidence: createTime ? "parsed" : "none"
  };
}

function sanitizeRuntimeAwemeEvidence(value: unknown, depth = 0): RawAwemeEvidence {
  if (!value || typeof value !== "object" || Array.isArray(value)) return {};
  const output: RawAwemeEvidence = {};
  for (const [key, child] of Object.entries(value as Record<string, unknown>).slice(0, 80)) {
    if (SECRET_LIKE_KEY_PATTERN.test(key)) continue;
    output[key] = sanitizeRuntimeEvidenceValue(child, depth + 1);
  }
  return output;
}

function sanitizeRuntimeEvidenceValue(value: unknown, depth: number): RawAwemeEvidence[keyof RawAwemeEvidence] {
  if (value === null || typeof value === "number" || typeof value === "boolean") return value;
  if (typeof value === "string") return value.length > 600 ? `${value.slice(0, 600)}…` : value;
  if (!value || typeof value !== "object" || typeof value === "function") return null;
  if (depth >= 5) return "[Truncated]";
  if (Array.isArray(value)) return value.slice(0, 12).map((entry) => sanitizeRuntimeEvidenceValue(entry, depth + 1));
  const output: RawAwemeEvidence = {};
  for (const [key, child] of Object.entries(value as Record<string, unknown>).slice(0, 80)) {
    if (SECRET_LIKE_KEY_PATTERN.test(key)) continue;
    output[key] = sanitizeRuntimeEvidenceValue(child, depth + 1);
  }
  return output;
}

function priorityRuntimeKeys(record: Record<string, unknown>): string[] {
  const all = Object.keys(record);
  return [...REACT_RUNTIME_KEYS.filter((key) => key in record), ...VUE_RUNTIME_KEYS.filter((key) => key in record), ...all.filter((key) => !REACT_RUNTIME_KEYS.includes(key) && !VUE_RUNTIME_KEYS.includes(key))];
}

function safeReadRuntimeChild(record: Record<string, unknown>, key: string): unknown {
  try {
    return record[key];
  } catch {
    return null;
  }
}

function safeParseRuntimeJson(value: string): unknown | null {
  const trimmed = value.trim();
  if (!trimmed || (trimmed[0] !== "{" && trimmed[0] !== "[")) return null;
  try {
    return JSON.parse(trimmed);
  } catch {
    return null;
  }
}

function looksLikeRuntimeAweme(record: Record<string, unknown>): boolean {
  return Boolean(record.aweme_id && (record.statistics || record.video || record.create_time || record.desc || record.author));
}

function normalizeRuntimeAwemeId(value: unknown): string | null {
  if (typeof value === "string" && value.trim()) return value.trim();
  if (typeof value === "number" && Number.isFinite(value)) return String(value).trim();
  return null;
}

function objectRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : null;
}

function stringRuntimeValue(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function numberRuntimeValue(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string" && value.trim() && /^\d+(?:\.\d+)?$/.test(value.trim())) return Number(value.trim());
  return null;
}

function normalizeRuntimeDurationSeconds(value: number | null): number | null {
  if (value == null || value <= 0) return null;
  return value >= 1000 ? Math.round(value / 1000) : value;
}

function extractRuntimeJsonRoots(source: string): unknown[] {
  const roots: unknown[] = [];
  const direct = safeParseRuntimeJson(source);
  if (direct) roots.push(direct);
  for (const literal of extractRuntimeBalancedJsonLiterals(source)) {
    const parsed = safeParseRuntimeJson(literal);
    if (parsed) roots.push(parsed);
  }
  return roots.slice(0, 50);
}

function extractRuntimeBalancedJsonLiterals(source: string): string[] {
  const literals: string[] = [];
  for (let index = 0; index < source.length; index += 1) {
    const char = source[index];
    if (char !== "{" && char !== "[") continue;
    const literal = readRuntimeBalancedLiteral(source, index);
    if (literal) {
      literals.push(literal.value);
      index = literal.endIndex;
    }
  }
  return literals.slice(0, 50);
}

function readRuntimeBalancedLiteral(source: string, startIndex: number): { value: string; endIndex: number } | null {
  const opener = source[startIndex];
  const closer = opener === "{" ? "}" : "]";
  const stack = [closer];
  let inString = false;
  let escaped = false;
  for (let index = startIndex + 1; index < source.length; index += 1) {
    const char = source[index];
    if (inString) {
      if (escaped) escaped = false;
      else if (char === "\\") escaped = true;
      else if (char === '"') inString = false;
      continue;
    }
    if (char === '"') {
      inString = true;
      continue;
    }
    if (char === "{" || char === "[") stack.push(char === "{" ? "}" : "]");
    else if (char === "}" || char === "]") {
      if (stack.pop() !== char) return null;
      if (!stack.length) return { value: source.slice(startIndex, index + 1), endIndex: index };
    }
  }
  return null;
}

function isWindowLikeObject(value: object): boolean {
  return typeof window !== "undefined" && value === window;
}

export function selectActiveModalVideo(document: Document): HTMLVideoElement | null {
  const videos = Array.from(document.querySelectorAll<HTMLVideoElement>("video")).filter((video) => isVisible(video));
  if (!videos.length) return null;
  const playing = videos.filter((video) => video.paused === false && isFinite(video.duration) && video.duration > 0);
  const candidates = playing.length ? playing : videos;
  return candidates.sort((left, right) => visibleArea(right) - visibleArea(left))[0] ?? null;
}

export function extractDurationFromVideo(video: HTMLVideoElement | null): number | null {
  if (!video) return null;
  const duration = video.duration;
  if (!Number.isFinite(duration) || duration <= 0) return null;
  return Math.round(duration * 1000) / 1000;
}

export function findTimelineDurationText(document: Document): { text: string; duration_text: string } | null {
  const nodes = Array.from(document.querySelectorAll<HTMLElement>("div, span, p"));
  for (const node of nodes) {
    const text = compactText(node.innerText || node.textContent || "");
    const match = /(\d{1,2}:\d{2}(?::\d{2})?)\s*\/\s*(\d{1,2}:\d{2}(?::\d{2})?)/.exec(text);
    if (match?.[2]) return { text, duration_text: match[2] };
  }
  return null;
}

export function parseTimelineDurationSeconds(value: string | null): number | null {
  if (!value) return null;
  const match = /^(\d{1,2}):(\d{2})(?::(\d{2}))?$/.exec(value.trim());
  if (!match) return null;
  if (match[3] !== undefined) {
    const hours = Number(match[1]);
    const minutes = Number(match[2]);
    const seconds = Number(match[3]);
    if (minutes >= 60 || seconds >= 60) return null;
    return hours * 3600 + minutes * 60 + seconds;
  }
  const minutes = Number(match[1]);
  const seconds = Number(match[2]);
  if (seconds >= 60) return null;
  return minutes * 60 + seconds;
}

export function findPostedText(document: Document): string | null {
  const nodes = Array.from(document.querySelectorAll<HTMLElement>("div, span, p"));
  for (const node of nodes) {
    const text = compactText(node.innerText || node.textContent || "");
    if (!text) continue;
    const match = /(\d+\s*(?:分钟前|小时前|天前|周前|月前|年前)|昨天|前天|\d{4}[./-]\d{1,2}[./-]\d{1,2}(?:\s+\d{1,2}:\d{2})?)/.exec(text);
    if (match?.[1]) return match[1];
  }
  return null;
}

function emptyActionBlockDetection(document: Document): CandidateDetectionResult {
  const viewportWidth = Math.max(0, Math.round(window.innerWidth || document.documentElement?.clientWidth || 0));
  const viewportHeight = Math.max(0, Math.round(window.innerHeight || document.documentElement?.clientHeight || 0));
  const activeVideo = selectActiveModalVideo(document);
  const activeVideoRect = activeVideo ? roundRect(activeVideo.getBoundingClientRect()) : null;
  return {
    accepted: [],
    rejected: [],
    rail_x_band: null,
    computed_rail_x_band: null,
    viewport_width: viewportWidth,
    viewport_height: viewportHeight,
    active_video_rect: activeVideoRect,
    modal_candidate_rect: null,
    icon_candidates: [],
    selected_action_icons: [],
    icon_anchored_metrics: [],
    rejected_number_examples: [],
    rejected_icon_examples: [],
    compact_count_candidates: [],
    compact_text_node_candidates_count: 0,
    compact_count_clusters: [],
    selected_compact_count_cluster: null,
    selected_cluster_texts: null,
    selected_cluster_rects: null,
    rail_region: null,
    numeric_labels_found: [],
    selected_rail_labels: null,
    selected_rail_labels_with_rect: null,
    assigned_metrics: null,
    rejected_examples: [],
    extraction_mode: null,
    action_blocks_missing_reason: "no_compact_counts",
    warning_reason: null
  };
}

function extractCdpDomSnapshotRightRail(snapshot: CdpDomSnapshotPayload | null | undefined, activeVideoRect: ActionRailRectDiagnostic | null): CdpDomSnapshotMetricSelection {
  if (!snapshot) return { result: null, warning_reason: "cdp_dom_snapshot_unavailable" };
  const region = computeSnapshotRightRailRegion(snapshot.viewport_width, snapshot.viewport_height, activeVideoRect);
  const rejected: ActionRailRejectedCandidateDiagnostic[] = [];
  const candidates: CdpDomSnapshotRailLabel[] = [];
  for (const entry of snapshot.text_entries) {
    const reason = getSnapshotTextRejectionReason(entry.text, entry.rect, region, snapshot.viewport_width, snapshot.viewport_height, activeVideoRect);
    if (reason) {
      if (rejected.length < 12) rejected.push({ visible_text: entry.text, rect: entry.rect, reason });
      continue;
    }
    const token = extractExactCompactCountText(entry.text);
    const value = parseMetricValue(token);
    if (token && value != null) candidates.push({ text: token, value, rect: entry.rect });
  }
  const deduped = dedupeSnapshotRailLabels(candidates).sort((a, b) => a.rect.y - b.rect.y || a.rect.x - b.rect.x);
  const selected = selectSnapshotRailLabelGroup(deduped);
  const warning = snapshotRailWarningReason(deduped, selected);
  if (!selected) {
    return {
      result: {
        source_used: "cdp_dom_snapshot_right_rail",
        extraction_source: "cdp_dom_snapshot_right_rail",
        confidence: "high",
        viewport_width: snapshot.viewport_width,
        viewport_height: snapshot.viewport_height,
        snapshot_text_count: snapshot.text_entries.length,
        compact_labels_found: deduped.length,
        right_rail_region: region,
        selected_rail_labels: [],
        rejected_examples: rejected,
        warning_reason: warning,
        status: "WARN",
        like_count: null,
        comment_count: null,
        favorite_count: null,
        share_count: null
      },
      warning_reason: warning
    };
  }
  const metricOrder: Array<NonNullable<CdpDomSnapshotRailLabel["assigned_metric"]>> = ["like", "comment", "favorite", "share"];
  const assigned = selected.map((label, index): CdpDomSnapshotRailLabel => ({ ...label, assigned_metric: metricOrder[index] ?? null }));
  return {
    result: {
      source_used: "cdp_dom_snapshot_right_rail",
      extraction_source: "cdp_dom_snapshot_right_rail",
      confidence: "high",
      viewport_width: snapshot.viewport_width,
      viewport_height: snapshot.viewport_height,
      snapshot_text_count: snapshot.text_entries.length,
      compact_labels_found: deduped.length,
      right_rail_region: region,
      selected_rail_labels: assigned,
      rejected_examples: rejected,
      warning_reason: null,
      status: "PASS",
      like_count: assigned[0]?.value ?? null,
      comment_count: assigned[1]?.value ?? null,
      favorite_count: assigned[2]?.value ?? null,
      share_count: assigned[3]?.value ?? null
    },
    warning_reason: null
  };
}

function computeSnapshotRightRailRegion(viewportWidth: number, viewportHeight: number, activeVideoRect: ActionRailRectDiagnostic | null): ActionRailRailRegionDiagnostic {
  const fallbackMinX = Math.max(0, viewportWidth - 170);
  const activeMinX = activeVideoRect ? Math.min(viewportWidth - 20, Math.max(activeVideoRect.x + activeVideoRect.width, activeVideoRect.x + activeVideoRect.width - 20)) : fallbackMinX;
  const minX = activeVideoRect ? Math.max(0, Math.min(activeMinX, fallbackMinX)) : fallbackMinX;
  return {
    min_x: Math.round(minX),
    max_x: Math.max(0, Math.round(viewportWidth - 20)),
    min_y: 90,
    max_y: Math.max(90, Math.round(viewportHeight - 130)),
    source: activeVideoRect ? "active_video_geometry" : "viewport_right_band"
  };
}

function getSnapshotTextRejectionReason(text: string, rect: ActionRailRectDiagnostic, region: ActionRailRailRegionDiagnostic, viewportWidth: number, viewportHeight: number, activeVideoRect: ActionRailRectDiagnostic | null): string | null {
  const trimmed = text.trim();
  if (!trimmed) return "empty_text";
  if (rect.width <= 0 || rect.height <= 0) return "zero_area";
  if (rect.x < 0 || rect.y < 0 || rect.x >= viewportWidth || rect.y >= viewportHeight) return "offscreen";
  if (rect.width > Math.max(240, viewportWidth * 0.25) || rect.height > 80) return "huge_text_block";
  if (rect.x < region.min_x || rect.x > region.max_x || rect.y < region.min_y || rect.y > region.max_y) return "outside_right_rail_region";
  if (isInLeftCaptionArea(rect, viewportWidth, activeVideoRect)) return "left_caption_area";
  if (/\d{1,2}:\d{2}/.test(trimmed)) return "timeline_or_duration_text";
  if (containsHardExcludedText(trimmed) || containsRejectedCandidateText(trimmed)) return "excluded_text";
  if (/^@/.test(trimmed) || /第\s*\d+\s*集/.test(trimmed) || /豆瓣\s*\d+(?:\.\d+)?/.test(trimmed)) return "caption_or_profile_text";
  if (!extractExactCompactCountText(trimmed)) return "not_compact_count";
  return null;
}

function dedupeSnapshotRailLabels(labels: CdpDomSnapshotRailLabel[]): CdpDomSnapshotRailLabel[] {
  const result: CdpDomSnapshotRailLabel[] = [];
  for (const label of labels) {
    const duplicate = result.some((existing) => existing.text === label.text && Math.abs(existing.rect.x - label.rect.x) <= 3 && Math.abs(existing.rect.y - label.rect.y) <= 3);
    if (!duplicate) result.push(label);
  }
  return result;
}

function selectSnapshotRailLabelGroup(labels: CdpDomSnapshotRailLabel[]): CdpDomSnapshotRailLabel[] | null {
  if (labels.length < 4) return null;
  if (labels.length === 4) return labels;
  let best: { labels: CdpDomSnapshotRailLabel[]; score: number } | null = null;
  let ambiguous = false;
  for (let index = 0; index <= labels.length - 4; index += 1) {
    const group = labels.slice(index, index + 4);
    const centerXs = group.map((label) => label.rect.x + label.rect.width / 2);
    const ys = group.map((label) => label.rect.y);
    const xSpread = Math.max(...centerXs) - Math.min(...centerXs);
    const gaps = [group[1]!.rect.y - group[0]!.rect.y, group[2]!.rect.y - group[1]!.rect.y, group[3]!.rect.y - group[2]!.rect.y];
    const positiveGaps = gaps.every((gap) => gap >= 24 && gap <= 170);
    if (xSpread > 70 || !positiveGaps) continue;
    const gapSpread = Math.max(...gaps) - Math.min(...gaps);
    const score = xSpread + gapSpread * 0.5 + index * 2;
    if (!best || score < best.score) {
      ambiguous = best ? Math.abs(best.score - score) < 8 : false;
      best = { labels: group, score };
    } else if (Math.abs(best.score - score) < 8) {
      ambiguous = true;
    }
  }
  return best && !ambiguous ? best.labels : null;
}

function snapshotRailWarningReason(labels: CdpDomSnapshotRailLabel[], selected: CdpDomSnapshotRailLabel[] | null): string | null {
  if (selected) return null;
  if (labels.length < 4) return "cdp_dom_snapshot_right_rail_fewer_than_four_labels";
  return "cdp_dom_snapshot_right_rail_ambiguous_labels";
}

function snapshotLabelToNumericDiagnostic(label: CdpDomSnapshotRailLabel): ActionRailNumericLabelDiagnostic {
  return {
    visible_text: label.text,
    value: label.value,
    rect: label.rect,
    accepted: true,
    reason: null,
    source: "element",
    center_x: label.rect.x + label.rect.width / 2,
    center_y: label.rect.y + label.rect.height / 2
  };
}

function extractVisualRightRailMetrics(payload: VisualRightRailPayload | null): VisualRightRailMetricSelection {
  const accessibilityLabels = collectAccessibilityCompactLabels(payload);
  const ocrLines = parseOcrCompactCountLines(payload?.screenshot_ocr?.raw_text ?? "");
  const cropRegion = payload?.screenshot_ocr?.crop_region ?? computeVisualRightRailRegion(payload?.accessibility_tree?.viewport_width ?? payload?.screenshot_ocr?.viewport_width ?? 0, payload?.accessibility_tree?.viewport_height ?? payload?.screenshot_ocr?.viewport_height ?? 0);
  const diagnostics: VisualRightRailDiagnostics = {
    source_used: null,
    accessibility_node_count: payload?.accessibility_tree?.nodes.length ?? 0,
    accessibility_compact_labels: accessibilityLabels,
    ocr_used: Boolean(payload?.screenshot_ocr),
    ocr_raw_text: payload?.screenshot_ocr?.raw_text ?? null,
    ocr_parsed_lines: payload?.screenshot_ocr?.parsed_lines ?? ocrLines.map((line) => line.text),
    ocr_selected_lines: [],
    crop_region: cropRegion,
    warning_reason: null
  };
  const axSelected = selectVisualLabels(accessibilityLabels, cropRegion);
  if (axSelected.length >= 4) {
    diagnostics.source_used = "accessibility_tree_right_rail";
    return { source: "accessibility_tree_right_rail", labels: axSelected.slice(0, 4), diagnostics, warning_reason: null };
  }
  const ocrLabels: VisualRightRailLabel[] = ocrLines.map((line, index) => ({ text: line.text, value: line.value, y: index, rect: null, source: "screenshot_ocr", role: null, backend_dom_node_id: null }));
  diagnostics.ocr_selected_lines = ocrLabels.slice(0, 4).map((label) => label.text);
  if (ocrLabels.length >= 4) {
    diagnostics.source_used = "screenshot_ocr_right_rail";
    return { source: "screenshot_ocr_right_rail", labels: ocrLabels.slice(0, 4), diagnostics, warning_reason: null };
  }
  diagnostics.warning_reason = axSelected.length || ocrLabels.length ? "visual_right_rail_incomplete_counts" : "visual_right_rail_no_compact_counts";
  return { source: null, labels: axSelected.length ? axSelected : ocrLabels, diagnostics, warning_reason: diagnostics.warning_reason };
}

function collectAccessibilityCompactLabels(payload: VisualRightRailPayload | null): VisualRightRailLabel[] {
  const labels: VisualRightRailLabel[] = [];
  for (const node of payload?.accessibility_tree?.nodes ?? []) {
    if (node.ignored === true) continue;
    const text = extractExactCompactCountText(node.name);
    const value = parseMetricValue(text);
    if (!text || value == null || isRejectedVisualCountText(node.name)) continue;
    labels.push({ text, value, rect: node.rect ?? null, y: node.rect ? node.rect.y + node.rect.height / 2 : null, source: "accessibility_tree", role: node.role ?? null, backend_dom_node_id: node.backend_dom_node_id ?? null });
  }
  return labels;
}

function selectVisualLabels(labels: VisualRightRailLabel[], region: ActionRailRailRegionDiagnostic | null): VisualRightRailLabel[] {
  const bounded = region ? labels.filter((label) => !label.rect || rectInRailRegion(label.rect, region)) : labels;
  return dedupeVisualLabels([...(bounded.length >= 4 ? bounded : labels)].sort((a, b) => (a.y ?? a.rect?.y ?? 0) - (b.y ?? b.rect?.y ?? 0)));
}

function dedupeVisualLabels(labels: VisualRightRailLabel[]): VisualRightRailLabel[] {
  const result: VisualRightRailLabel[] = [];
  for (const label of labels) {
    const y = label.y ?? label.rect?.y ?? null;
    if (result.some((existing) => existing.text === label.text && Math.abs((existing.y ?? existing.rect?.y ?? -9999) - (y ?? -9999)) < 12)) continue;
    result.push(label);
  }
  return result;
}

function parseOcrCompactCountLines(rawText: string): Array<{ text: string; value: number }> {
  return rawText
    .split(/\r?\n/)
    .map((line) => line.trim())
    .map((line) => extractExactCompactCountText(line))
    .filter((line): line is string => Boolean(line && !isRejectedVisualCountText(line)))
    .map((text) => ({ text, value: parseMetricValue(text) }))
    .filter((line): line is { text: string; value: number } => line.value != null);
}

function computeVisualRightRailRegion(viewportWidth: number, viewportHeight: number): ActionRailRailRegionDiagnostic | null {
  if (!viewportWidth || !viewportHeight) return null;
  return { min_x: Math.max(0, viewportWidth - 170), max_x: Math.max(0, viewportWidth - 20), min_y: 90, max_y: Math.max(90, viewportHeight - 130), source: "viewport_right_band" };
}

function rectInRailRegion(rect: ActionRailRectDiagnostic, region: ActionRailRailRegionDiagnostic): boolean {
  const centerX = rect.x + rect.width / 2;
  const centerY = rect.y + rect.height / 2;
  return centerX >= region.min_x && centerX <= region.max_x && centerY >= region.min_y && centerY <= region.max_y;
}

function isRejectedVisualCountText(text: string): boolean {
  return /第\d+集|豆瓣|\d{4}[-/.年]\d{1,2}|听抖音|@|倍速|智能|清屏|连播|搜索|合集|完整版|分钟|小时|评论区|关注/.test(text);
}

function detectActionBlockCandidates(document: Document): CandidateDetectionResult {
  const viewportWidth = window.innerWidth || document.documentElement?.clientWidth || 0;
  const viewportHeight = window.innerHeight || document.documentElement?.clientHeight || 0;
  const activeVideo = selectActiveModalVideo(document);
  const activeVideoRect = activeVideo ? roundRectWithFallback(activeVideo.getBoundingClientRect()) : null;
  const modalCandidateRect = activeVideoRect;
  const railRegion = computeRightRailRegion(viewportWidth, viewportHeight, activeVideoRect);
  const elementLabels = collectRightRailNumericLabels(document, railRegion);
  const fallbackLabels = collectRightRailLabelsFromPoint(document, railRegion);
  const labels = dedupeNumericRailLabels([...elementLabels, ...fallbackLabels]);
  const selected = selectRightRailNumericLabels(labels);
  const accepted = buildCandidatesFromRailLabels(selected);
  const selectedKeys = new Set(selected.map((candidate) => numericRailLabelKey(candidate)));
  const diagnostics = labels.map((candidate) => numericRailLabelDiagnostic(candidate, selectedKeys.has(numericRailLabelKey(candidate))));
  const rejected = diagnostics
    .filter((candidate) => !candidate.accepted)
    .slice(0, 12)
    .map((candidate) => ({ visible_text: candidate.visible_text, reason: candidate.reason ?? "not_selected_right_rail_label", rect: candidate.rect }));
  const railXBand: ActionRailXBandDiagnostic = { min: railRegion.minX, max: railRegion.maxX, source: "right_rail_numeric_band" };
  const extractionMode: ActionRailExtractionMode | null = accepted.length
    ? selected.some((candidate) => candidate.source === "element_from_point") && elementLabels.filter((candidate) => candidate.reason === null).length < 4
      ? "right_rail_element_from_point_fallback"
      : "right_rail_numeric_band"
    : null;
  const actionBlocksMissingReason: ActionRailMissingReason | null = accepted.length ? null : labels.length === 0 ? "no_compact_counts" : "compact_counts_rejected";
  const warningReason = accepted.length > 0 && accepted.length < 4 ? "partial_right_rail_numeric_band" : actionBlocksMissingReason;
  return {
    accepted,
    rejected,
    rail_x_band: railXBand,
    computed_rail_x_band: railXBand,
    viewport_width: viewportWidth,
    viewport_height: viewportHeight,
    active_video_rect: activeVideoRect,
    modal_candidate_rect: modalCandidateRect,
    icon_candidates: [],
    selected_action_icons: [],
    icon_anchored_metrics: [],
    rejected_number_examples: rejected.slice(0, 10),
    rejected_icon_examples: [],
    compact_count_candidates: diagnostics,
    compact_text_node_candidates_count: 0,
    compact_count_clusters: [],
    selected_compact_count_cluster: null,
    selected_cluster_texts: selected.map((candidate) => candidate.text),
    selected_cluster_rects: selected.map((candidate) => roundRect(candidate.rect)),
    rail_region: railRegionDiagnostic(railRegion),
    numeric_labels_found: diagnostics,
    selected_rail_labels: selected.map((candidate) => candidate.text),
    selected_rail_labels_with_rect: selected.map((candidate) => numericRailLabelDiagnostic(candidate, true)),
    assigned_metrics: assignedRailMetricDiagnostics(selected, extractionMode ?? "right_rail_numeric_band"),
    rejected_examples: rejected,
    extraction_mode: extractionMode,
    action_blocks_missing_reason: actionBlocksMissingReason,
    warning_reason: warningReason
  };
}

function computeRightRailRegion(viewportWidth: number, viewportHeight: number, activeVideoRect: ActionRailRectDiagnostic | null): RightRailRegion {
  const minY = Math.max(80, Math.round(viewportHeight * 0.08));
  const maxY = Math.max(minY + 1, viewportHeight - 120);
  const viewportMinX = Math.max(0, viewportWidth - 140);
  if (activeVideoRect && activeVideoRect.x + activeVideoRect.width < viewportWidth - 80) {
    return { minX: Math.max(0, Math.round(activeVideoRect.x + activeVideoRect.width)), maxX: viewportWidth, minY, maxY, source: "active_video_geometry" };
  }
  return { minX: viewportMinX, maxX: viewportWidth, minY, maxY, source: "viewport_right_band" };
}

function collectRightRailNumericLabels(document: Document, railRegion: RightRailRegion): NumericRailLabelCandidate[] {
  return Array.from(document.querySelectorAll<HTMLElement>("*"))
    .filter((node) => isElementLike(node) && isVisible(node))
    .map((node) => numericRailCandidateFromElement(node, "element", railRegion))
    .filter((candidate): candidate is NumericRailLabelCandidate => Boolean(candidate));
}

function collectRightRailLabelsFromPoint(document: Document, railRegion: RightRailRegion): NumericRailLabelCandidate[] {
  const elementsFromPoint = document.elementsFromPoint?.bind(document);
  if (!elementsFromPoint) return [];
  const candidates: NumericRailLabelCandidate[] = [];
  const sampleXs = [railRegion.maxX - 24, railRegion.maxX - 56, Math.round((railRegion.minX + railRegion.maxX) / 2)].filter((x) => x >= railRegion.minX && x <= railRegion.maxX);
  const step = Math.max(18, Math.round((railRegion.maxY - railRegion.minY) / 28));
  for (let y = railRegion.minY; y <= railRegion.maxY; y += step) {
    for (const x of sampleXs) {
      for (const node of elementsFromPoint(x, y)) {
        if (isElementLike(node) && isVisible(node)) {
          const candidate = numericRailCandidateFromElement(node, "element_from_point", railRegion);
          if (candidate) candidates.push(candidate);
        }
      }
    }
  }
  return candidates;
}

function numericRailCandidateFromElement(node: HTMLElement, source: "element" | "element_from_point", railRegion: RightRailRegion): NumericRailLabelCandidate | null {
  const rect = normalizeRect(node.getBoundingClientRect());
  const rawText = compactText(node.innerText || node.textContent || "");
  const text = extractRightRailMetricText(rawText);
  const reason = getNumericRailLabelRejectionReason(node, text, rect, railRegion);
  if (!text && !reason) return null;
  return {
    node,
    text: text ?? rawText.slice(0, 80),
    value: parseRailMetricValue(null, text),
    rect,
    source,
    accepted: reason === null,
    reason,
    nearestTag: node.tagName?.toLowerCase() ?? null,
    nearestClass: typeof node.className === "string" ? node.className.slice(0, 120) : null,
    nearestAriaLabel: node.getAttribute?.("aria-label") ?? null,
    nearestTitle: node.getAttribute?.("title") ?? null
  };
}

function getNumericRailLabelRejectionReason(node: HTMLElement, text: string | null, rect: { x: number; y: number; width: number; height: number }, railRegion: RightRailRegion): string | null {
  const rawText = compactText(node.innerText || node.textContent || "");
  if (!rawText) return "empty_text";
  if (looksLikeDateLikeDecimal(rawText)) return "date_like_decimal_text";
  if (!text) return "not_exact_compact_numeric_label";
  if (rect.width <= 0 || rect.height <= 0) return "zero_element_rect";
  const centerX = rect.x + rect.width / 2;
  const centerY = rect.y + rect.height / 2;
  if (centerX < railRegion.minX || centerX > railRegion.maxX || centerY < railRegion.minY || centerY > railRegion.maxY) return centerX < railRegion.minX ? "left_caption_area" : "outside_right_rail_region";
  if (rect.width > 96 || rect.height > 48) return "label_rect_too_large";
  if (containsHardExcludedText(rawText) || looksLikeTimelineText(rawText)) return "hard_excluded_number_text";
  const parentText = compactText(node.parentElement?.innerText || node.parentElement?.textContent || "");
  if (parentText && parentText !== rawText && containsHardExcludedText(parentText)) return "hard_excluded_number_text";
  if (isInsideSearchBox(node)) return "search_box_text";
  if (hasVideoCardAncestor(node)) return "profile_grid_card_number";
  return null;
}

function extractExactCompactCountText(text: string): string | null {
  const normalized = compactText(text);
  if (!normalized || normalized.length > 8) return null;
  if (/^\d+(?:\.\d+)?\s*(?:万|w|W|k|K)?$/.test(normalized)) return normalized.replace(/\s+/g, "");
  return null;
}

function dedupeNumericRailLabels(candidates: NumericRailLabelCandidate[]): NumericRailLabelCandidate[] {
  const acceptedFirst = [...candidates].sort((left, right) => Number(right.reason === null) - Number(left.reason === null));
  const result: NumericRailLabelCandidate[] = [];
  for (const candidate of acceptedFirst) {
    const keyMatch = result.find((existing) => existing.text === candidate.text && Math.abs(centerY(existing.rect) - centerY(candidate.rect)) <= 10 && Math.abs(centerX(existing.rect) - centerX(candidate.rect)) <= 20);
    if (!keyMatch) result.push(candidate);
  }
  return result.sort((left, right) => centerY(left.rect) - centerY(right.rect));
}

function selectRightRailNumericLabels(candidates: NumericRailLabelCandidate[]): NumericRailLabelCandidate[] {
  const accepted = candidates.filter((candidate) => candidate.reason === null).sort((left, right) => centerY(left.rect) - centerY(right.rect));
  if (accepted.length <= 1) return accepted.slice(0, 1);
  const clusters = accepted.filter((candidate, _index, array) => Math.abs(centerX(candidate.rect) - median(array.map((item) => centerX(item.rect)))) <= 80);
  const separated: NumericRailLabelCandidate[] = [];
  for (const candidate of clusters) {
    if (!separated.some((existing) => Math.abs(centerY(existing.rect) - centerY(candidate.rect)) < 26)) separated.push(candidate);
  }
  return separated.slice(0, 4);
}

function buildCandidatesFromRailLabels(labels: NumericRailLabelCandidate[]): ActionBlockCandidate[] {
  const kinds: ActionKind[] = ["like", "comment", "favorite", "share"];
  return labels.map((label, index) => ({
    semantic_kind: kinds[index] ?? null,
    icon_kind: kinds[index] ?? null,
    countNode: label.node,
    marker: label.node,
    blockElements: [label.node],
    blockText: label.text,
    metricText: label.text,
    value: label.value,
    confidence: labels.length >= 4 || index === 0 ? "high" : "low",
    order_index: index,
    block_descriptor: `right_rail_numeric_band:${index}:${label.text}`,
    rect: label.rect,
    hints: label.source
  }));
}

function railRegionDiagnostic(region: RightRailRegion): ActionRailRailRegionDiagnostic {
  return { min_x: region.minX, max_x: region.maxX, min_y: region.minY, max_y: region.maxY, source: region.source };
}

function numericRailLabelDiagnostic(candidate: NumericRailLabelCandidate, accepted: boolean): ActionRailNumericLabelDiagnostic {
  return {
    visible_text: candidate.text || null,
    value: candidate.value,
    rect: roundRect(candidate.rect),
    accepted,
    reason: accepted ? null : candidate.reason ?? "not_selected_right_rail_label",
    source: candidate.source,
    center_x: Math.round(centerX(candidate.rect)),
    center_y: Math.round(centerY(candidate.rect)),
    nearest_tag: candidate.nearestTag,
    nearest_class: candidate.nearestClass,
    nearest_aria_label: candidate.nearestAriaLabel,
    nearest_title: candidate.nearestTitle
  };
}

function assignedRailMetricDiagnostics(labels: NumericRailLabelCandidate[], mode: ActionRailExtractionMode): ActionRailAssignedMetricDiagnostic[] {
  const kinds: ActionKind[] = ["like", "comment", "favorite", "share"];
  return labels.map((label, index) => ({ metric: kinds[index] ?? "share", visible_text: label.text, value: label.value, rect: roundRect(label.rect), source: mode }));
}

function numericRailLabelKey(candidate: NumericRailLabelCandidate): string {
  return `${candidate.text}:${Math.round(centerX(candidate.rect))}:${Math.round(centerY(candidate.rect))}`;
}

function centerX(rect: { x: number; width: number }): number {
  return rect.x + rect.width / 2;
}

function centerY(rect: { y: number; height: number }): number {
  return rect.y + rect.height / 2;
}

function median(values: number[]): number {
  if (!values.length) return 0;
  const sorted = [...values].sort((left, right) => left - right);
  return sorted[Math.floor(sorted.length / 2)] ?? 0;
}

function collectActionIconCandidates(
  nodes: HTMLElement[],
  viewportWidth: number,
  viewportHeight: number,
  activeVideoRect: ActionRailRectDiagnostic | null,
  rejectedIcons: ActionRailRejectedCandidateDiagnostic[]
): ActionIconCandidate[] {
  return nodes
    .map((node) => {
      const rect = normalizeRect(node.getBoundingClientRect());
      const hints = collectIconSemanticHints(node);
      const kind = identifyActionIconKind(hints);
      const rejectionReason = getIconCandidateRejectionReason(node, rect, hints, viewportWidth, viewportHeight, activeVideoRect);
      if (rejectionReason) rejectedIcons.push({ visible_text: hints || null, reason: rejectionReason, rect: roundRect(rect) });
      return { node, kind, rect, hints, rejectionReason } satisfies ActionIconCandidate;
    })
    .filter((candidate) => !candidate.rejectionReason);
}

function selectRightRailActionIcons(candidates: ActionIconCandidate[]): ActionIconCandidate[] {
  const actionOrder = ["like", "comment", "favorite", "share"] as const;
  const ordered = candidates.slice().sort((left, right) => left.rect.y - right.rect.y);
  const selected: ActionIconCandidate[] = [];
  for (const kind of actionOrder) {
    const semantic = ordered.find((candidate) => candidate.kind === kind && !selected.includes(candidate));
    if (semantic) selected.push(semantic);
  }
  const missingKinds = actionOrder.filter((kind) => !selected.some((candidate) => candidate.kind === kind));
  for (const candidate of ordered) {
    if (selected.length >= 4) break;
    if (selected.includes(candidate)) continue;
    const nextKind = missingKinds.shift();
    if (!nextKind) break;
    selected.push({ ...candidate, kind: candidate.kind ?? nextKind });
  }
  return selected.sort((left, right) => actionOrder.indexOf((left.kind ?? "share") as ActionKind) - actionOrder.indexOf((right.kind ?? "share") as ActionKind));
}

function buildIconAnchoredMetrics(selectedIcons: ActionIconCandidate[], counts: CompactCountCandidate[], rejectedNumbers: ActionRailRejectedCandidateDiagnostic[]): IconAnchoredMetric[] {
  return selectedIcons.map((icon, index) => {
    const kind = icon.kind ?? (["like", "comment", "favorite", "share"] as const)[index]!;
    const count = findCountBelowIcon(icon, counts);
    if (!count) rejectedNumbers.push({ visible_text: null, reason: `count_missing_below_${kind}_icon`, rect: roundRect(icon.rect) });
    return { kind, icon, count, distance: count ? Math.round(count.rect.y - (icon.rect.y + icon.rect.height)) : null } satisfies IconAnchoredMetric;
  });
}

function buildCandidatesFromIconAnchors(metrics: IconAnchoredMetric[]): ActionBlockCandidate[] {
  return metrics
    .filter((metric) => metric.count?.value !== null && metric.count?.value !== undefined)
    .map((metric, index) => {
      const count = metric.count!;
      const rect = mergeRects([metric.icon.rect, count.rect]);
      return {
        semantic_kind: metric.kind,
        icon_kind: metric.kind,
        countNode: count.node,
        marker: metric.icon.node,
        blockElements: [metric.icon.node, count.node],
        blockText: count.text,
        metricText: count.text,
        value: count.value,
        confidence: metric.icon.kind ? "high" : "low",
        order_index: index,
        block_descriptor: `${metric.kind}:${Math.round(rect.y)}:${count.text}`,
        rect,
        hints: metric.icon.hints ? `${metric.icon.hints} | source=icon_anchored_right_rail` : "source=icon_anchored_right_rail"
      } satisfies ActionBlockCandidate;
    });
}

function findCountBelowIcon(icon: ActionIconCandidate, counts: CompactCountCandidate[]): CompactCountCandidate | null {
  const iconCenterX = icon.rect.x + icon.rect.width / 2;
  const eligible = counts
    .filter((count) => !count.rejectionReason && count.value !== null)
    .map((count) => ({ count, dx: Math.abs(count.rect.x + count.rect.width / 2 - iconCenterX), dy: count.rect.y - (icon.rect.y + icon.rect.height) }))
    .filter((item) => item.dx <= 50 && item.dy >= 0 && item.dy <= 55)
    .sort((left, right) => left.dy * 10 + left.dx - (right.dy * 10 + right.dx));
  return eligible[0]?.count ?? null;
}

function iconAnchoredXBand(icons: ActionIconCandidate[]): ActionRailXBandDiagnostic {
  const centers = icons.map((icon) => icon.rect.x + icon.rect.width / 2);
  const center = centers.length ? centers.reduce((sum, value) => sum + value, 0) / centers.length : 0;
  return { min: Math.max(0, Math.round(center - 70)), max: Math.round(center + 70), source: "icon_candidates" };
}

function iconDiagnostic(candidate: ActionIconCandidate, accepted: boolean): ActionRailIconCandidateDiagnostic {
  return { kind: candidate.kind, rect: roundRect(candidate.rect), accepted, reason: accepted ? null : candidate.rejectionReason ?? "not_selected_action_icon", hints: candidate.hints };
}

function iconAnchoredMetricDiagnostic(metric: IconAnchoredMetric): ActionRailIconAnchoredMetricDiagnostic {
  return { metric: metric.kind, icon_rect: roundRect(metric.icon.rect), count_text: metric.count?.text ?? null, count_rect: metric.count ? roundRect(metric.count.rect) : null, distance_icon_to_count: metric.distance, source: "icon_anchored_right_rail" };
}

function collectIconSemanticHints(node: HTMLElement): string {
  const parent = node.parentElement;
  const titleTexts = Array.from(node.querySelectorAll?.("title") ?? []).map((item) => item.textContent || "");
  const useRefs = Array.from(node.querySelectorAll?.("use") ?? []).flatMap((item) => [item.getAttribute("href") || "", item.getAttribute("xlink:href") || ""]);
  const parts = [
    node.getAttribute("aria-label") || "",
    node.getAttribute("title") || "",
    node.getAttribute("href") || "",
    node.getAttribute("xlink:href") || "",
    ...titleTexts,
    ...useRefs,
    typeof node.className === "string" ? node.className : String(node.className || ""),
    parent?.getAttribute?.("aria-label") || "",
    parent?.getAttribute?.("title") || "",
    typeof parent?.className === "string" ? parent.className : String(parent?.className || ""),
    compactText(node.innerText || node.textContent || "")
  ];
  return parts.map((part) => compactText(part)).filter(Boolean).join(" ").slice(0, 300);
}

function identifyActionIconKind(hints: string): ActionKind | null {
  const lowered = hints.toLowerCase();
  for (const kind of ["like", "comment", "favorite", "share"] as const) {
    if (actionMarkers(kind).some((marker) => lowered.includes(marker))) return kind;
  }
  if (/heart|like|赞|喜欢|点赞/.test(lowered)) return "like";
  if (/comment|评论|bubble/.test(lowered)) return "comment";
  if (/favorite|collect|star|收藏/.test(lowered)) return "favorite";
  if (/share|arrow|forward|分享/.test(lowered)) return "share";
  return null;
}

function getIconCandidateRejectionReason(
  node: HTMLElement,
  rect: { x: number; y: number; width: number; height: number },
  hints: string,
  viewportWidth: number,
  viewportHeight: number,
  activeVideoRect: ActionRailRectDiagnostic | null
): string | null {
  if (rect.width <= 0 || rect.height <= 0) return "icon_rect_not_visible";
  if (rect.width > 120 || rect.height > 120) return "icon_rect_too_large";
  if (viewportHeight > 0 && rect.y + rect.height / 2 > viewportHeight - 120) return "bottom_player_controls";
  if (hasVideoCardAncestor(node)) return "inside_video_card_anchor";
  if (containsHardExcludedText(hints)) return "hard_excluded_icon_text";
  if (/(follow|avatar|profile|music|listen|关注|头像|作者|音乐|听抖音)/i.test(hints)) return "non_action_rail_icon";
  const centerX = rect.x + rect.width / 2;
  if (activeVideoRect) {
    const minX = activeVideoRect.x + activeVideoRect.width * 0.72;
    const maxX = activeVideoRect.x + activeVideoRect.width + 260;
    if (centerX < minX || centerX > maxX) return "outside_active_video_right_rail";
  } else if (viewportWidth > 0 && centerX < viewportWidth * 0.55) return "outside_viewport_right_rail";
  if (!looksLikeRailIconCandidate(node) && !identifyActionIconKind(hints)) return "not_icon_like";
  return null;
}

function selectActionMetric(candidates: ActionBlockCandidate[], kind: ActionKind, claimedBlocks: Set<string>): ActionMetricSelection {
  const semanticMatches = candidates
    .filter((candidate) => candidate.semantic_kind === kind)
    .sort((left, right) => left.blockElements.length - right.blockElements.length);
  const valuedSemanticMatches = semanticMatches.filter((candidate) => candidate.value !== null);
  if (semanticMatches.length && !valuedSemanticMatches.length) {
    const zeroCandidate = semanticMatches.find((candidate) => parseRailMetricValue(kind, candidate.metricText) === 0);
    if (zeroCandidate) {
      const signature = blockSignature(zeroCandidate);
      if (!claimedBlocks.has(signature)) {
        claimedBlocks.add(signature);
        return {
          value: 0,
          text: zeroCandidate.metricText,
          block_text: zeroCandidate.blockText,
          confidence: "high",
          rejected_reason: null,
          source: "dom_zero_sentinel",
          node_descriptor: candidateSignature(zeroCandidate)
        };
      }
    }
    return {
      value: null,
      text: semanticMatches[0]?.metricText ?? null,
      block_text: semanticMatches[0]?.blockText ?? null,
      confidence: "low",
      rejected_reason: "metric_text_missing",
      source: null,
      node_descriptor: semanticMatches[0] ? candidateSignature(semanticMatches[0]) : null
    };
  }
  if (valuedSemanticMatches.length) {
    const distinctKeys = new Set(valuedSemanticMatches.map((candidate) => candidateSignature(candidate)));
    if (distinctKeys.size > 1) {
      return {
        value: null,
        text: null,
        block_text: valuedSemanticMatches[0]?.blockText ?? null,
        confidence: "low",
        rejected_reason: "ambiguous_multiple_action_blocks",
        source: null,
        node_descriptor: valuedSemanticMatches[0] ? candidateSignature(valuedSemanticMatches[0]) : null
      };
    }
    const selected = valuedSemanticMatches[0]!;
    const signature = blockSignature(selected);
    if (claimedBlocks.has(signature)) {
      return {
        value: null,
        text: selected.metricText,
        block_text: selected.blockText,
        confidence: "low",
        rejected_reason: "shared_action_block_rejected",
        source: null,
        node_descriptor: candidateSignature(selected)
      };
    }
    claimedBlocks.add(signature);
    return {
      value: selected.value,
      text: selected.metricText,
      block_text: selected.blockText,
      confidence: selected.confidence,
      rejected_reason: null,
      source: "dom_detail_modal",
      node_descriptor: candidateSignature(selected)
    };
  }

  const orderedCandidates = candidates
    .filter(
      (candidate) =>
        candidate.value !== null &&
        candidate.semantic_kind === null &&
        !claimedBlocks.has(blockSignature(candidate)) &&
        isLikelyActionRailCandidate(candidate)
    )
    .sort((left, right) => left.order_index - right.order_index);
  const fallback = orderedCandidates[0];
  if (!fallback) {
    return {
      value: null,
      text: null,
      block_text: null,
      confidence: "low",
      rejected_reason: "action_block_not_found",
      source: null,
      node_descriptor: null
    };
  }
  const fallbackSignature = blockSignature(fallback);
  claimedBlocks.add(fallbackSignature);
  return {
    value: fallback.value,
    text: fallback.metricText,
    block_text: fallback.blockText,
    confidence: "low",
    rejected_reason: null,
    source: "dom_detail_modal",
    node_descriptor: `${candidateSignature(fallback)}:vertical_order_fallback`
  };
}

function findProfileCardLikeMetric(document: Document, awemeId: string): ActionMetricSelection {
  const anchor = findProfileGridAnchorForAwemeId(document, awemeId);
  if (!anchor) {
    return { value: null, text: null, block_text: null, confidence: "low", rejected_reason: "profile_card_not_found", source: null, node_descriptor: null };
  }
  const firstLine = firstNonEmptyLine(anchor.innerText || anchor.textContent || "");
  if (!firstLine) {
    return { value: null, text: null, block_text: compactText(anchor.innerText || anchor.textContent || ""), confidence: "low", rejected_reason: "profile_card_like_missing", source: null, node_descriptor: null };
  }
  const parsedValue = parseProfileCardLikeValue(firstLine);
  if (parsedValue === null) {
    return {
      value: null,
      text: firstLine,
      block_text: compactText(anchor.innerText || anchor.textContent || ""),
      confidence: "low",
      rejected_reason: "profile_card_like_rejected",
      source: null,
      node_descriptor: `profile_card:${awemeId}:${firstLine}`
    };
  }
  return {
    value: parsedValue,
    text: firstLine,
    block_text: compactText(anchor.innerText || anchor.textContent || ""),
    confidence: "high",
    rejected_reason: null,
    source: "dom_profile_card_fallback",
    node_descriptor: `profile_card:${awemeId}:${firstLine}`
  };
}

function clickNextControl(document: Document): boolean {
  const selectors = [
    'button[aria-label*="下一个"]',
    'button[aria-label*="next"]',
    '[role="button"][aria-label*="下一个"]',
    '[role="button"][aria-label*="next"]',
    'button[class*="next"]',
    '[role="button"][class*="next"]'
  ];
  for (const selector of selectors) {
    const element = document.querySelector<HTMLElement>(selector);
    if (element && isVisible(element)) {
      element.click();
      return true;
    }
  }
  return false;
}

function triggerNextKeyboardNavigation(document: Document): void {
  document.dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowDown", bubbles: true }));
  document.dispatchEvent(new KeyboardEvent("keydown", { key: "PageDown", bubbles: true }));
}

function inferActionKinds(node: HTMLElement): ActionKind[] {
  const text = compactText(node.innerText || node.textContent || "");
  const markerText = [node.getAttribute("aria-label") || "", node.getAttribute("title") || "", node.className || "", text].join(" ").toLowerCase();
  const kinds = (["like", "comment", "favorite", "share"] as const).filter((kind) => actionMarkers(kind).some((marker) => markerText.includes(marker)));
  return kinds;
}

function isLikelyActionRailCandidate(candidate: ActionBlockCandidate): boolean {
  const lowered = (candidate.blockText ?? "").toLowerCase();
  if (candidate.marker.tagName?.toLowerCase?.() === "a") {
    const href = (candidate.marker as HTMLAnchorElement).href ?? candidate.marker.getAttribute?.("href") ?? "";
    if (href.includes("/video/")) return false;
  }
  if (/(follow|music|listen|sound|avatar|profile|å…³æ³¨|éŸ³ä¹|ä½œè€…)/i.test(lowered)) return false;
  return true;
}

function detectRailXBand(iconNodes: HTMLElement[], viewportWidth: number, viewportHeight: number, activeVideoRect?: ActionRailRectDiagnostic | null): ActionRailXBandDiagnostic | null {
  if (viewportWidth <= 0 && !activeVideoRect) return null;
  const geometryBand = activeVideoRect && activeVideoRect.width > 0 ? { min: Math.round(activeVideoRect.x + activeVideoRect.width - 40), max: Math.round(activeVideoRect.x + activeVideoRect.width + 180), source: "active_video_geometry" as const } : null;
  const railIcons = iconNodes
    .map((node) => normalizeRect(node.getBoundingClientRect()))
    .filter((rect) => rect.width > 0 && rect.height > 0 && isInActionRailYRange(rect, viewportHeight));
  const geometryIcons = geometryBand ? railIcons.filter((rect) => rect.x + rect.width / 2 >= geometryBand.min && rect.x + rect.width / 2 <= geometryBand.max) : [];
  const rightRailIcons = railIcons.filter((rect) => viewportWidth > 0 && rect.x + rect.width / 2 >= viewportWidth * 0.72);
  const selectedIcons = geometryIcons.length >= 2 ? geometryIcons : rightRailIcons;
  if (selectedIcons.length >= 2) {
    const centers = selectedIcons.map((rect) => rect.x + rect.width / 2).sort((left, right) => left - right);
    const median = centers[Math.floor(centers.length / 2)] ?? (geometryBand ? (geometryBand.min + geometryBand.max) / 2 : viewportWidth * 0.875);
    return { min: Math.max(0, Math.round(median - 80)), max: Math.round(median + 80), source: "icon_candidates" };
  }
  if (geometryBand) return geometryBand;
  return viewportWidth > 0 ? { min: Math.round(viewportWidth * 0.85), max: viewportWidth, source: "viewport_fallback" } : null;
}

function isInActionRailYRange(rect: { x: number; y: number; width: number; height: number }, viewportHeight: number): boolean {
  const centerY = rect.y + rect.height / 2;
  if (viewportHeight > 0 && centerY < viewportHeight * 0.08) return false;
  if (viewportHeight > 0 && centerY > viewportHeight * 0.88) return false;
  return true;
}

function roundRect(rect: { x: number; y: number; width: number; height: number }): { x: number; y: number; width: number; height: number } {
  return {
    x: Math.round(rect.x || 0),
    y: Math.round(rect.y || 0),
    width: Math.round(rect.width || 0),
    height: Math.round(rect.height || 0)
  };
}

function normalizeRect(rect: { x?: number; y?: number; width?: number; height?: number; left?: number; top?: number }): { x: number; y: number; width: number; height: number } {
  return {
    x: Number(rect.x ?? rect.left ?? 0),
    y: Number(rect.y ?? rect.top ?? 0),
    width: Number(rect.width ?? 0),
    height: Number(rect.height ?? 0)
  };
}

function roundRectWithFallback(rect: { x?: number; y?: number; width?: number; height?: number; left?: number; top?: number }): ActionRailRectDiagnostic {
  return roundRect(normalizeRect(rect));
}

function candidateKey(candidate: CompactCountCandidate): string {
  return `${candidate.text}|${Math.round(candidate.rect.x)}|${Math.round(candidate.rect.y)}`;
}

function clusterCompactCountCandidates(candidates: CompactCountCandidate[], activeVideoRect: ActionRailRectDiagnostic | null, viewportWidth: number, viewportHeight: number): ScoredCompactCountCluster[] {
  const sorted = candidates.slice().sort((left, right) => (left.rect.x + left.rect.width / 2) - (right.rect.x + right.rect.width / 2));
  const groups: CompactCountCandidate[][] = [];
  for (const candidate of sorted) {
    const centerX = candidate.rect.x + candidate.rect.width / 2;
    const group = groups.find((items) => Math.abs(groupCenterX(items) - centerX) <= 50);
    if (group) group.push(candidate);
    else groups.push([candidate]);
  }
  return groups
    .map((group, index) => scoreCompactCountCluster(`cluster_${index + 1}`, group, activeVideoRect, viewportWidth, viewportHeight))
    .sort((left, right) => right.score - left.score);
}

function scoreCompactCountCluster(id: string, group: CompactCountCandidate[], activeVideoRect: ActionRailRectDiagnostic | null, viewportWidth: number, viewportHeight: number): ScoredCompactCountCluster {
  const ordered = group.slice().sort((left, right) => left.rect.y - right.rect.y);
  const centerX = groupCenterX(ordered);
  const centersY = ordered.map((candidate) => candidate.rect.y + candidate.rect.height / 2);
  const gaps = centersY.slice(1).map((value, index) => value - (centersY[index] ?? value));
  const regularGaps = gaps.filter((gap) => gap >= 45 && gap <= 180).length;
  const videoRight = activeVideoRect ? activeVideoRect.x + activeVideoRect.width : viewportWidth;
  const distanceFromVideoRight = Math.abs(centerX - videoRight);
  const rightOfVideo = activeVideoRect ? centerX >= activeVideoRect.x + activeVideoRect.width * 0.72 : viewportWidth > 0 && centerX >= viewportWidth * 0.45;
  const inModalSideArea = activeVideoRect ? centerX >= activeVideoRect.x && centerX <= activeVideoRect.x + activeVideoRect.width + 220 : true;
  let score = 0;
  score += Math.min(4, ordered.length) * 100;
  if (ordered.length === 4) score += 100;
  if (ordered.length === 3) score += 60;
  if (ordered.length >= 1) score += 20;
  score += regularGaps * 35;
  if (rightOfVideo) score += 80;
  if (inModalSideArea) score += 60;
  if (activeVideoRect) score += Math.max(0, 120 - Math.min(120, distanceFromVideoRight)) / 2;
  if (viewportHeight > 0 && ordered.every((candidate) => isInActionRailYRange(candidate.rect, viewportHeight))) score += 50;
  const reason = ordered.length >= 3 && rightOfVideo && inModalSideArea ? null : ordered.length >= 1 && rightOfVideo && inModalSideArea && score >= 210 ? null : "cluster_score_below_threshold";
  const xBand = { min: Math.max(0, Math.round(centerX - 60)), max: Math.round(centerX + 60), source: "compact_count_cluster" as const };
  return { id, centerX, candidates: ordered.slice(0, 4), score: Math.round(score), reason, xBand };
}

function groupCenterX(group: CompactCountCandidate[]): number {
  if (!group.length) return 0;
  return group.reduce((sum, candidate) => sum + candidate.rect.x + candidate.rect.width / 2, 0) / group.length;
}

function clusterDiagnostic(cluster: ScoredCompactCountCluster, selected: ScoredCompactCountCluster | null): ActionRailCompactCountClusterDiagnostic {
  return {
    id: cluster.id,
    center_x: Math.round(cluster.centerX),
    candidate_count: cluster.candidates.length,
    y_values: cluster.candidates.map((candidate) => Math.round(candidate.rect.y + candidate.rect.height / 2)),
    score: cluster.score,
    accepted: selected?.id === cluster.id,
    reason: selected?.id === cluster.id ? null : cluster.reason ?? "lower_scored_cluster",
    x_band: cluster.xBand,
    candidates: cluster.candidates.map((candidate) => ({ visible_text: candidate.text || null, value: candidate.value, rect: roundRect(candidate.rect), accepted: selected?.id === cluster.id, reason: selected?.id === cluster.id ? null : "lower_scored_cluster" }))
  };
}

function buildCandidatesFromCluster(cluster: ScoredCompactCountCluster | null, iconNodes: HTMLElement[]): ActionBlockCandidate[] {
  if (!cluster) return [];
  const acceptedKinds = ["like", "comment", "favorite", "share"] as const;
  return cluster.candidates.map((candidate, index) => {
    const iconNode = findNearestIconAbove(candidate.node, iconNodes);
    const blockElements = iconNode ? [iconNode, candidate.node] : [candidate.node];
    const rect = iconNode ? mergeRects([normalizeRect(iconNode.getBoundingClientRect()), candidate.rect]) : candidate.rect;
    const blockText = summarizeBlockText(blockElements);
    const iconKinds = iconNode ? inferActionKinds(iconNode) : [];
    return {
      semantic_kind: iconKinds.length === 1 ? iconKinds[0]! : acceptedKinds[index] ?? null,
      icon_kind: iconKinds.length === 1 ? iconKinds[0]! : null,
      countNode: candidate.node,
      marker: iconNode ?? candidate.node,
      blockElements,
      blockText,
      metricText: candidate.text,
      value: candidate.value,
      confidence: iconKinds.length === 1 ? "high" : "low",
      order_index: index,
      block_descriptor: `${Math.round(rect.y)}:${candidate.text}:${blockText ?? ""}`,
      rect,
      hints: iconNode ? summarizeActionHints(iconNode) : `adaptive_compact_count_cluster:${cluster.id}`
    } satisfies ActionBlockCandidate;
  });
}

function collectVisibleTextNodeRects(
  document: Document,
  viewportWidth: number,
  viewportHeight: number,
  activeVideoRect: ActionRailRectDiagnostic | null,
  rejected: ActionRailRejectedCandidateDiagnostic[]
): CompactCountCandidate[] {
  const textRects: TextNodeRectCandidate[] = [];
  const root = document.body ?? document.documentElement;
  const walkerFactory = document.createTreeWalker?.bind(document);
  const rangeFactory = document.createRange?.bind(document);
  if (!root || !walkerFactory || !rangeFactory) return [];
  const showText = typeof NodeFilter !== "undefined" ? NodeFilter.SHOW_TEXT : 4;
  const walker = walkerFactory(root, showText);
  let current = walker.nextNode();
  while (current) {
    const text = compactText(current.textContent || "");
    const nearestElement = nearestElementForNode(current);
    if (!text || !nearestElement) {
      current = walker.nextNode();
      continue;
    }
    const compactCount = extractCompactCountText(text);
    if (!compactCount) {
      current = walker.nextNode();
      continue;
    }
    const range = rangeFactory();
    try {
      range.selectNodeContents(current);
      const rect = normalizeRect(range.getBoundingClientRect());
      if (rect.width <= 0 || rect.height <= 0) {
        rejected.push({ visible_text: compactCount, reason: "text_node_rect_not_visible", rect: roundRect(rect) });
        current = walker.nextNode();
        continue;
      }
      textRects.push({
        text: compactCount,
        rect,
        nearestElement,
        nearestTag: nearestElement.tagName?.toLowerCase?.() ?? null,
        nearestClass: typeof nearestElement.className === "string" ? nearestElement.className : String(nearestElement.className || "") || null,
        nearestAriaLabel: nearestElement.getAttribute?.("aria-label") ?? null,
        nearestTitle: nearestElement.getAttribute?.("title") ?? null
      });
    } finally {
      range.detach?.();
    }
    current = walker.nextNode();
  }
  return textRects.map((candidate) => {
    const rejectionReason = getTextNodeCandidateRejectionReason(candidate, viewportWidth, viewportHeight, activeVideoRect);
    if (rejectionReason) rejected.push({ visible_text: candidate.text, reason: rejectionReason, rect: roundRect(candidate.rect) });
    return {
      node: candidate.nearestElement,
      text: candidate.text,
      value: parseMetricValue(candidate.text),
      rect: candidate.rect,
      rejectionReason,
      source: "text_node",
      nearestTag: candidate.nearestTag,
      nearestClass: candidate.nearestClass,
      nearestAriaLabel: candidate.nearestAriaLabel,
      nearestTitle: candidate.nearestTitle
    } satisfies CompactCountCandidate;
  });
}

function nearestElementForNode(node: Node): HTMLElement | null {
  let current: Node | null = node.parentNode;
  while (current) {
    if (isElementLike(current)) return current;
    current = current.parentNode;
  }
  return null;
}

function getTextNodeCandidateRejectionReason(
  candidate: TextNodeRectCandidate,
  viewportWidth: number,
  viewportHeight: number,
  activeVideoRect: ActionRailRectDiagnostic | null
): string | null {
  const contextText = textNodeCandidateContext(candidate);
  if (hasVideoCardAncestor(candidate.nearestElement)) return "inside_video_card_anchor";
  if (isInsideSearchBox(candidate.nearestElement)) return "inside_search_box";
  if (containsHardExcludedText(contextText)) return "hard_excluded_number_text";
  if (candidate.rect.width > 100 || candidate.rect.height > 40) return "count_rect_too_large";
  if (parseMetricValue(candidate.text) === null) return "count_text_not_numeric";
  if (looksLikeTimelineText(candidate.text) || containsTimelineText(contextText)) return "bottom_player_time";
  if (looksLikeDateLikeDecimal(candidate.text)) return "date_like_decimal_text";
  if (viewportHeight > 0 && candidate.rect.y + candidate.rect.height / 2 > viewportHeight - 120) return "bottom_player_controls";
  if (!isInActionRailYRange(candidate.rect, viewportHeight)) return "bottom_player_time";
  if (isInLeftCaptionArea(candidate.rect, viewportWidth, activeVideoRect)) return "left_caption_area";
  return null;
}

function looksLikeDateLikeDecimal(text: string): boolean {
  return /^\d{1,2}\.\d{1,2}$/.test(text);
}

function isInLeftCaptionArea(rect: { x: number; y: number; width: number; height: number }, viewportWidth: number, activeVideoRect: ActionRailRectDiagnostic | null): boolean {
  const centerX = rect.x + rect.width / 2;
  if (activeVideoRect) return centerX < activeVideoRect.x + activeVideoRect.width * 0.45;
  return viewportWidth > 0 && centerX < viewportWidth * 0.35;
}

function mergeElementRects(elements: HTMLElement[]): { x: number; y: number; width: number; height: number } {
  const rects = elements.map((element) => element.getBoundingClientRect()).filter((rect) => rect.width > 0 && rect.height > 0);
  if (!rects.length) return { x: 0, y: 0, width: 0, height: 0 };
  const left = Math.min(...rects.map((rect) => rect.x));
  const top = Math.min(...rects.map((rect) => rect.y));
  const right = Math.max(...rects.map((rect) => rect.x + rect.width));
  const bottom = Math.max(...rects.map((rect) => rect.y + rect.height));
  return { x: left, y: top, width: Math.max(0, right - left), height: Math.max(0, bottom - top) };
}

function mergeRects(rects: Array<{ x: number; y: number; width: number; height: number }>): { x: number; y: number; width: number; height: number } {
  const visibleRects = rects.filter((rect) => rect.width > 0 && rect.height > 0);
  if (!visibleRects.length) return { x: 0, y: 0, width: 0, height: 0 };
  const left = Math.min(...visibleRects.map((rect) => rect.x));
  const top = Math.min(...visibleRects.map((rect) => rect.y));
  const right = Math.max(...visibleRects.map((rect) => rect.x + rect.width));
  const bottom = Math.max(...visibleRects.map((rect) => rect.y + rect.height));
  return { x: left, y: top, width: Math.max(0, right - left), height: Math.max(0, bottom - top) };
}

function summarizeActionHints(node: HTMLElement): string | null {
  const parts = [node.getAttribute("aria-label") || "", node.getAttribute("title") || "", node.className || ""]
    .map((value) => compactText(String(value || "")))
    .filter(Boolean);
  if (!parts.length) return null;
  return parts.join(" | ").slice(0, 200);
}

function hasCompactCountText(node: HTMLElement): boolean {
  const text = compactText(node.innerText || node.textContent || "");
  if (!text) return false;
  return Boolean(extractCompactCountText(text));
}

function looksLikeRailIconCandidate(node: HTMLElement): boolean {
  const rect = node.getBoundingClientRect();
  if (rect.width <= 0 || rect.height <= 0) return false;
  if (rect.width > 120 || rect.height > 120) return false;
  const hints = summarizeActionHints(node);
  if (hints) return true;
  const role = node.getAttribute("role") || "";
  return role.toLowerCase() === "button" || node.tagName?.toLowerCase?.() === "button";
}

function getCountNodeRejectionReason(
  node: HTMLElement,
  compactCount: string,
  rect: { x: number; y: number; width: number; height: number },
  viewportHeight: number
): string | null {
  if (hasVideoCardAncestor(node)) return "inside_video_card_anchor";
  if (rect.width > 100 || rect.height > 40) return "count_rect_too_large";
  const blockText = compactText(node.innerText || node.textContent || "");
  if (blockText.length > 12) return "candidate_text_too_long";
  if (containsRejectedCandidateText(blockText)) return "caption_or_card_text_detected";
  if (looksLikeTimelineText(blockText)) return "bottom_player_time";
  if (!isInActionRailYRange(rect, viewportHeight)) return "outside_action_rail_y_range";
  if (parseMetricValue(compactCount) === null) return "count_text_not_numeric";
  return null;
}

function hasVideoCardAncestor(node: HTMLElement): boolean {
  let current: HTMLElement | null = node;
  while (current) {
    const href = (current as HTMLAnchorElement).href ?? current.getAttribute?.("href") ?? "";
    if (href.includes("/video/")) return true;
    current = current.parentElement;
  }
  return false;
}

function looksLikeTimelineText(text: string): boolean {
  return /^\d{1,2}:\d{2}\s*\/\s*\d{1,2}:\d{2}(?::\d{2})?$/.test(text);
}

function textNodeCandidateContext(candidate: TextNodeRectCandidate): string {
  const ancestorTexts: string[] = [];
  let current: HTMLElement | null = candidate.nearestElement;
  for (let depth = 0; current && depth < 3; depth += 1) {
    ancestorTexts.push(compactText(current.innerText || current.textContent || ""));
    current = current.parentElement;
  }
  return [candidate.text, candidate.nearestClass, candidate.nearestAriaLabel, candidate.nearestTitle, ...ancestorTexts].filter(Boolean).join(" ");
}

function isInsideSearchBox(node: HTMLElement): boolean {
  let current: HTMLElement | null = node;
  while (current) {
    const text = compactText(current.innerText || current.textContent || "");
    const hints = [
      current.getAttribute?.("role") || "",
      current.getAttribute?.("aria-label") || "",
      current.getAttribute?.("title") || "",
      current.getAttribute?.("placeholder") || "",
      typeof current.className === "string" ? current.className : String(current.className || ""),
      text
    ].join(" ");
    if (/search|搜索|搜一搜|搜索框/i.test(hints)) return true;
    current = current.parentElement;
  }
  return false;
}

function containsHardExcludedText(text: string): boolean {
  if (!text) return false;
  return /#|豆瓣|纪录片|章节要点|关注|合集|播放进度|current\s*time|total\s*time|\d{1,2}:\d{2}\s*\/\s*\d{1,2}:\d{2}(?::\d{2})?/i.test(text);
}

function containsTimelineText(text: string): boolean {
  return /\d{1,2}:\d{2}\s*\/\s*\d{1,2}:\d{2}(?::\d{2})?/.test(text);
}

function containsRejectedCandidateText(text: string): boolean {
  if (!text) return false;
  return containsHardExcludedText(text) || /follow|听抖音|listen/i.test(text);
}

function findNearestIconAbove(countNode: HTMLElement, iconNodes: HTMLElement[]): HTMLElement | null {
  const countRect = countNode.getBoundingClientRect();
  const countCenterX = countRect.x + countRect.width / 2;
  let best: { node: HTMLElement; score: number } | null = null;
  for (const iconNode of iconNodes) {
    if (iconNode === countNode) continue;
    if (hasVideoCardAncestor(iconNode)) continue;
    const rect = iconNode.getBoundingClientRect();
    if (rect.width > 140 || rect.height > 140) continue;
    const iconCenterX = rect.x + rect.width / 2;
    const deltaX = Math.abs(iconCenterX - countCenterX);
    const deltaY = countRect.y - (rect.y + rect.height);
    if (deltaY < -4 || deltaY > 120) continue;
    if (deltaX > 60) continue;
    const score = deltaY * 10 + deltaX;
    if (!best || score < best.score) best = { node: iconNode, score };
  }
  return best?.node ?? null;
}

function buildActionBlockDiagnostics(
  candidates: ActionBlockCandidate[],
  assignedDescriptors: Record<ActionKind, string | null>
): ActionRailBlockDiagnostic[] {
  const assignmentByDescriptor = new Map<string, ActionKind>();
  for (const [kind, descriptor] of Object.entries(assignedDescriptors) as [ActionKind, string | null][]) {
    if (!descriptor) continue;
    assignmentByDescriptor.set(descriptor.split(":vertical_order_fallback")[0]!, kind);
  }
  return candidates.map((candidate, index) => ({
    index,
    rect: {
      x: Math.round(candidate.rect.x),
      y: Math.round(candidate.rect.y),
      width: Math.round(candidate.rect.width),
      height: Math.round(candidate.rect.height)
    },
    visible_text: candidate.blockText,
    aria_title_class_hints: candidate.hints,
    assigned_metric: assignmentByDescriptor.get(candidateSignature(candidate)) ?? null,
    count_text: candidate.metricText,
    count_value: candidate.value
  }));
}

function resolveActionBlockElements(node: HTMLElement): HTMLElement[] {
  const elements: HTMLElement[] = [];
  appendUniqueElement(elements, node);
  for (const sibling of relatedElements(node)) appendUniqueElement(elements, sibling);
  return elements.filter((element) => isVisible(element));
}

function relatedElements(node: HTMLElement): HTMLElement[] {
  const parent = node.parentElement;
  const related: HTMLElement[] = [];
  const parentWithChildren = parent as unknown as { children?: unknown[] | HTMLCollection } | null;
  if (parentWithChildren && typeof parentWithChildren.children !== "undefined") {
    for (const child of Array.from(parentWithChildren.children ?? [])) {
      if (isElementLike(child)) related.push(child);
    }
  }
  if (isElementLike(node.previousElementSibling)) related.push(node.previousElementSibling);
  if (isElementLike(node.nextElementSibling)) related.push(node.nextElementSibling);
  return related;
}

function appendUniqueElement(target: HTMLElement[], element: HTMLElement): void {
  if (!target.includes(element)) target.push(element);
}

function extractMetricTextFromActionBlock(node: HTMLElement, elements: HTMLElement[]): string | null {
  const uniqueTexts = new Set<string>();
  const ordered = [...elements.filter((element) => element !== node), node];
  for (const element of ordered) {
    const text = compactText(element.innerText || element.textContent || "");
    const metricText = extractStructuredMetricText(text);
    if (metricText) uniqueTexts.add(metricText);
  }
  if (uniqueTexts.size === 1) return Array.from(uniqueTexts)[0] ?? null;
  return null;
}

function summarizeBlockText(elements: HTMLElement[]): string | null {
  const texts = elements.map((element) => compactText(element.innerText || element.textContent || "")).filter(Boolean);
  const unique = Array.from(new Set(texts));
  if (!unique.length) return null;
  return unique.join(" | ").slice(0, 300);
}

function candidateSignature(candidate: ActionBlockCandidate): string {
  return `${candidate.semantic_kind ?? "order"}|${candidate.metricText ?? ""}|${candidate.blockText ?? ""}|${candidate.block_descriptor}`;
}

function blockSignature(candidate: ActionBlockCandidate): string {
  return `${candidate.metricText ?? ""}|${candidate.blockText ?? ""}`;
}

function summarizeExtractionWarning(rejectedMetricReasons: Record<string, string>): string | null {
  const entries = Object.entries(rejectedMetricReasons);
  if (!entries.length) return null;
  return entries.map(([field, reason]) => `${field}:${reason}`).join("; ");
}

function summarizeHarvestedItem(item: FullModalHarvestItemPayload, status: string, index?: number | null): FullModalHarvestLastItemSummary {
  return {
    index: index ?? null,
    aweme_id: item.aweme_id,
    duration_seconds: item.raw_dom_detail_metrics.duration_seconds ?? null,
    duration_text: item.raw_dom_detail_metrics.duration_text ?? null,
    like_count: item.raw_dom_detail_metrics.like_count ?? null,
    like_count_source: item.raw_dom_detail_metrics.like_count_source ?? null,
    comment_count: item.raw_dom_detail_metrics.comment_count ?? null,
    favorite_count: item.raw_dom_detail_metrics.favorite_count ?? null,
    share_count: item.raw_dom_detail_metrics.share_count ?? null,
    posted_text: item.raw_dom_detail_metrics.posted_text ?? null,
    extraction_warning: item.raw_dom_detail_metrics.extraction_warning ?? null,
    status,
    target_aweme_id: item.target_aweme_id ?? null,
    extracted_aweme_id: item.extracted_aweme_id ?? item.aweme_id ?? null,
    data_integrity_status: item.data_integrity_status ?? "ok",
    data_integrity_reason: item.data_integrity_reason ?? null,
    metric_signature: item.metric_signature ?? null,
    duplicate_signature_warning: item.duplicate_signature_warning ?? null
  };
}

function probeFromHarvestedItem(item: FullModalHarvestItemPayload): FullModalHarvestProbeResult {
  const actionBlocksMissingReason = item.raw_dom_detail_metrics.action_blocks_missing_reason ?? null;
  const hasCompleteActionMetrics =
    item.raw_dom_detail_metrics.like_count != null &&
    item.raw_dom_detail_metrics.comment_count != null &&
    item.raw_dom_detail_metrics.favorite_count != null &&
    item.raw_dom_detail_metrics.share_count != null;
  const readyForFullHarvest = item.aweme_id != null && item.raw_dom_detail_metrics.duration_seconds != null && hasCompleteActionMetrics;
  const probeStatus = !readyForFullHarvest ? "WARN" : isCalibratedPointPassSource(item.raw_dom_detail_metrics.source_used) ? "PASS" : "WARN";
  return {
    aweme_id: item.aweme_id,
    calibration_status: "calibrated",
    calibrated_viewport:
      item.raw_dom_detail_metrics.viewport_width != null && item.raw_dom_detail_metrics.viewport_height != null
        ? { width: item.raw_dom_detail_metrics.viewport_width, height: item.raw_dom_detail_metrics.viewport_height }
        : null,
    current_viewport:
      item.raw_dom_detail_metrics.viewport_width != null && item.raw_dom_detail_metrics.viewport_height != null
        ? { width: item.raw_dom_detail_metrics.viewport_width, height: item.raw_dom_detail_metrics.viewport_height }
        : null,
    source_priority_used: item.raw_dom_detail_metrics.source_priority_used ?? "missing",
    source_used: item.raw_dom_detail_metrics.source_used ?? null,
    exact_aweme_runtime_found: false,
    exact_aweme_source: "none",
    raw_aweme_keys: null,
    fallback_used: null,
    rejected_reason: item.raw_dom_detail_metrics.rejected_reason ?? null,
    duration_seconds: item.raw_dom_detail_metrics.duration_seconds ?? null,
    duration_text: item.raw_dom_detail_metrics.duration_text ?? null,
    like_count: item.raw_dom_detail_metrics.like_count ?? null,
    comment_count: item.raw_dom_detail_metrics.comment_count ?? null,
    favorite_count: item.raw_dom_detail_metrics.favorite_count ?? null,
    share_count: item.raw_dom_detail_metrics.share_count ?? null,
    posted_text: item.raw_dom_detail_metrics.posted_text ?? null,
    point_results: item.raw_dom_detail_metrics.point_results ?? null,
    confidence_by_field: item.raw_dom_detail_metrics.metric_confidence_by_field ?? null,
    rejected_metric_reasons: item.raw_dom_detail_metrics.rejected_metric_reasons ?? null,
    action_blocks_found: item.raw_dom_detail_metrics.action_blocks_found ?? 0,
    modal_action_blocks_found: item.raw_dom_detail_metrics.modal_action_blocks_found ?? null,
    action_block_diagnostics: item.raw_dom_detail_metrics.action_block_diagnostics ?? null,
    accepted_action_blocks: item.raw_dom_detail_metrics.action_block_diagnostics ?? null,
    rejected_candidates_count: item.raw_dom_detail_metrics.rejected_candidates_count ?? null,
    rejected_candidate_examples: item.raw_dom_detail_metrics.rejected_candidate_examples ?? null,
    rail_x_band: item.raw_dom_detail_metrics.rail_x_band ?? null,
    computed_rail_x_band: item.raw_dom_detail_metrics.computed_rail_x_band ?? null,
    viewport_width: item.raw_dom_detail_metrics.viewport_width ?? null,
    viewport_height: item.raw_dom_detail_metrics.viewport_height ?? null,
    active_video_rect: item.raw_dom_detail_metrics.active_video_rect ?? null,
    modal_candidate_rect: item.raw_dom_detail_metrics.modal_candidate_rect ?? null,
    compact_count_candidates: item.raw_dom_detail_metrics.compact_count_candidates ?? null,
    compact_text_node_candidates_count: item.raw_dom_detail_metrics.compact_text_node_candidates_count ?? null,
    compact_count_clusters: item.raw_dom_detail_metrics.compact_count_clusters ?? null,
    selected_compact_count_cluster: item.raw_dom_detail_metrics.selected_compact_count_cluster ?? null,
    selected_cluster_texts: item.raw_dom_detail_metrics.selected_cluster_texts ?? null,
    selected_cluster_rects: item.raw_dom_detail_metrics.selected_cluster_rects ?? null,
    action_blocks_missing_reason: actionBlocksMissingReason,
    extraction_mode: item.raw_dom_detail_metrics.extraction_mode ?? null,
    combined_text_segment: item.raw_dom_detail_metrics.combined_text_segment ?? null,
    combined_count_tokens: item.raw_dom_detail_metrics.combined_count_tokens ?? null,
    extraction_warning: item.raw_dom_detail_metrics.extraction_warning ?? null,
    warning_reason: item.raw_dom_detail_metrics.warning_reason ?? null,
    probe_status: probeStatus,
    ready_for_full_harvest: readyForFullHarvest,
    blocking_reason:
      item.aweme_id == null
        ? "current_aweme_id_missing"
        : item.raw_dom_detail_metrics.duration_seconds == null
          ? "duration_seconds_missing"
          : !hasCompleteActionMetrics
            ? `action_blocks_missing:${actionBlocksMissingReason ?? "no_reliable_calibrated_counts"}`
            : null
  };
}

function findProfileGridAnchorForAwemeId(document: Document, awemeId: string): HTMLAnchorElement | null {
  const selector = `a[href*="/video/${awemeId}"]`;
  const direct = document.querySelector<HTMLAnchorElement>(selector);
  if (direct) return direct;
  const anchors = Array.from(document.querySelectorAll<HTMLAnchorElement>('a[href*="/video/"]'));
  for (const anchor of anchors) {
    const href = anchor.href ?? anchor.getAttribute?.("href") ?? "";
    if (href.includes(`/video/${awemeId}`)) return anchor;
  }
  return null;
}

export function parseCombinedModalActionText(text: string): CombinedModalActionTextResult | null {
  const markerIndex = text.indexOf("连播");
  if (markerIndex < 0) return null;
  const afterMarker = text.slice(markerIndex + "连播".length);
  const stopMatches = ["听抖音", "@", "作者", "发布", "发表于", "·"].map((marker) => afterMarker.indexOf(marker)).filter((index) => index >= 0);
  const postedDateMatch = /\d{1,2}月\d{1,2}日/.exec(afterMarker);
  if (postedDateMatch?.index != null) stopMatches.push(postedDateMatch.index);
  const stopIndex = stopMatches.length ? Math.min(...stopMatches) : afterMarker.length;
  const combinedTextSegment = compactText(afterMarker.slice(0, stopIndex));
  if (!combinedTextSegment) return null;
  const tokens = combinedTextSegment.match(/\d+(?:\.\d+)?(?:万|[wWkK])?/g) ?? [];
  if (tokens.length !== 4) return null;
  const values = tokens.map((token) => parseMetricValue(token));
  if (values.some((value) => value === null)) return null;
  return {
    extraction_source: "combined_modal_text_fallback",
    like_count: values[0] as number,
    comment_count: values[1] as number,
    favorite_count: values[2] as number,
    share_count: values[3] as number,
    combined_text_segment: combinedTextSegment,
    combined_count_tokens: tokens,
    confidence: "high"
  };
}

function extractCombinedModalActionText(document: Document): CombinedModalActionTextResult | null {
  const texts = [document.body?.innerText ?? ""];
  for (const node of Array.from(document.querySelectorAll<HTMLElement>("div, span, p"))) {
    const text = node.innerText || node.textContent || "";
    if (text.includes("连播")) texts.push(text);
  }
  for (const text of texts) {
    const parsed = parseCombinedModalActionText(text);
    if (parsed) return parsed;
  }
  return null;
}

function firstNonEmptyLine(value: string): string | null {
  for (const line of value.split(/\r?\n/)) {
    const compact = compactText(line);
    if (compact) return compact;
  }
  return null;
}

function parseProfileCardLikeValue(value: string): number | null {
  const trimmed = value.trim();
  if (!trimmed) return null;
  if (/豆瓣|rating|评分/i.test(trimmed)) return null;
  if (/^\d+\.\d+$/.test(trimmed)) return null;
  if (/^\d+\.\d+\/\d+$/.test(trimmed)) return null;
  if (/[^\d.wWkKmM万]/.test(trimmed)) return null;
  if (/[万wWkKmM]/.test(trimmed)) return parseMetricValue(trimmed);
  if (!/^\d+$/.test(trimmed)) return null;
  return parseMetricValue(trimmed);
}

function extractStructuredMetricText(text: string): string | null {
  if (!text) return null;
  const match = /(^|\s)(\d+(?:\.\d+)?)([wWkKmM万]?)(?=\s|$)/.exec(text);
  if (!match?.[2]) return null;
  return `${match[2]}${match[3] ?? ""}`;
}

function extractCompactCountText(text: string): string | null {
  const compact = compactText(text);
  if (!compact) return null;
  if (compact.length > 12) return null;
  if (containsRejectedCandidateText(compact)) return null;
  if (looksLikeTimelineText(compact)) return null;
  if (!/^\d+(?:\.\d+)?[wWkKmM万]?$/.test(compact)) return null;
  return compact;
}

function parseRailMetricValue(kind: ActionKind | null, raw: string | null): number | null {
  const numeric = parseMetricValue(raw);
  if (numeric !== null) return numeric;
  if (kind === "like" || kind === "favorite") return null;
  if (kind === "comment") return parseDouyinEngagementCount("comment", raw);
  if (kind === "share") return parseDouyinEngagementCount("share", raw, { shareIconContext: true });
  return parseDouyinEngagementCount("comment", raw) ?? parseDouyinEngagementCount("share", raw, { shareIconContext: true });
}

function extractRightRailMetricText(rawText: string): string | null {
  const compact = compactText(rawText);
  const numeric = extractExactCompactCountText(compact);
  if (numeric) return numeric;
  const comment = parseDouyinEngagementText("comment", compact);
  if (comment.kind === "zero_sentinel") return comment.rawText;
  const share = parseDouyinEngagementText("share", compact, { shareIconContext: true });
  if (share.kind === "zero_sentinel") return share.rawText;
  return null;
}

function parseMetricValue(raw: string | null): number | null {
  if (!raw) return null;
  const text = raw.trim();
  if (!/^\d+(?:\.\d+)?[wWkKmM万]?$/.test(text)) return null;
  const suffix = text.slice(-1);
  const hasSuffix = /[wWkKmM万]/.test(suffix);
  const numeric = Number(hasSuffix ? text.slice(0, -1) : text);
  if (!Number.isFinite(numeric) || numeric < 0) return null;
  const multiplier = suffix === "万" || suffix.toLowerCase() === "w" ? 10_000 : suffix.toLowerCase() === "k" ? 1_000 : suffix.toLowerCase() === "m" ? 1_000_000 : 1;
  return Math.round(numeric * multiplier);
}

function actionMarkers(kind: "like" | "comment" | "favorite" | "share"): string[] {
  if (kind === "like") return ["赞", "like", "heart", "digg"];
  if (kind === "comment") return ["评论", "comment", "message"];
  if (kind === "favorite") return ["收藏", "favorite", "collect", "star"];
  return ["分享", "share", "forward"];
}

function isVisible(element: HTMLElement): boolean {
  const style = window.getComputedStyle(element);
  if (style.display === "none" || style.visibility === "hidden" || Number(style.opacity || "1") === 0) return false;
  const rect = element.getBoundingClientRect();
  return rect.width > 1 && rect.height > 1;
}

function isElementLike(value: unknown): value is HTMLElement {
  return Boolean(
    value &&
      typeof value === "object" &&
      "innerText" in value &&
      "textContent" in value &&
      "getBoundingClientRect" in value
  );
}

function visibleArea(element: HTMLElement): number {
  const rect = element.getBoundingClientRect();
  return Math.max(0, rect.width) * Math.max(0, rect.height);
}

function compactText(value: string): string {
  return value.replace(/\s+/g, " ").trim();
}

function wait(timeoutMs: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, timeoutMs));
}

function clampInteger(value: number | undefined, fallback: number, min: number, max: number): number {
  const numeric = Number.isFinite(value) ? Math.trunc(value as number) : fallback;
  return Math.min(max, Math.max(min, numeric));
}

function formatDuration(value: number): string {
  const totalSeconds = Math.max(0, Math.round(value));
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;
  if (hours > 0) return `${hours}:${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
  return `${minutes}:${String(seconds).padStart(2, "0")}`;
}

