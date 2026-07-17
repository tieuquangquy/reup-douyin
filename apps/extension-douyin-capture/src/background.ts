import { postBackendJson } from "./extensionBackendClient.js";
import { findExactAwemeCandidates, parseCdpResponseBodyJson, type CdpAwemeCandidate } from "./cdpAweme.js";
import { WHOLE_PROFILE_HARVEST_STATE_KEY, appendWholeProfileTrace, computeTargetStatusSummary, createPersistentScanJobRecord, createWholeProfileHarvestIdleState, emptyClassificationCounts, emptyClassificationState, type PersistentScanJobRecord, type PostScanCounterSnapshot, type WholeProfileHarvestQueueItem, type WholeProfileHarvestState, type WholeProfileHarvestTargetDetail } from "./wholeProfileHarvest/state.js";
import { buildCollectQueuePreviewFromQueue } from "./wholeProfileHarvest/profileClassification.js";
import { scanPersistedMeetsExpectedCount } from "./wholeProfileHarvest/profileContext.js";
import { normalizeDouyinProfileUrl } from "./wholeProfileHarvest/profileResolver.js";
import {
  ensureDouyinTabForHybridTailGapCollect,
  fetchProfilePostPageFromHybridTab,
  readDomTailReconcileProbeFromHybridTab
} from "./wholeProfileHarvest/hybridTailGapTabRuntime.js";
import { LARGE_PROFILE_QUEUE_PREVIEW_WINDOW_SIZE, buildQueueWindowFromRecords, createProfileTargetRepository, profileIdentifierFromUrl, type ProfileTargetCursorCheckpoint, type ProfileTargetRecord, type ProfileTargetScanContinuationCheckpoint } from "./wholeProfileHarvest/profileTargetRepository.js";
import type {
  AccessibilityTreePayload,
  ActionRailRectDiagnostic,
  CdpAwemeEvidence,
  CdpAwemeStatus,
  CdpDomSnapshotPayload,
  ExtensionBackendPostRequest,
  ExtensionBackendPostResponse,
  ExtensionMessage,
  ExtensionMessageResponse,
  ScreenshotOcrPayload,
  VisualRightRailPayload
} from "./types.js";
import type { WholeProfileHarvestRuntime, HybridNetworkCacheRunnerOptions, WholeProfileCaptureSessionItemsResult, WholeProfileCaptureInboxProfileItemsResult, WholeProfileCaptureInboxProfileSummaryResult, WholeProfileBackendFlushResult } from "./wholeProfileHarvest/controller.js";
import { runBatchCollectHybridNetworkCacheMode, runCloseUnreachableTailGap, runSkipHybridUncollectableRemainder, runUnattendedHybridCollectAllRemaining, pauseWholeProfileHarvestOnAuthLoss, chunkDetailHydrationDiscoveries, HYBRID_DETAIL_HYDRATION_PARALLEL_CHUNKS } from "./wholeProfileHarvest/controller.js";
import { syncDouyinCalibrationFromStorage, DOUYIN_SCANNER_CALIBRATION_KEY } from "./wholeProfileHarvest/calibration.js";
import { BACKGROUND_RUNTIME_BUILD_ID, EXTENSION_BUILD_TIMESTAMP, EXTENSION_RUNTIME_BUILD_ID } from "./generated/buildIdentity.js";
import { reconcileExtensionAuthWithWebTabToken } from "./wholeProfileHarvest/appBackendAuth.js";
import { buildHybridProfileCardEvidence, evidenceHasHybridRequiredMetrics } from "./wholeProfileHarvest/hybridHydration.js";
import {
  buildDisplayedProfileQueueCapDiagnostics,
  capOrderedQueueToDisplayedProfileLimit,
  capTargetDetailsToAwemeIds,
  DISPLAYED_PROFILE_COLLECT_SCOPE,
  resolveOverDisplayedExtraAwemeIdSet
} from "./wholeProfileHarvest/displayedProfileQueueCap.js";
import {
  applyProfileCollectContractToPostScanSnapshot,
  buildProfileCollectContractFromState
} from "./wholeProfileHarvest/profileCollectContract.js";
import { extractExactDetailCandidates, buildHybridDetailFetchUrls, selectBestDetailCandidate } from "./detailHydration.js";
import type { NetworkVideoMetadata } from "./types.js";

type Debuggee = { tabId: number };
type ResponseInfo = { url: string; requestId: string };

type CdpSession = {
  tabId: number;
  attached: boolean;
  debugger_version: string;
  network_enabled: boolean;
  runtime_enabled: boolean;
  response_count: number;
  json_response_count: number;
  candidate_aweme_count: number;
  exact_match_count: number;
  runtime_exact_match_count: number;
  last_matching_aweme_id: string | null;
  last_matching_response_url: string | null;
  last_error: string | null;
  responses: Map<string, ResponseInfo>;
  awemeById: Map<string, CdpAwemeEvidence>;
};

const cdpSessions = new Map<number, CdpSession>();
type ProfileScanTraceVersion = "22C-11B" | "22C-12F";
type PostProbeProductiveGate22C11B = "productive" | "empty_profile" | "blocked" | "not_productive" | "probe_missing";

type PostProbeProductiveGateDerivation22C11B = {
  gate: PostProbeProductiveGate22C11B;
  source: "raw_probe" | "normalized_probe" | "flattened_diagnostics";
  reason: "aweme_ids_present" | "video_anchors_present" | "grid_candidates_present" | "explicit_empty_profile" | "checkpoint_detected" | "no_candidates" | "probe_missing";
  inputs: Record<string, unknown>;
};

const SCAN_PROFILE_BACKGROUND_TRACE_VERSION: ProfileScanTraceVersion = "22C-12F";
const SCAN_PROFILE_BACKGROUND_CONTROLLER_VERSION = "22C-12F-unified-runtime";
const SCAN_POST_PROBE_HANDOFF_VERSION: ProfileScanTraceVersion = "22C-12F";
const SCAN_POST_PROBE_HANDOFF_PATCH = "minimal_active_works_grid_scanner_22C12F";
const CANONICAL_SCAN_PROFILE_MESSAGE_22C11B = "DOUYIN_SCAN_PROFILE_MINIMAL_22C11B";
const CANONICAL_SCAN_PROFILE_PING_22C11B = "DOUYIN_SCAN_PROFILE_MINIMAL_22C11B_PING";
const CANONICAL_SCAN_PROFILE_PAGE_MESSAGE_22C14B = "DOUYIN_SCAN_PROFILE_POST_PAGE_22C14B";
const CANONICAL_SCAN_PAGE_BUDGET_22C14B = 128;
const CANONICAL_SCAN_AUTO_CONTINUATION_MAX_BATCHES_22C14B = 4;
const CANONICAL_SCAN_MAX_RETRIES_22C14B = 4;
const CANONICAL_SCAN_NO_NEW_PAGE_LIMIT_22C14B = 3;
const CANONICAL_SCAN_RETRY_WAIT_STALL_MS_22C14B = 30_000;
const CANONICAL_SCAN_RUNNING_STALL_MS_22C14B = 45_000;
const CANONICAL_SCAN_TAIL_RECONCILE_MAX_CANDIDATES_22C14E = 120;
const CANONICAL_SCAN_TAIL_RECONCILE_TIME_BUDGET_MS_22C14E = 1500;
const SCAN_PROFILE_STORAGE_BUDGET_BYTES_22C11B = 700_000;
const SCAN_PROFILE_STAGE_TIMEOUTS_22C11B: Record<string, number> = { resolving_tab: 5_000, ensuring_content_script: 10_000, probing_dom: 10_000, scanning_profile: 45_000 };
const STORAGE_COMPACT_QUEUE_LIMIT_22C13C = LARGE_PROFILE_QUEUE_PREVIEW_WINDOW_SIZE;
const STORAGE_COMPACT_RESULTS_LIMIT_22C13C = 200;
const STORAGE_COMPACT_TRACE_LIMIT_22C13C = 40;
const STORAGE_COMPACT_DEBUG_TRACE_LIMIT_22C13C = 60;
const STORAGE_COMPACT_DIAGNOSTIC_MAX_DEPTH_22C13C = 4;
const STORAGE_COMPACT_DIAGNOSTIC_MAX_KEYS_22C13C = 320;
const STORAGE_COMPACT_DIAGNOSTIC_MAX_ARRAY_ITEMS_22C13C = 80;
const STORAGE_COMPACT_DIAGNOSTIC_MAX_STRING_LENGTH_22C13C = 640;

function recordValue(source: Record<string, unknown> | null | undefined, ...keys: string[]): unknown {
  if (!source) return undefined;
  for (const key of keys) {
    if (source[key] !== undefined && source[key] !== null) return source[key];
  }
  return undefined;
}

function numericValue(value: unknown): number {
  const numberValue = typeof value === "number" ? value : Number(value ?? 0);
  return Number.isFinite(numberValue) ? numberValue : 0;
}

function numberFromDiagnostics(...values: unknown[]): number {
  for (const value of values) {
    const next = typeof value === "number" ? value : Number(value ?? Number.NaN);
    if (Number.isFinite(next)) return Math.max(0, Math.round(next));
  }
  return 0;
}

function nearCompleteExpectedGap22C14N(expectedCount: number | null, totalPersisted: number): { allowed: boolean; gap: number | null; threshold: number | null; ratio: number | null } {
  if (expectedCount == null || !Number.isFinite(expectedCount) || expectedCount <= 0) return { allowed: false, gap: null, threshold: null, ratio: null };
  const persisted = Number.isFinite(totalPersisted) ? Math.max(0, Math.round(totalPersisted)) : 0;
  const gap = Math.max(Math.round(expectedCount) - persisted, 0);
  const threshold = Math.max(5, Math.ceil(expectedCount * 0.01));
  const ratio = gap / expectedCount;
  return { allowed: gap > 0 && gap <= threshold, gap, threshold, ratio };
}

type TailReconcileCandidate22C14E = { aweme_id: string; source_url: string; profile_url: string | null; caption?: string | null; thumbnail_url?: string | null; source?: string; endpoint_path?: string | null; endpoint_kind?: string | null };
type TailReconcileResult22C14E = { queue: WholeProfileHarvestQueueItem[]; targetDetails: WholeProfileHarvestTargetDetail[]; diagnostics: Record<string, unknown> };

function tailReconcileCandidateArray22C14E(value: unknown, source = "dom_profile_probe_tail_reconcile_candidates_22C14E"): { candidates: TailReconcileCandidate22C14E[]; invalidCount: number } {
  if (!Array.isArray(value)) return { candidates: [], invalidCount: 0 };
  let invalidCount = 0;
  const candidates = value.flatMap((entry): TailReconcileCandidate22C14E[] => {
    if (typeof entry === "string") {
      if (/^\d{8,24}$/.test(entry)) return [{ aweme_id: entry, source_url: `https://www.douyin.com/video/${entry}`, profile_url: null, source }];
      invalidCount += 1;
      return [];
    }
    if (!entry || typeof entry !== "object") { invalidCount += 1; return []; }
    const record = entry as Record<string, unknown>;
    const awemeId = typeof record.aweme_id === "string" ? record.aweme_id : typeof record.awemeId === "string" ? record.awemeId : null;
    if (!awemeId || !/^\d{8,24}$/.test(awemeId)) { invalidCount += 1; return []; }
    const sourceUrl = typeof record.source_url === "string" && record.source_url ? record.source_url : typeof record.sourceUrl === "string" && record.sourceUrl ? record.sourceUrl : `https://www.douyin.com/video/${awemeId}`;
    const profileUrl = typeof record.profile_url === "string" ? record.profile_url : typeof record.profileUrl === "string" ? record.profileUrl : null;
    const endpointPath = typeof record.endpoint_path === "string" ? record.endpoint_path : typeof record.endpointPath === "string" ? record.endpointPath : null;
    const endpointKind = typeof record.endpoint_kind === "string" ? record.endpoint_kind : typeof record.endpointKind === "string" ? record.endpointKind : null;
    return [{ aweme_id: awemeId, source_url: sourceUrl, profile_url: profileUrl, caption: typeof record.caption === "string" ? record.caption : null, thumbnail_url: typeof record.thumbnail_url === "string" ? record.thumbnail_url : null, source, endpoint_path: endpointPath, endpoint_kind: endpointKind }];
  });
  return { candidates, invalidCount };
}

function tailReconcileSameProfile22C14E(candidate: TailReconcileCandidate22C14E, profileUrl: string): boolean {
  if (!candidate.profile_url) return candidate.source !== "passive_profile_post_network_22C14E";
  return profileIdentifierFromUrl(candidate.profile_url) === profileIdentifierFromUrl(profileUrl);
}

function tailReconcilePassiveProfilePostCandidates22C14E(diagnostics: Record<string, unknown>, profileUrl: string): { candidates: TailReconcileCandidate22C14E[]; invalidCount: number; favoriteCount: number; otherProfileCount: number } {
  const raw = tailReconcileCandidateArray22C14E(diagnostics.network_profile_post_targets, "passive_profile_post_network_22C14E");
  let favoriteCount = 0;
  let otherProfileCount = 0;
  const candidates = raw.candidates.filter((candidate) => {
    const endpointPathOk = candidate.endpoint_path == null || candidate.endpoint_path === "/aweme/v1/web/aweme/post/";
    const endpointKindOk = candidate.endpoint_kind == null || candidate.endpoint_kind === "profile_post";
    if (candidate.endpoint_kind === "favorite" || (candidate.endpoint_path != null && candidate.endpoint_path !== "/aweme/v1/web/aweme/post/")) { favoriteCount += 1; return false; }
    if (!endpointPathOk || !endpointKindOk) return false;
    if (!tailReconcileSameProfile22C14E(candidate, profileUrl)) { otherProfileCount += 1; return false; }
    return true;
  });
  return { candidates, invalidCount: raw.invalidCount, favoriteCount, otherProfileCount };
}

async function reconcileScanTailCandidates22C14E(args: { scanRunId: string; tabId?: number | null; profileUrl: string; expectedCount: number | null; queue: WholeProfileHarvestQueueItem[]; targetDetails: WholeProfileHarvestTargetDetail[]; activeTerminalEvidence: boolean; at: string; responseDiagnostics: Record<string, unknown>; activeDiagnostics: Record<string, unknown> }): Promise<TailReconcileResult22C14E> {
  const started = Date.now();
  const currentCount = args.queue.length;
  const gap = args.expectedCount == null ? 0 : Math.max(args.expectedCount - currentCount, 0);
  const activeFetchCount = numberFromDiagnostics(args.activeDiagnostics.target_count, args.activeDiagnostics.only_aweme_count);
  const cursorSummary = `has_more=${String(args.activeDiagnostics.has_more_state ?? "unknown")};max_cursor=${String(args.activeDiagnostics.max_cursor ?? args.activeDiagnostics.cursor ?? "unknown")};min_cursor=${String(args.activeDiagnostics.min_cursor ?? "unknown")};request_item_cursor=${String(args.activeDiagnostics.request_item_cursor ?? "unknown")};last_batch_size=${String(args.activeDiagnostics.last_batch_size ?? args.activeDiagnostics.page_count ?? "unknown")}`;
  const emptyDiagnostics = (attempted: "no" | "not_needed", reason: string) => ({ tail_reconcile_attempted: attempted, tail_reconcile_candidates: 0, tail_reconcile_added: 0, tail_reconcile_rejected: 0, tail_reconcile_gap_before: gap, tail_reconcile_gap_after: gap, tail_reconcile_sources_checked: [], tail_reconcile_unrecoverable_reason: reason, tail_reconcile_reason: reason, tail_reconcile_duration_ms: Date.now() - started, final_gap_reconciliation_attempted: attempted === "not_needed" ? "not_needed" : "no", final_gap_reconciliation_result: reason, final_gap_reconciliation_sources_checked: [], final_gap_expected_count: args.expectedCount, final_gap_active_fetch_count: activeFetchCount, final_gap_missing_count_before_reconcile: gap, final_gap_missing_count_after_reconcile: gap, final_gap_recovered_count: 0, final_gap_unrecovered_count: gap, final_gap_unrecovered_reason: reason, final_gap_passive_profile_post_count: 0, final_gap_passive_profile_post_new_count: 0, final_gap_dom_anchor_count: 0, final_gap_dom_anchor_new_count: 0, final_gap_duplicate_drop_count: 0, final_gap_invalid_drop_count: 0, final_gap_other_profile_drop_count: 0, final_gap_cursor_summary: cursorSummary, final_gap_last_batch_size: numberFromDiagnostics(args.activeDiagnostics.last_batch_size), final_gap_terminal_has_more: args.activeDiagnostics.has_more_state ?? null, final_gap_expected_count_source: args.responseDiagnostics.expected_profile_video_count_source ?? args.responseDiagnostics.expected_count_source ?? null });
  if (args.expectedCount == null || gap <= 0 || !args.activeTerminalEvidence || args.tabId == null) {
    const unrecoverableReason = gap <= 0 ? "no_expected_gap" : !args.activeTerminalEvidence ? "active_terminal_evidence_not_strong" : args.tabId == null ? "tab_unavailable" : "expected_count_unknown";
    return { queue: args.queue, targetDetails: args.targetDetails, diagnostics: emptyDiagnostics(gap <= 0 ? "not_needed" : "no", unrecoverableReason) };
  }
  const probe = await chrome.tabs.sendMessage(args.tabId, { type: "DOUYIN_PROFILE_DOM_PROBE_22C11B", scan_run_id: args.scanRunId, expected_profile_url: args.profileUrl, expectedProfileVideoCount: args.expectedCount, expected_profile_video_count: args.expectedCount, traceVersion: "22C-14E" } satisfies ExtensionMessage).catch((error) => ({ ok: false, diagnostics: { error: error instanceof Error ? error.message : String(error) } })) as ExtensionMessageResponse;
  const diagnostics = probe.diagnostics && typeof probe.diagnostics === "object" ? probe.diagnostics as Record<string, unknown> : {};
  const probeRecord = probe.profile_dom_probe && typeof probe.profile_dom_probe === "object" ? probe.profile_dom_probe as Record<string, unknown> : {};
  const passive = tailReconcilePassiveProfilePostCandidates22C14E(args.responseDiagnostics, args.profileUrl);
  const dom = tailReconcileCandidateArray22C14E(diagnostics.tail_reconcile_candidates ?? probeRecord.tail_reconcile_candidates ?? diagnostics.tail_reconcile_candidate_ids ?? probeRecord.tail_reconcile_candidate_ids, "dom_profile_probe_tail_reconcile_candidates_22C14E");
  const candidates = [...passive.candidates, ...dom.candidates].slice(0, CANONICAL_SCAN_TAIL_RECONCILE_MAX_CANDIDATES_22C14E);
  const sourcesChecked = ["passive_profile_post_network_22C14E", "dom_profile_probe_tail_reconcile_candidates_22C14E"];
  const seen = new Set(args.queue.map((item) => item.aweme_id));
  const queue = [...args.queue];
  const targetDetails = [...args.targetDetails];
  let duplicateDropCount = 0;
  let otherProfileDropCount = passive.otherProfileCount;
  let added = 0;
  // A terminal has_more=false response may still leave an expected-count gap; recover only same-profile candidates from reliable same-run evidence.
  for (const candidate of candidates) {
    if (Date.now() - started > CANONICAL_SCAN_TAIL_RECONCILE_TIME_BUDGET_MS_22C14E || queue.length >= args.expectedCount) break;
    if (seen.has(candidate.aweme_id)) { duplicateDropCount += 1; continue; }
    if (!tailReconcileSameProfile22C14E(candidate, args.profileUrl)) { otherProfileDropCount += 1; continue; }
    seen.add(candidate.aweme_id);
    added += 1;
    const index = queue.length + 1;
    const source = candidate.source ?? "tail_reconcile_unknown_22C14E";
    const evidence = { active_works_confidence: "high", source, profile_url: args.profileUrl, discovered_at: args.at };
    queue.push({ index, aweme_id: candidate.aweme_id, capture_status: "new", status: "new", attempts: 0, checkpoint_sequence: null, extraction_result: null, last_error: null, capture_inbox_item_id: null, source_url: candidate.source_url, thumbnail_url: candidate.thumbnail_url ?? null, caption: candidate.caption ?? null, profile_card_evidence: evidence });
    targetDetails.push({ index, aweme_id: candidate.aweme_id, source_url: candidate.source_url, profile_url: args.profileUrl, thumbnail_url: candidate.thumbnail_url ?? null, title: null, caption: candidate.caption ?? null, text_sample: candidate.caption ?? null, posted_text: null, posted_at: null, duration_text: null, duration_seconds: null, view_text: null, view_count: null, candidate_validation: { status: "accepted", source: "video_link", reason: source, source_url: candidate.source_url, card_context: true }, metadata_completeness: { has_profile_identity: true, has_thumbnail: candidate.thumbnail_url != null, has_title_or_caption: candidate.caption != null, has_posted_text: false, has_duration: false, has_view_count: false, has_detail_metrics: false }, capture_status: "new", backend_item: null, extraction_source: source, profile_card_evidence: evidence });
  }
  const gapAfter = Math.max(gap - added, 0);
  const invalidDropCount = passive.invalidCount + dom.invalidCount;
  const rejected = duplicateDropCount + invalidDropCount + otherProfileDropCount;
  const unrecoverableReason = gapAfter <= 0 ? null : candidates.length === 0 ? "no_reliable_same_profile_final_gap_candidates" : added === 0 ? "final_gap_candidates_not_same_profile_invalid_or_duplicate" : "final_gap_candidates_insufficient_for_expected_gap";
  const result = added >= gap ? "expected_gap_filled" : added > 0 ? "partial_gap_filled" : "no_valid_missing_candidates";
  return { queue: queue.map((item, index) => ({ ...item, index: index + 1 })), targetDetails: targetDetails.map((target, index) => ({ ...target, index: index + 1 })), diagnostics: { tail_reconcile_attempted: "yes", tail_reconcile_candidates: candidates.length, tail_reconcile_added: added, tail_reconcile_rejected: rejected, tail_reconcile_gap_before: gap, tail_reconcile_gap_after: gapAfter, tail_reconcile_sources_checked: sourcesChecked, tail_reconcile_unrecoverable_reason: unrecoverableReason, tail_reconcile_reason: result, tail_reconcile_duration_ms: Date.now() - started, final_gap_reconciliation_attempted: "yes", final_gap_reconciliation_result: result, final_gap_reconciliation_sources_checked: sourcesChecked, final_gap_expected_count: args.expectedCount, final_gap_active_fetch_count: activeFetchCount, final_gap_missing_count_before_reconcile: gap, final_gap_missing_count_after_reconcile: gapAfter, final_gap_recovered_count: added, final_gap_unrecovered_count: gapAfter, final_gap_unrecovered_reason: unrecoverableReason, final_gap_passive_profile_post_count: passive.candidates.length, final_gap_passive_profile_post_new_count: passive.candidates.filter((candidate) => !args.queue.some((item) => item.aweme_id === candidate.aweme_id)).length, final_gap_dom_anchor_count: dom.candidates.length, final_gap_dom_anchor_new_count: dom.candidates.filter((candidate) => !args.queue.some((item) => item.aweme_id === candidate.aweme_id)).length, final_gap_duplicate_drop_count: duplicateDropCount, final_gap_invalid_drop_count: invalidDropCount, final_gap_other_profile_drop_count: otherProfileDropCount, final_gap_cursor_summary: cursorSummary, final_gap_last_batch_size: numberFromDiagnostics(args.activeDiagnostics.last_batch_size), final_gap_terminal_has_more: args.activeDiagnostics.has_more_state ?? null, final_gap_expected_count_source: args.responseDiagnostics.expected_profile_video_count_source ?? args.responseDiagnostics.expected_count_source ?? null, final_gap_favorite_endpoint_drop_count: passive.favoriteCount } };
}

function canonicalRequestedProfileUrlFromDiagnostics(diagnostics: Record<string, unknown>, fallbackProfileUrl: string): string {
  const raw = typeof diagnostics.minimal_scan_network_probe_requested_profile_url_22C11B === "string"
    ? diagnostics.minimal_scan_network_probe_requested_profile_url_22C11B
    : typeof diagnostics.profile_url === "string"
      ? diagnostics.profile_url
      : fallbackProfileUrl;
  try {
    const parsed = new URL(raw);
    parsed.search = "";
    parsed.hash = "";
    return parsed.toString();
  } catch {
    return raw;
  }
}

function booleanValue(value: unknown): boolean {
  return value === true || value === "true" || value === "yes" || value === 1;
}

function objectValue(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : null;
}

function yesNoUnknownValue22C12B(value: unknown): "yes" | "no" | "unknown" {
  if (value === true || value === "true" || value === "yes" || value === 1) return "yes";
  if (value === false || value === "false" || value === "no" || value === 0) return "no";
  return "unknown";
}

function trueFalseUnknownValue22C12B(value: unknown): "true" | "false" | "unknown" {
  if (value === true || value === "true" || value === "yes" || value === 1) return "true";
  if (value === false || value === "false" || value === "no" || value === 0) return "false";
  return "unknown";
}

function optionalDiagnosticText22C12B(value: unknown): string | null {
  if (typeof value !== "string") return null;
  const normalized = value.trim();
  if (!normalized || normalized === "none") return null;
  return normalized;
}

function sanitizeDiagnosticObjectArray22C12B(value: unknown, maxItems = 16): Record<string, unknown>[] {
  if (!Array.isArray(value)) return [];
  return value
    .slice(0, Math.max(0, Math.round(maxItems)))
    .map((entry) => {
      if (!entry || typeof entry !== "object" || Array.isArray(entry)) return null;
      const record = entry as Record<string, unknown>;
      const compact: Record<string, unknown> = {};
      for (const [key, raw] of Object.entries(record).slice(0, 12)) {
        if (typeof key !== "string" || !key.trim()) continue;
        if (typeof raw === "string") {
          compact[key] = raw.length > 180 ? raw.slice(0, 180) : raw;
          continue;
        }
        if (typeof raw === "number" || typeof raw === "boolean") {
          compact[key] = raw;
          continue;
        }
        if (raw == null) {
          compact[key] = null;
        }
      }
      return compact;
    })
    .filter((entry): entry is Record<string, unknown> => Boolean(entry));
}

function sanitizeDiagnosticTextArray22C13B(value: unknown, maxItems = 32): string[] {
  if (!Array.isArray(value)) return [];
  return value
    .filter((entry): entry is string => typeof entry === "string" && entry.trim().length > 0)
    .slice(0, Math.max(0, Math.round(maxItems)))
    .map((entry) => entry.trim());
}

function sanitizeDiagnosticNumberRecord22C13B(value: unknown, maxKeys = 24): Record<string, number> {
  if (!value || typeof value !== "object" || Array.isArray(value)) return {};
  const record = value as Record<string, unknown>;
  const compact: Record<string, number> = {};
  for (const [key, raw] of Object.entries(record).slice(0, Math.max(0, Math.round(maxKeys)))) {
    if (typeof key !== "string" || !key.trim()) continue;
    const numeric = typeof raw === "number" ? raw : Number(raw ?? Number.NaN);
    if (!Number.isFinite(numeric)) continue;
    compact[key.trim()] = Math.max(0, Math.round(numeric));
  }
  return compact;
}

function canonicalActiveProfilePostDiagnostics22C12B(source: Record<string, unknown> | null | undefined): Record<string, unknown> {
  const diagnostics = source ?? {};
  const nested = objectValue(recordValue(diagnostics, "active_profile_post", "activeProfilePost")) ?? {};
  const notAttemptedReasonRaw = recordValue(
    diagnostics,
    "minimal_scan_active_profile_post_fetch_not_attempted_reason_22C12B",
    "active_profile_post_fetch_not_attempted_reason"
  ) ?? recordValue(nested, "not_attempted_reason");
  const stopReasonRaw = recordValue(
    diagnostics,
    "minimal_scan_active_profile_post_fetch_stop_reason_22C12B",
    "active_profile_post_fetch_stop_reason"
  ) ?? recordValue(nested, "stop_reason");
  const stopReason = optionalDiagnosticText22C12B(stopReasonRaw);
  const notAttemptedReason = optionalDiagnosticText22C12B(notAttemptedReasonRaw);
  const attempted = yesNoUnknownValue22C12B(
    recordValue(
      diagnostics,
      "minimal_scan_active_profile_post_fetch_attempted_22C12B",
      "active_profile_post_fetch_attempted"
    ) ?? recordValue(nested, "attempted") ?? (notAttemptedReason ? "no" : "unknown")
  );
  const enabled = yesNoUnknownValue22C12B(
    recordValue(
      diagnostics,
      "minimal_scan_active_profile_post_fetch_enabled_22C12B",
      "active_profile_post_fetch_enabled"
    ) ?? recordValue(nested, "enabled")
  );
  const diagnosticNumberArray22C14P = (value: unknown): number[] => Array.isArray(value)
    ? value.filter((entry): entry is number => typeof entry === "number" && Number.isFinite(entry)).map((entry) => Math.max(0, Math.round(entry)))
    : [];
  const diagnosticBooleanArray22C14P = (value: unknown): boolean[] => Array.isArray(value)
    ? value.filter((entry): entry is boolean => typeof entry === "boolean")
    : [];
  const diagnosticStatusArray22C14P = (value: unknown): Array<number | string | null> => Array.isArray(value)
    ? value.map((entry) => typeof entry === "number" || typeof entry === "string" ? entry : null)
    : [];
  const diagnosticTextArray22C14P = (value: unknown): string[] => Array.isArray(value)
    ? value.filter((entry): entry is string => typeof entry === "string" && entry.trim().length > 0).map((entry) => entry.trim())
    : [];
  const rawCanonical = {
    enabled,
    attempted,
    stop_reason: stopReason ?? notAttemptedReason,
    not_attempted_reason: notAttemptedReason,
    target_count: numberFromDiagnostics(
      recordValue(diagnostics, "minimal_scan_active_profile_post_fetch_target_count_22C12B", "active_profile_post_fetch_target_count"),
      recordValue(nested, "target_count")
    ),
    raw_items_total: numberFromDiagnostics(recordValue(diagnostics, "minimal_scan_active_profile_post_fetch_raw_items_total_22C14P", "active_profile_post_fetch_raw_items_total"), recordValue(nested, "raw_items_total")),
    raw_aweme_ids_total: numberFromDiagnostics(recordValue(diagnostics, "minimal_scan_active_profile_post_fetch_raw_aweme_ids_total_22C14P", "active_profile_post_fetch_raw_aweme_ids_total"), recordValue(nested, "raw_aweme_ids_total")),
    accepted_targets_total: numberFromDiagnostics(recordValue(diagnostics, "minimal_scan_active_profile_post_fetch_accepted_targets_total_22C14P", "active_profile_post_fetch_accepted_targets_total"), recordValue(nested, "accepted_targets_total")),
    duplicate_drop_count: numberFromDiagnostics(recordValue(diagnostics, "minimal_scan_active_profile_post_fetch_duplicate_drop_count_22C14P", "active_profile_post_fetch_duplicate_drop_count"), recordValue(nested, "duplicate_drop_count")),
    invalid_drop_count: numberFromDiagnostics(recordValue(diagnostics, "minimal_scan_active_profile_post_fetch_invalid_drop_count_22C14P", "active_profile_post_fetch_invalid_drop_count"), recordValue(nested, "invalid_drop_count")),
    other_profile_drop_count: numberFromDiagnostics(recordValue(diagnostics, "minimal_scan_active_profile_post_fetch_other_profile_drop_count_22C14P", "active_profile_post_fetch_other_profile_drop_count"), recordValue(nested, "other_profile_drop_count")),
    favorite_endpoint_drop_count: numberFromDiagnostics(recordValue(diagnostics, "minimal_scan_active_profile_post_fetch_favorite_endpoint_drop_count_22C14P", "active_profile_post_fetch_favorite_endpoint_drop_count"), recordValue(nested, "favorite_endpoint_drop_count")),
    missing_aweme_id_count: numberFromDiagnostics(recordValue(diagnostics, "minimal_scan_active_profile_post_fetch_missing_aweme_id_count_22C14P", "active_profile_post_fetch_missing_aweme_id_count"), recordValue(nested, "missing_aweme_id_count")),
    per_page_raw_counts: diagnosticNumberArray22C14P(recordValue(diagnostics, "minimal_scan_active_profile_post_fetch_per_page_raw_counts_22C14P", "active_profile_post_fetch_per_page_raw_counts") ?? recordValue(nested, "per_page_raw_counts")),
    per_page_aweme_id_counts: diagnosticNumberArray22C14P(recordValue(diagnostics, "minimal_scan_active_profile_post_fetch_per_page_aweme_id_counts_22C14P", "active_profile_post_fetch_per_page_aweme_id_counts") ?? recordValue(nested, "per_page_aweme_id_counts")),
    per_page_accepted_counts: diagnosticNumberArray22C14P(recordValue(diagnostics, "minimal_scan_active_profile_post_fetch_per_page_accepted_counts_22C14P", "active_profile_post_fetch_per_page_accepted_counts") ?? recordValue(nested, "per_page_accepted_counts")),
    per_page_duplicate_drop_counts: diagnosticNumberArray22C14P(recordValue(diagnostics, "minimal_scan_active_profile_post_fetch_per_page_duplicate_drop_counts_22C14P", "active_profile_post_fetch_per_page_duplicate_drop_counts") ?? recordValue(nested, "per_page_duplicate_drop_counts")),
    per_page_missing_aweme_id_counts: diagnosticNumberArray22C14P(recordValue(diagnostics, "minimal_scan_active_profile_post_fetch_per_page_missing_aweme_id_counts_22C14P", "active_profile_post_fetch_per_page_missing_aweme_id_counts") ?? recordValue(nested, "per_page_missing_aweme_id_counts")),
    per_page_has_more: diagnosticBooleanArray22C14P(recordValue(diagnostics, "minimal_scan_active_profile_post_fetch_per_page_has_more_22C14P", "active_profile_post_fetch_per_page_has_more") ?? recordValue(nested, "per_page_has_more")),
    per_page_cursor_present: diagnosticBooleanArray22C14P(recordValue(diagnostics, "minimal_scan_active_profile_post_fetch_per_page_cursor_present_22C14P", "active_profile_post_fetch_per_page_cursor_present") ?? recordValue(nested, "per_page_cursor_present")),
    per_page_status_codes: diagnosticStatusArray22C14P(recordValue(diagnostics, "minimal_scan_active_profile_post_fetch_per_page_status_codes_22C14P", "active_profile_post_fetch_per_page_status_codes") ?? recordValue(nested, "per_page_status_codes")),
    per_page_stop_reasons: diagnosticTextArray22C14P(recordValue(diagnostics, "minimal_scan_active_profile_post_fetch_per_page_stop_reasons_22C14P", "active_profile_post_fetch_per_page_stop_reasons") ?? recordValue(nested, "per_page_stop_reasons")),
    has_more_state: trueFalseUnknownValue22C12B(
      recordValue(diagnostics, "minimal_scan_active_profile_post_fetch_has_more_state_22C12B", "active_profile_post_fetch_has_more_state") ?? recordValue(nested, "has_more_state")
    ),
    only_aweme_count: numberFromDiagnostics(
      recordValue(diagnostics, "minimal_scan_active_profile_post_only_aweme_count_22C12B", "active_profile_post_only_aweme_count"),
      recordValue(nested, "only_aweme_count")
    ),
    request_count: numberFromDiagnostics(
      recordValue(diagnostics, "minimal_scan_active_profile_post_fetch_request_count_22C12B", "active_profile_post_fetch_request_count"),
      recordValue(nested, "request_count")
    ),
    batch_count: numberFromDiagnostics(
      recordValue(diagnostics, "minimal_scan_active_profile_post_fetch_batch_count_22C12B", "active_profile_post_fetch_batch_count"),
      recordValue(nested, "batch_count")
    ),
    page_count: numberFromDiagnostics(
      recordValue(diagnostics, "active_profile_post_fetch_page_count"),
      recordValue(diagnostics, "minimal_scan_active_profile_post_fetch_page_count_22C12B"),
      recordValue(nested, "page_count"),
      recordValue(diagnostics, "minimal_scan_active_profile_post_fetch_request_count_22C12B", "active_profile_post_fetch_request_count"),
      recordValue(diagnostics, "minimal_scan_active_profile_post_fetch_batch_count_22C12B", "active_profile_post_fetch_batch_count"),
      recordValue(nested, "request_count"),
      recordValue(nested, "batch_count")
    ),
    page_cap: numberFromDiagnostics(
      recordValue(diagnostics, "minimal_scan_active_profile_post_fetch_page_cap_22C12B", "active_profile_post_fetch_page_cap"),
      recordValue(nested, "page_cap")
    ),
    page_cap_hit_count: numberFromDiagnostics(
      recordValue(diagnostics, "minimal_scan_active_profile_post_fetch_page_cap_hit_count_22C12B", "active_profile_post_fetch_page_cap_hit_count"),
      recordValue(nested, "page_cap_hit_count")
    ),
    page_cap_hit_while_has_more_count: numberFromDiagnostics(
      recordValue(
        diagnostics,
        "minimal_scan_active_profile_post_fetch_page_cap_hit_while_has_more_count_22C12B",
        "active_profile_post_fetch_page_cap_hit_while_has_more_count"
      ),
      recordValue(nested, "page_cap_hit_while_has_more_count")
    ),
    runtime_timeout_ms: numberFromDiagnostics(
      recordValue(diagnostics, "minimal_scan_active_profile_post_fetch_runtime_timeout_ms_22C12B", "active_profile_post_fetch_runtime_timeout_ms"),
      recordValue(nested, "runtime_timeout_ms")
    ),
    runtime_timeout_hit: yesNoUnknownValue22C12B(
      recordValue(diagnostics, "minimal_scan_active_profile_post_fetch_runtime_timeout_hit_22C12B", "active_profile_post_fetch_runtime_timeout_hit")
      ?? recordValue(nested, "runtime_timeout_hit")
    ),
    continuation_policy: (() => {
      const value = recordValue(diagnostics, "minimal_scan_active_profile_post_fetch_continuation_policy_22C12B", "active_profile_post_fetch_continuation_policy")
        ?? recordValue(nested, "continuation_policy");
      return optionalDiagnosticText22C12B(value);
    })(),
    fallback_cycle_eligible: yesNoUnknownValue22C12B(
      recordValue(diagnostics, "minimal_scan_active_profile_post_fetch_fallback_cycle_eligible_22C13B", "active_profile_post_fetch_fallback_cycle_eligible")
      ?? recordValue(nested, "fallback_cycle_eligible")
    ),
    fallback_cycle_attempted: yesNoUnknownValue22C12B(
      recordValue(diagnostics, "minimal_scan_active_profile_post_fetch_fallback_cycle_attempted_22C13B", "active_profile_post_fetch_fallback_cycle_attempted")
      ?? recordValue(nested, "fallback_cycle_attempted")
    ),
    fallback_cycle_stop_reason: (() => {
      const value = recordValue(diagnostics, "minimal_scan_active_profile_post_fetch_fallback_cycle_stop_reason_22C13B", "active_profile_post_fetch_fallback_cycle_stop_reason")
        ?? recordValue(nested, "fallback_cycle_stop_reason");
      return optionalDiagnosticText22C12B(value);
    })(),
    fallback_cycle_has_more_state: trueFalseUnknownValue22C12B(
      recordValue(diagnostics, "minimal_scan_active_profile_post_fetch_fallback_cycle_has_more_state_22C13B", "active_profile_post_fetch_fallback_cycle_has_more_state")
      ?? recordValue(nested, "fallback_cycle_has_more_state")
    ),
    fallback_cycle_request_count: numberFromDiagnostics(
      recordValue(diagnostics, "minimal_scan_active_profile_post_fetch_fallback_cycle_request_count_22C13B", "active_profile_post_fetch_fallback_cycle_request_count"),
      recordValue(nested, "fallback_cycle_request_count")
    ),
    fallback_cycle_batch_count: numberFromDiagnostics(
      recordValue(diagnostics, "minimal_scan_active_profile_post_fetch_fallback_cycle_batch_count_22C13B", "active_profile_post_fetch_fallback_cycle_batch_count"),
      recordValue(nested, "fallback_cycle_batch_count")
    ),
    error: (() => {
      const value = recordValue(diagnostics, "minimal_scan_active_profile_post_fetch_error_22C12B", "active_profile_post_fetch_error") ?? recordValue(nested, "error");
      return optionalDiagnosticText22C12B(value);
    })(),
    response_shape: (() => {
      const value = recordValue(diagnostics, "minimal_scan_active_profile_post_fetch_response_shape_22C12B", "active_profile_post_fetch_response_shape") ?? recordValue(nested, "response_shape");
      return typeof value === "string" && value.trim() ? value.trim() : "unknown";
    })(),
    endpoint_variant_attempt_count: numberFromDiagnostics(
      recordValue(
        diagnostics,
        "minimal_scan_active_profile_post_fetch_endpoint_variant_attempt_count_22C12B",
        "active_profile_post_fetch_endpoint_variant_attempt_count"
      ),
      recordValue(nested, "endpoint_variant_attempt_count")
    ),
    endpoint_variant_success: (() => {
      const value = recordValue(
        diagnostics,
        "minimal_scan_active_profile_post_fetch_endpoint_variant_success_22C12B",
        "active_profile_post_fetch_endpoint_variant_success",
        "active_profile_post_fetch_endpoint_used"
      ) ?? recordValue(nested, "endpoint_variant_success", "endpoint_used");
      return optionalDiagnosticText22C12B(value);
    })(),
    endpoint_attempt_samples: sanitizeDiagnosticObjectArray22C12B(
      recordValue(
        diagnostics,
        "minimal_scan_active_profile_post_fetch_endpoint_attempt_samples_22C12B",
        "active_profile_post_fetch_endpoint_attempt_samples"
      ) ?? recordValue(nested, "endpoint_attempt_samples")
    ),
    parser_route: (() => {
      const value = recordValue(
        diagnostics,
        "minimal_scan_active_profile_post_fetch_parser_route_22C12B",
        "active_profile_post_fetch_parser_route"
      ) ?? recordValue(nested, "parser_route");
      return optionalDiagnosticText22C12B(value);
    })(),
    parser_routes_tried: (() => {
      const value = recordValue(
        diagnostics,
        "minimal_scan_active_profile_post_fetch_parser_routes_tried_22C12B",
        "active_profile_post_fetch_parser_routes_tried"
      ) ?? recordValue(nested, "parser_routes_tried");
      if (!Array.isArray(value)) return [];
      return value
        .filter((entry): entry is string => typeof entry === "string" && entry.trim().length > 0)
        .slice(0, 32)
        .map((entry) => entry.trim());
    })(),
    parser_direct_routes_tried: (() => {
      const value = recordValue(
        diagnostics,
        "minimal_scan_active_profile_post_fetch_parser_direct_routes_tried_22C12B",
        "active_profile_post_fetch_parser_direct_routes_tried"
      ) ?? recordValue(nested, "parser_direct_routes_tried");
      if (!Array.isArray(value)) return [];
      return value
        .filter((entry): entry is string => typeof entry === "string" && entry.trim().length > 0)
        .slice(0, 32)
        .map((entry) => entry.trim());
    })(),
    parser_direct_match_count: numberFromDiagnostics(
      recordValue(
        diagnostics,
        "minimal_scan_active_profile_post_fetch_parser_direct_match_count_22C12B",
        "active_profile_post_fetch_parser_direct_match_count"
      ),
      recordValue(nested, "parser_direct_match_count")
    ),
    parser_fallback_attempted: yesNoUnknownValue22C12B(
      recordValue(
        diagnostics,
        "minimal_scan_active_profile_post_fetch_parser_fallback_attempted_22C12B",
        "active_profile_post_fetch_parser_fallback_attempted"
      ) ?? recordValue(nested, "parser_fallback_attempted")
    ),
    parser_fallback_match_count: numberFromDiagnostics(
      recordValue(
        diagnostics,
        "minimal_scan_active_profile_post_fetch_parser_fallback_match_count_22C12B",
        "active_profile_post_fetch_parser_fallback_match_count"
      ),
      recordValue(nested, "parser_fallback_match_count")
    ),
    parser_fallback_candidate_count: numberFromDiagnostics(
      recordValue(
        diagnostics,
        "minimal_scan_active_profile_post_fetch_parser_fallback_candidate_count_22C12B",
        "active_profile_post_fetch_parser_fallback_candidate_count"
      ),
      recordValue(nested, "parser_fallback_candidate_count")
    ),
    parser_fallback_visited_nodes: numberFromDiagnostics(
      recordValue(
        diagnostics,
        "minimal_scan_active_profile_post_fetch_parser_fallback_visited_nodes_22C12B",
        "active_profile_post_fetch_parser_fallback_visited_nodes"
      ),
      recordValue(nested, "parser_fallback_visited_nodes")
    ),
    effective_attempted: yesNoUnknownValue22C12B(
      recordValue(
        diagnostics,
        "minimal_scan_active_profile_post_fetch_effective_attempted_22C13B",
        "active_profile_post_fetch_effective_attempted"
      ) ?? recordValue(nested, "effective_attempted")
    ),
    effective_attempt_reason: (() => {
      const value = recordValue(
        diagnostics,
        "minimal_scan_active_profile_post_fetch_effective_attempt_reason_22C13B",
        "active_profile_post_fetch_effective_attempt_reason"
      ) ?? recordValue(nested, "effective_attempt_reason");
      return optionalDiagnosticText22C12B(value);
    })(),
    template_warmup_attempted: yesNoUnknownValue22C12B(
      recordValue(
        diagnostics,
        "minimal_scan_active_profile_post_template_warmup_attempted_22C13B",
        "active_profile_post_template_warmup_attempted"
      ) ?? recordValue(nested, "template_warmup_attempted")
    ),
    template_warmup_attempt_count: numberFromDiagnostics(
      recordValue(
        diagnostics,
        "minimal_scan_active_profile_post_template_warmup_attempt_count_22C13B",
        "active_profile_post_template_warmup_attempt_count"
      ),
      recordValue(nested, "template_warmup_attempt_count")
    ),
    template_warmup_applied_template: yesNoUnknownValue22C12B(
      recordValue(
        diagnostics,
        "minimal_scan_active_profile_post_template_warmup_applied_template_22C13B",
        "active_profile_post_template_warmup_applied_template"
      ) ?? recordValue(nested, "template_warmup_applied_template")
    ),
    template_warmup_stop_reason: (() => {
      const value = recordValue(
        diagnostics,
        "minimal_scan_active_profile_post_template_warmup_stop_reason_22C13B",
        "active_profile_post_template_warmup_stop_reason"
      ) ?? recordValue(nested, "template_warmup_stop_reason");
      return optionalDiagnosticText22C12B(value);
    })(),
    template_found: yesNoUnknownValue22C12B(
      recordValue(
        diagnostics,
        "minimal_scan_active_profile_post_template_found_22C13B",
        "active_profile_post_template_found"
      ) ?? recordValue(nested, "template_found")
    ),
    template_source: (() => {
      const value = recordValue(
        diagnostics,
        "minimal_scan_active_profile_post_template_source_22C13B",
        "active_profile_post_template_source"
      ) ?? recordValue(nested, "template_source");
      return optionalDiagnosticText22C12B(value);
    })(),
    template_endpoint_path: (() => {
      const value = recordValue(
        diagnostics,
        "minimal_scan_active_profile_post_template_endpoint_path_22C13B",
        "active_profile_post_template_endpoint_path"
      ) ?? recordValue(nested, "template_endpoint_path");
      return optionalDiagnosticText22C12B(value);
    })(),
    template_query_keys: sanitizeDiagnosticTextArray22C13B(
      recordValue(
        diagnostics,
        "minimal_scan_active_profile_post_template_query_keys_22C13B",
        "active_profile_post_template_query_keys"
      ) ?? recordValue(nested, "template_query_keys")
    ),
    template_required_query_keys: sanitizeDiagnosticTextArray22C13B(
      recordValue(
        diagnostics,
        "minimal_scan_active_profile_post_template_required_query_keys_22C13B",
        "active_profile_post_template_required_query_keys"
      ) ?? recordValue(nested, "template_required_query_keys")
    ),
    template_required_query_keys_available: yesNoUnknownValue22C12B(
      recordValue(
        diagnostics,
        "minimal_scan_active_profile_post_template_required_query_keys_available_22C13B",
        "active_profile_post_template_required_query_keys_available"
      ) ?? recordValue(nested, "template_required_query_keys_available")
    ),
    template_missing_required_query_keys: sanitizeDiagnosticTextArray22C13B(
      recordValue(
        diagnostics,
        "minimal_scan_active_profile_post_template_missing_required_query_keys_22C13B",
        "active_profile_post_template_missing_required_query_keys"
      ) ?? recordValue(nested, "template_missing_required_query_keys")
    ),
    template_secret_keys_present: yesNoUnknownValue22C12B(
      recordValue(
        diagnostics,
        "minimal_scan_active_profile_post_template_secret_keys_present_22C13B",
        "active_profile_post_template_secret_keys_present"
      ) ?? recordValue(nested, "template_secret_keys_present")
    ),
    template_secret_query_keys: sanitizeDiagnosticTextArray22C13B(
      recordValue(
        diagnostics,
        "minimal_scan_active_profile_post_template_secret_query_keys_22C13B",
        "active_profile_post_template_secret_query_keys"
      ) ?? recordValue(nested, "template_secret_query_keys")
    ),
    response_status_code: (() => {
      const raw = recordValue(
        diagnostics,
        "minimal_scan_active_profile_post_fetch_response_status_code_22C13B",
        "active_profile_post_fetch_response_status_code"
      ) ?? recordValue(nested, "response_status_code");
      if (typeof raw === "number" && Number.isFinite(raw)) return Math.round(raw);
      if (typeof raw === "string" && raw.trim()) return raw.trim();
      return null;
    })(),
    response_status_msg: (() => {
      const value = recordValue(
        diagnostics,
        "minimal_scan_active_profile_post_fetch_response_status_msg_22C13B",
        "active_profile_post_fetch_response_status_msg"
      ) ?? recordValue(nested, "response_status_msg");
      return optionalDiagnosticText22C12B(value);
    })(),
    response_top_level_keys: sanitizeDiagnosticTextArray22C13B(
      recordValue(
        diagnostics,
        "minimal_scan_active_profile_post_fetch_response_top_level_keys_22C13B",
        "active_profile_post_fetch_response_top_level_keys"
      ) ?? recordValue(nested, "response_top_level_keys")
    ),
    response_data_keys: sanitizeDiagnosticTextArray22C13B(
      recordValue(
        diagnostics,
        "minimal_scan_active_profile_post_fetch_response_data_keys_22C13B",
        "active_profile_post_fetch_response_data_keys"
      ) ?? recordValue(nested, "response_data_keys")
    ),
    response_result_keys: sanitizeDiagnosticTextArray22C13B(
      recordValue(
        diagnostics,
        "minimal_scan_active_profile_post_fetch_response_result_keys_22C13B",
        "active_profile_post_fetch_response_result_keys"
      ) ?? recordValue(nested, "response_result_keys")
    ),
    parser_path_counts: sanitizeDiagnosticNumberRecord22C13B(
      recordValue(
        diagnostics,
        "minimal_scan_active_profile_post_fetch_parser_path_counts_22C13B",
        "active_profile_post_fetch_parser_path_counts"
      ) ?? recordValue(nested, "parser_path_counts")
    ),
    list_sample_keys: sanitizeDiagnosticTextArray22C13B(
      recordValue(
        diagnostics,
        "minimal_scan_active_profile_post_fetch_list_sample_keys_22C13B",
        "active_profile_post_fetch_list_sample_keys"
      ) ?? recordValue(nested, "list_sample_keys")
    ),
    reject_reasons: sanitizeDiagnosticTextArray22C13B(
      recordValue(
        diagnostics,
        "minimal_scan_active_profile_post_fetch_reject_reasons_22C13B",
        "active_profile_post_fetch_reject_reasons"
      ) ?? recordValue(nested, "reject_reasons")
    ),
    template_sources_tried: sanitizeDiagnosticTextArray22C13B(recordValue(diagnostics, "minimal_scan_active_profile_post_template_sources_tried_22C13B", "active_profile_post_template_sources_tried") ?? recordValue(nested, "template_sources_tried")),
    template_source_selected: optionalDiagnosticText22C12B(recordValue(diagnostics, "minimal_scan_active_profile_post_template_source_selected_22C13B", "active_profile_post_template_source_selected") ?? recordValue(nested, "template_source_selected")),
    template_cache_hit: yesNoUnknownValue22C12B(recordValue(diagnostics, "minimal_scan_active_profile_post_template_cache_hit_22C13B", "active_profile_post_template_cache_hit") ?? recordValue(nested, "template_cache_hit")),
    fetch_tier_attempted: optionalDiagnosticText22C12B(recordValue(diagnostics, "minimal_scan_active_profile_post_fetch_tier_attempted_22C13B", "active_profile_post_fetch_tier_attempted") ?? recordValue(nested, "fetch_tier_attempted")),
    fetch_tier_result: optionalDiagnosticText22C12B(recordValue(diagnostics, "minimal_scan_active_profile_post_fetch_tier_result_22C13B", "active_profile_post_fetch_tier_result") ?? recordValue(nested, "fetch_tier_result")),
    fetch_tier_failure_reason: optionalDiagnosticText22C12B(recordValue(diagnostics, "minimal_scan_active_profile_post_fetch_tier_failure_reason_22C13B", "active_profile_post_fetch_tier_failure_reason") ?? recordValue(nested, "fetch_tier_failure_reason")),
    status_non_zero_retryable: yesNoUnknownValue22C12B(recordValue(diagnostics, "minimal_scan_active_profile_post_fetch_status_non_zero_retryable_22C13B", "active_profile_post_fetch_status_non_zero_retryable") ?? recordValue(nested, "status_non_zero_retryable")),
    status_non_zero_retry_count: numberFromDiagnostics(recordValue(diagnostics, "minimal_scan_active_profile_post_fetch_status_non_zero_retry_count_22C13B", "active_profile_post_fetch_status_non_zero_retry_count"), recordValue(nested, "status_non_zero_retry_count")),
    last_non_zero_code: recordValue(diagnostics, "minimal_scan_active_profile_post_fetch_last_non_zero_code_22C13B", "active_profile_post_fetch_last_non_zero_code") ?? recordValue(nested, "last_non_zero_code") ?? null,
    last_non_zero_reason: optionalDiagnosticText22C12B(recordValue(diagnostics, "minimal_scan_active_profile_post_fetch_last_non_zero_reason_22C13B", "active_profile_post_fetch_last_non_zero_reason") ?? recordValue(nested, "last_non_zero_reason"))
  };
  if (rawCanonical.template_found === "no") {
    rawCanonical.template_required_query_keys_available = "no";
    if (rawCanonical.template_warmup_stop_reason === "template_ready_initial") rawCanonical.template_warmup_stop_reason = "template_not_found_after_warmup";
    rawCanonical.template_source = null;
    rawCanonical.template_endpoint_path = null;
    rawCanonical.template_query_keys = [];
    rawCanonical.template_missing_required_query_keys = rawCanonical.template_required_query_keys;
    rawCanonical.template_secret_keys_present = "no";
    rawCanonical.template_secret_query_keys = [];
  }
  return rawCanonical;
}

function withCanonicalActiveProfilePostDiagnostics22C12B(source: Record<string, unknown> | null | undefined): Record<string, unknown> {
  const diagnostics = source ?? {};
  const activeProfilePost = canonicalActiveProfilePostDiagnostics22C12B(diagnostics);
  return {
    ...diagnostics,
    active_profile_post: activeProfilePost,
    active_profile_post_fetch_enabled: activeProfilePost.enabled,
    active_profile_post_fetch_attempted: activeProfilePost.attempted,
    active_profile_post_fetch_stop_reason: typeof activeProfilePost.stop_reason === "string" && activeProfilePost.stop_reason ? activeProfilePost.stop_reason : "none",
    active_profile_post_fetch_not_attempted_reason: typeof activeProfilePost.not_attempted_reason === "string" && activeProfilePost.not_attempted_reason ? activeProfilePost.not_attempted_reason : "none",
    active_profile_post_fetch_target_count: activeProfilePost.target_count,
    active_profile_post_fetch_has_more_state: activeProfilePost.has_more_state,
    active_profile_post_only_aweme_count: activeProfilePost.only_aweme_count,
    active_profile_post_fetch_request_count: activeProfilePost.request_count,
    active_profile_post_fetch_batch_count: activeProfilePost.batch_count,
    active_profile_post_fetch_page_count: numberFromDiagnostics(activeProfilePost.page_count),
    active_profile_post_fetch_raw_items_total: activeProfilePost.raw_items_total,
    active_profile_post_fetch_raw_aweme_ids_total: activeProfilePost.raw_aweme_ids_total,
    active_profile_post_fetch_accepted_targets_total: activeProfilePost.accepted_targets_total,
    active_profile_post_fetch_duplicate_drop_count: activeProfilePost.duplicate_drop_count,
    active_profile_post_fetch_invalid_drop_count: activeProfilePost.invalid_drop_count,
    active_profile_post_fetch_other_profile_drop_count: activeProfilePost.other_profile_drop_count,
    active_profile_post_fetch_favorite_endpoint_drop_count: activeProfilePost.favorite_endpoint_drop_count,
    active_profile_post_fetch_missing_aweme_id_count: activeProfilePost.missing_aweme_id_count,
    active_profile_post_fetch_per_page_raw_counts: activeProfilePost.per_page_raw_counts,
    active_profile_post_fetch_per_page_aweme_id_counts: activeProfilePost.per_page_aweme_id_counts,
    active_profile_post_fetch_per_page_accepted_counts: activeProfilePost.per_page_accepted_counts,
    active_profile_post_fetch_per_page_duplicate_drop_counts: activeProfilePost.per_page_duplicate_drop_counts,
    active_profile_post_fetch_per_page_missing_aweme_id_counts: activeProfilePost.per_page_missing_aweme_id_counts,
    active_profile_post_fetch_per_page_has_more: activeProfilePost.per_page_has_more,
    active_profile_post_fetch_per_page_cursor_present: activeProfilePost.per_page_cursor_present,
    active_profile_post_fetch_per_page_status_codes: activeProfilePost.per_page_status_codes,
    active_profile_post_fetch_per_page_stop_reasons: activeProfilePost.per_page_stop_reasons,
    active_profile_post_fetch_page_cap: numberFromDiagnostics(activeProfilePost.page_cap),
    active_profile_post_fetch_page_cap_hit_count: numberFromDiagnostics(activeProfilePost.page_cap_hit_count),
    active_profile_post_fetch_page_cap_hit_while_has_more_count: numberFromDiagnostics(activeProfilePost.page_cap_hit_while_has_more_count),
    active_profile_post_fetch_runtime_timeout_ms: numberFromDiagnostics(activeProfilePost.runtime_timeout_ms),
    active_profile_post_fetch_runtime_timeout_hit: yesNoUnknownValue22C12B(activeProfilePost.runtime_timeout_hit),
    active_profile_post_fetch_continuation_policy: typeof activeProfilePost.continuation_policy === "string" && activeProfilePost.continuation_policy
      ? activeProfilePost.continuation_policy
      : "none",
    active_profile_post_fetch_fallback_cycle_eligible: yesNoUnknownValue22C12B(activeProfilePost.fallback_cycle_eligible),
    active_profile_post_fetch_fallback_cycle_attempted: yesNoUnknownValue22C12B(activeProfilePost.fallback_cycle_attempted),
    active_profile_post_fetch_fallback_cycle_stop_reason: typeof activeProfilePost.fallback_cycle_stop_reason === "string" && activeProfilePost.fallback_cycle_stop_reason
      ? activeProfilePost.fallback_cycle_stop_reason
      : "none",
    active_profile_post_fetch_fallback_cycle_has_more_state: trueFalseUnknownValue22C12B(activeProfilePost.fallback_cycle_has_more_state),
    active_profile_post_fetch_fallback_cycle_request_count: numberFromDiagnostics(activeProfilePost.fallback_cycle_request_count),
    active_profile_post_fetch_fallback_cycle_batch_count: numberFromDiagnostics(activeProfilePost.fallback_cycle_batch_count),
    active_profile_post_fetch_error: typeof activeProfilePost.error === "string" && activeProfilePost.error ? activeProfilePost.error : "none",
    active_profile_post_fetch_response_shape: activeProfilePost.response_shape,
    active_profile_post_fetch_endpoint_variant_attempt_count: numberFromDiagnostics(activeProfilePost.endpoint_variant_attempt_count),
    active_profile_post_fetch_endpoint_variant_success: typeof activeProfilePost.endpoint_variant_success === "string" && activeProfilePost.endpoint_variant_success
      ? activeProfilePost.endpoint_variant_success
      : "none",
    active_profile_post_fetch_endpoint_attempt_samples: Array.isArray(activeProfilePost.endpoint_attempt_samples)
      ? activeProfilePost.endpoint_attempt_samples
      : [],
    active_profile_post_fetch_parser_route: typeof activeProfilePost.parser_route === "string" && activeProfilePost.parser_route
      ? activeProfilePost.parser_route
      : "none",
    active_profile_post_fetch_parser_routes_tried: Array.isArray(activeProfilePost.parser_routes_tried)
      ? activeProfilePost.parser_routes_tried
      : [],
    active_profile_post_fetch_parser_direct_routes_tried: Array.isArray(activeProfilePost.parser_direct_routes_tried)
      ? activeProfilePost.parser_direct_routes_tried
      : [],
    active_profile_post_fetch_parser_direct_match_count: numberFromDiagnostics(activeProfilePost.parser_direct_match_count),
    active_profile_post_fetch_parser_fallback_attempted: yesNoUnknownValue22C12B(activeProfilePost.parser_fallback_attempted),
    active_profile_post_fetch_parser_fallback_match_count: numberFromDiagnostics(activeProfilePost.parser_fallback_match_count),
    active_profile_post_fetch_parser_fallback_candidate_count: numberFromDiagnostics(activeProfilePost.parser_fallback_candidate_count),
    active_profile_post_fetch_parser_fallback_visited_nodes: numberFromDiagnostics(activeProfilePost.parser_fallback_visited_nodes),
    active_profile_post_fetch_effective_attempted: yesNoUnknownValue22C12B(activeProfilePost.effective_attempted),
    active_profile_post_fetch_effective_attempt_reason: typeof activeProfilePost.effective_attempt_reason === "string" && activeProfilePost.effective_attempt_reason
      ? activeProfilePost.effective_attempt_reason
      : "none",
    active_profile_post_template_warmup_attempted: yesNoUnknownValue22C12B(activeProfilePost.template_warmup_attempted),
    active_profile_post_template_warmup_attempt_count: numberFromDiagnostics(activeProfilePost.template_warmup_attempt_count),
    active_profile_post_template_warmup_applied_template: yesNoUnknownValue22C12B(activeProfilePost.template_warmup_applied_template),
    active_profile_post_template_warmup_stop_reason: typeof activeProfilePost.template_warmup_stop_reason === "string" && activeProfilePost.template_warmup_stop_reason
      ? activeProfilePost.template_warmup_stop_reason
      : "none",
    active_profile_post_template_found: yesNoUnknownValue22C12B(activeProfilePost.template_found),
    active_profile_post_template_source: typeof activeProfilePost.template_source === "string" && activeProfilePost.template_source
      ? activeProfilePost.template_source
      : "none",
    active_profile_post_template_endpoint_path: typeof activeProfilePost.template_endpoint_path === "string" && activeProfilePost.template_endpoint_path
      ? activeProfilePost.template_endpoint_path
      : "none",
    active_profile_post_template_query_keys: Array.isArray(activeProfilePost.template_query_keys)
      ? activeProfilePost.template_query_keys
      : [],
    active_profile_post_template_required_query_keys: Array.isArray(activeProfilePost.template_required_query_keys)
      ? activeProfilePost.template_required_query_keys
      : [],
    active_profile_post_template_required_query_keys_available: yesNoUnknownValue22C12B(activeProfilePost.template_required_query_keys_available),
    active_profile_post_template_missing_required_query_keys: Array.isArray(activeProfilePost.template_missing_required_query_keys)
      ? activeProfilePost.template_missing_required_query_keys
      : [],
    active_profile_post_template_secret_keys_present: yesNoUnknownValue22C12B(activeProfilePost.template_secret_keys_present),
    active_profile_post_template_secret_query_keys: Array.isArray(activeProfilePost.template_secret_query_keys)
      ? activeProfilePost.template_secret_query_keys
      : [],
    active_profile_post_fetch_response_status_code: typeof activeProfilePost.response_status_code === "number"
      ? Math.round(activeProfilePost.response_status_code)
      : typeof activeProfilePost.response_status_code === "string" && activeProfilePost.response_status_code.trim()
        ? activeProfilePost.response_status_code.trim()
        : "none",
    active_profile_post_fetch_response_status_msg: typeof activeProfilePost.response_status_msg === "string" && activeProfilePost.response_status_msg
      ? activeProfilePost.response_status_msg
      : "none",
    active_profile_post_fetch_response_top_level_keys: Array.isArray(activeProfilePost.response_top_level_keys)
      ? activeProfilePost.response_top_level_keys
      : [],
    active_profile_post_fetch_response_data_keys: Array.isArray(activeProfilePost.response_data_keys)
      ? activeProfilePost.response_data_keys
      : [],
    active_profile_post_fetch_response_result_keys: Array.isArray(activeProfilePost.response_result_keys)
      ? activeProfilePost.response_result_keys
      : [],
    active_profile_post_fetch_parser_path_counts: activeProfilePost.parser_path_counts && typeof activeProfilePost.parser_path_counts === "object" && !Array.isArray(activeProfilePost.parser_path_counts)
      ? activeProfilePost.parser_path_counts
      : {},
    active_profile_post_fetch_list_sample_keys: Array.isArray(activeProfilePost.list_sample_keys)
      ? activeProfilePost.list_sample_keys
      : [],
    active_profile_post_fetch_reject_reasons: Array.isArray(activeProfilePost.reject_reasons)
      ? activeProfilePost.reject_reasons
      : [],
    active_profile_post_template_sources_tried: Array.isArray(activeProfilePost.template_sources_tried) ? activeProfilePost.template_sources_tried : [],
    active_profile_post_template_source_selected: typeof activeProfilePost.template_source_selected === "string" && activeProfilePost.template_source_selected ? activeProfilePost.template_source_selected : "none",
    active_profile_post_template_cache_hit: yesNoUnknownValue22C12B(activeProfilePost.template_cache_hit),
    active_profile_post_fetch_tier_attempted: typeof activeProfilePost.fetch_tier_attempted === "string" && activeProfilePost.fetch_tier_attempted ? activeProfilePost.fetch_tier_attempted : "none",
    active_profile_post_fetch_tier_result: typeof activeProfilePost.fetch_tier_result === "string" && activeProfilePost.fetch_tier_result ? activeProfilePost.fetch_tier_result : "none",
    active_profile_post_fetch_tier_failure_reason: typeof activeProfilePost.fetch_tier_failure_reason === "string" && activeProfilePost.fetch_tier_failure_reason ? activeProfilePost.fetch_tier_failure_reason : "none",
    active_profile_post_fetch_status_non_zero_retryable: yesNoUnknownValue22C12B(activeProfilePost.status_non_zero_retryable),
    active_profile_post_fetch_status_non_zero_retry_count: numberFromDiagnostics(activeProfilePost.status_non_zero_retry_count),
    active_profile_post_fetch_last_non_zero_code: activeProfilePost.last_non_zero_code ?? "none",
    active_profile_post_fetch_last_non_zero_reason: typeof activeProfilePost.last_non_zero_reason === "string" && activeProfilePost.last_non_zero_reason ? activeProfilePost.last_non_zero_reason : "none"
  };
}

function derivePostProbeProductiveGate22C11B(probeResult: unknown, diagnostics: Record<string, unknown> = {}): PostProbeProductiveGateDerivation22C11B {
  const rawProbe = objectValue(probeResult) ?? objectValue(diagnostics.profile_dom_probe);
  const normalizedProbe = objectValue(diagnostics.normalized_profile_dom_probe) ?? objectValue(diagnostics.profile_dom_probe_summary);
  const sources: Array<{ name: "raw_probe" | "normalized_probe" | "flattened_diagnostics"; data: Record<string, unknown> }> = [
    ...(rawProbe ? [{ name: "raw_probe" as const, data: rawProbe }] : []),
    ...(normalizedProbe ? [{ name: "normalized_probe" as const, data: normalizedProbe }] : []),
    { name: "flattened_diagnostics", data: diagnostics }
  ];
  for (const source of sources) {
    const status = String(recordValue(source.data, "profileDomProbeStatus", "profile_dom_probe_status") ?? diagnostics.profile_dom_probe_status ?? (source.name === "raw_probe" ? "completed" : ""));
    const probeCompleted = status === "completed";
    const gridReady = booleanValue(recordValue(source.data, "profileGridReady", "profile_grid_ready", "profileGridFound", "profile_grid_found") ?? recordValue(diagnostics, "profileGridReady", "profile_grid_ready"));
    const awemeIdRaw = recordValue(source.data, "awemeIds", "aweme_ids") ?? recordValue(diagnostics, "awemeIds", "aweme_ids");
    const videoAnchorRaw = recordValue(source.data, "videoAnchors", "video_anchors") ?? recordValue(diagnostics, "videoAnchors", "video_anchors");
    const gridCardRaw = recordValue(source.data, "gridCards", "grid_cards") ?? recordValue(diagnostics, "gridCards", "grid_cards");
    const awemeIdCount = Math.max(numericValue(recordValue(source.data, "awemeIdCount", "aweme_id_count") ?? recordValue(diagnostics, "awemeIdCount", "aweme_id_count")), Array.isArray(awemeIdRaw) ? awemeIdRaw.length : 0);
    const videoAnchorCount = Math.max(numericValue(recordValue(source.data, "videoAnchorCount", "video_anchor_count") ?? recordValue(diagnostics, "videoAnchorCount", "video_anchor_count")), Array.isArray(videoAnchorRaw) ? videoAnchorRaw.length : 0);
    const gridCardCandidateCount = Math.max(numericValue(recordValue(source.data, "gridCardCandidateCount", "grid_card_candidate_count") ?? recordValue(diagnostics, "gridCardCandidateCount", "grid_card_candidate_count")), Array.isArray(gridCardRaw) ? gridCardRaw.length : 0);
    const emptyProfileDetected = booleanValue(recordValue(source.data, "emptyProfileDetected", "empty_profile_detected"));
    const loginWallDetected = booleanValue(recordValue(source.data, "loginWallDetected", "login_wall_detected", "loginRequired", "login_required"));
    const captchaDetected = booleanValue(recordValue(source.data, "captchaDetected", "captcha_detected", "abnormalTrafficDetected", "abnormal_traffic_detected"));
    const checkpointDetected = booleanValue(recordValue(source.data, "checkpointDetected", "checkpoint_detected", "accessDeniedDetected", "access_denied_detected"));
    const inputs = { probeStatus: status || null, gridReady, awemeIdCount, videoAnchorCount, gridCardCandidateCount, emptyProfileDetected, loginWallDetected, captchaDetected, checkpointDetected };
    if (!probeCompleted) continue;
    if (loginWallDetected || captchaDetected || checkpointDetected) return { gate: "blocked", source: source.name, reason: "checkpoint_detected", inputs };
    if (awemeIdCount > 0) return { gate: "productive", source: source.name, reason: "aweme_ids_present", inputs };
    if (videoAnchorCount > 0) return { gate: "productive", source: source.name, reason: "video_anchors_present", inputs };
    if (gridCardCandidateCount > 0) return { gate: "productive", source: source.name, reason: "grid_candidates_present", inputs };
    if (emptyProfileDetected) return { gate: "empty_profile", source: source.name, reason: "explicit_empty_profile", inputs };
    return { gate: "not_productive", source: source.name, reason: "no_candidates", inputs };
  }
  return { gate: "probe_missing", source: "flattened_diagnostics", reason: "probe_missing", inputs: { probeStatus: null, gridReady: false, awemeIdCount: 0, videoAnchorCount: 0, gridCardCandidateCount: 0, emptyProfileDetected: false, loginWallDetected: false, captchaDetected: false, checkpointDetected: false } };
}
let activeBackgroundScanProfileRunId: string | null = null;
let scanProfileWatchdogSequence22C11B = 0;

function scanRetryWaitDelayMs22C14B(nextRetryAt: string | null | undefined, nowMs = Date.now()): number | null {
  if (!nextRetryAt) return null;
  const target = Date.parse(nextRetryAt);
  if (!Number.isFinite(target)) return null;
  return Math.max(0, target - nowMs);
}

async function sleepScanRetryWait22C14B(delayMs: number): Promise<void> {
  await new Promise((resolve) => setTimeout(resolve, Math.max(0, delayMs)));
}

const EXTENSION_AUTH_TOKEN_STORAGE_KEY = "apiAuthToken";
const WEB_API_AUTH_TOKEN_STORAGE_KEY = "reup_douyin_api_auth_token";
const AUTH_SESSION_SYNC_VERSION_22C13A = "22C-13A-auth-session-sync";

chrome.runtime.onInstalled.addListener(() => {
  void chrome.storage.sync.set({ apiBaseUrl: "http://127.0.0.1:8000" });
});

chrome.runtime.onMessage.addListener((rawMessage, sender, rawSendResponse) => {
  const message = rawMessage as ExtensionMessage;
  const sendResponse = rawSendResponse as (response: ExtensionMessageResponse) => void;
  void handleMessage(message, sender)
    .then(sendResponse)
    .catch((error) => sendResponse({ ok: false, error: error instanceof Error ? error.message : "Background request failed." }));
  return true;
});

chrome.debugger?.onEvent?.addListener((source, method, params) => {
  const tabId = source.tabId;
  if (typeof tabId !== "number") return;
  void handleCdpEvent(tabId, method, params ?? {}).catch((error) => {
    const session = cdpSessions.get(tabId);
    if (session) session.last_error = error instanceof Error ? error.message : "cdp_event_failed";
  });
});

chrome.debugger?.onDetach?.addListener((source, reason) => {
  const tabId = source.tabId;
  if (typeof tabId !== "number") return;
  const session = cdpSessions.get(tabId);
  if (session) {
    session.attached = false;
    session.last_error = reason || null;
  }
});

chrome.tabs?.onRemoved?.addListener((tabId) => {
  if (cdpSessions.has(tabId)) cdpSessions.delete(tabId);
});

export async function handleMessage(message: ExtensionMessage, sender: unknown): Promise<ExtensionMessageResponse> {
  if (message.type === "DOUYIN_SCANNER_START_SCAN_PROFILE_22C11B" || message.type === "DOUYIN_SCANNER_START_SCAN_PROFILE") {
    const tabContext = message.tabContext ?? null;
    const scanRunId = `scan_profile_22C11B_${Date.now()}`;
    activeBackgroundScanProfileRunId = scanRunId;
    await persistCanonicalScanAccepted22C11B(scanRunId, tabContext);
    void runScanProfile22C11B({ scanRunId, tabContext, requestedAt: new Date().toISOString(), source: message.type }).catch((error) => console.error("[reup-douyin][scan-profile-22C11B]", error));
    return { ok: true, accepted: true, scanner_started: true, scanner_runtime_owner: "background", scan_run_id: scanRunId };
  }
  if (message.type === "REUP_DOUYIN_POST_BACKEND" && message.request) {
    const backendPost = await postToBackend(await withStoredAuthHeader(message.request));
    return backendPost.ok ? { ok: true, backend_post: backendPost } : { ok: false, backend_post: backendPost, error: backendPost.error_message || "Backend request failed." };
  }
  if (message.type === "REUP_DOUYIN_SYNC_AUTH_SESSION_22C13A") {
    return syncAuthSession22C13A(message.base_url ?? null);
  }
  if (message.type === "REUP_DOUYIN_CDP_START") {
    const tabId = await resolveActiveDouyinTabId(message.tab_id ?? senderTabId(sender));
    const status = await startCdpHarvest(tabId);
    return { ok: true, cdp_status: status };
  }
  if (message.type === "REUP_DOUYIN_CDP_STOP") {
    const tabId = message.tab_id ?? senderTabId(sender);
    if (typeof tabId !== "number") return { ok: true };
    await stopCdpHarvest(tabId, "operator_stopped");
    return { ok: true, cdp_status: statusForSession(cdpSessions.get(tabId) ?? null, tabId) };
  }
  if (message.type === "REUP_DOUYIN_CDP_STATUS") {
    const tabId = await resolveActiveDouyinTabId(message.tab_id ?? senderTabId(sender));
    return { ok: true, cdp_status: statusForSession(cdpSessions.get(tabId) ?? null, tabId) };
  }
  if (message.type === "REUP_DOUYIN_CDP_REFRESH_MODAL") {
    const tabId = await resolveActiveDouyinTabId(message.tab_id ?? senderTabId(sender));
    const status = await attachCdpAndReload(tabId);
    return { ok: true, cdp_status: status };
  }
  if (message.type === "REUP_DOUYIN_CDP_GET_AWEME") {
    const tabId = await resolveActiveDouyinTabId(message.tab_id ?? senderTabId(sender));
    const session = cdpSessions.get(tabId) ?? (await ensureCdpSession(tabId));
    const aweme = message.aweme_id ? session.awemeById.get(String(message.aweme_id).trim()) ?? null : null;
    return { ok: true, cdp_status: statusForSession(session, tabId), cdp_aweme: aweme };
  }
  if (message.type === "REUP_DOUYIN_CDP_DOM_SNAPSHOT") {
    const tabId = await resolveActiveDouyinTabId(message.tab_id ?? senderTabId(sender));
    const session = cdpSessions.get(tabId) ?? (await ensureCdpSession(tabId));
    const snapshot = await captureDomSnapshotRightRailPayload(session);
    return { ok: true, cdp_status: statusForSession(session, tabId), cdp_dom_snapshot: snapshot };
  }
  if (message.type === "REUP_DOUYIN_VISUAL_RIGHT_RAIL") {
    const tabId = await resolveActiveDouyinTabId(message.tab_id ?? senderTabId(sender));
    const session = cdpSessions.get(tabId) ?? (await ensureCdpSession(tabId));
    const visualRightRail = await captureVisualRightRailPayload(session);
    return { ok: true, cdp_status: statusForSession(session, tabId), visual_right_rail: visualRightRail };
  }
  if (message.type === "REUP_DOUYIN_CAPTURE_VISIBLE_TAB") {
    const dataUrl = await chrome.tabs.captureVisibleTab(null, { format: "png" });
    return { ok: true, screenshot_data_url: dataUrl };
  }
  if (message.type === "REUP_DOUYIN_CDP_RUNTIME_SCAN") {
    const tabId = await resolveActiveDouyinTabId(message.tab_id ?? senderTabId(sender));
    const session = cdpSessions.get(tabId) ?? (await ensureCdpSession(tabId));
    const aweme = message.aweme_id ? await scanRuntimeAweme(session, String(message.aweme_id).trim()) : null;
    return { ok: true, cdp_status: statusForSession(session, tabId), cdp_aweme: aweme };
  }
  if (message.type === "DOUYIN_SCANNER_SKIP_HYBRID_INCOMPLETE") {
    try {
      const backgroundRuntime = buildBackgroundHybridRuntime();
      await runSkipHybridUncollectableRemainder(backgroundRuntime);
      return { ok: true };
    } catch (error) {
      return { ok: false, error: error instanceof Error ? error.message : "skip_hybrid_incomplete_background_failed" };
    }
  }
  if (message.type === "DOUYIN_SCANNER_CLOSE_UNREACHABLE_TAIL_GAP") {
    try {
      const backgroundRuntime = buildBackgroundHybridRuntime();
      await runCloseUnreachableTailGap(backgroundRuntime);
      return { ok: true };
    } catch (error) {
      return { ok: false, error: error instanceof Error ? error.message : "close_unreachable_tail_gap_background_failed" };
    }
  }
  if (message.type === "DOUYIN_HYBRID_UNATTENDED_COLLECT_ALL") {
    try {
      const backgroundRuntime = buildBackgroundHybridRuntime();
      await runUnattendedHybridCollectAllRemaining(backgroundRuntime, (message.options ?? {}) as HybridNetworkCacheRunnerOptions);
      return { ok: true };
    } catch (error) {
      return { ok: false, error: error instanceof Error ? error.message : "hybrid_unattended_collect_background_failed" };
    }
  }
  if (message.type === "DOUYIN_HYBRID_NETWORK_CACHE_RUNNER") {
    try {
      const backgroundRuntime = buildBackgroundHybridRuntime();
      // MV3 lifecycle fix: DO NOT detach this long-running runner. The canonical
      // onMessage wrapper returns true while handleMessage's promise is pending,
      // so awaiting the runner here keeps Chrome's message channel open and gives
      // the service worker a real lifecycle owner. The previous fire-and-forget
      // version returned {ok:true} immediately; Chrome could then terminate the
      // detached worker at random points (ACK, step_2c, step_3, ...), silently
      // dropping in-flight promises with error:none and no catch block. Awaiting
      // is the only reliable no-permission keepalive for this message-triggered
      // job; the runner already writes progress/ACK to storage, so the popup can
      // still render progress while this response is pending.
      await runBatchCollectHybridNetworkCacheMode(backgroundRuntime, (message.options ?? {}) as HybridNetworkCacheRunnerOptions);
      return { ok: true };
    } catch (error) {
      return { ok: false, error: error instanceof Error ? error.message : "hybrid_runner_background_failed" };
    }
  }
  return { ok: false, error: "Unsupported extension message." };
}

export async function startCdpHarvest(tabId: number): Promise<CdpAwemeStatus> {
  const session = await ensureCdpSession(tabId);
  return statusForSession(session, tabId);
}

export async function stopCdpHarvest(tabId: number, reason = "stopped"): Promise<void> {
  const session = cdpSessions.get(tabId);
  if (!session) return;
  if (session.attached) {
    try {
      await chrome.debugger.detach({ tabId });
    } catch (error) {
      session.last_error = error instanceof Error ? error.message : reason;
    }
  }
  cdpSessions.delete(tabId);
}

async function ensureCdpSession(tabId: number): Promise<CdpSession> {
  const existing = cdpSessions.get(tabId);
  if (existing?.attached) return existing;
  const session: CdpSession = existing ?? createCdpSession(tabId);
  cdpSessions.set(tabId, session);
  try {
    await chrome.debugger.attach({ tabId }, session.debugger_version);
    session.attached = true;
    await chrome.debugger.sendCommand({ tabId }, "Network.enable");
    session.network_enabled = true;
    await chrome.debugger.sendCommand({ tabId }, "Runtime.enable");
    session.runtime_enabled = true;
    await chrome.debugger.sendCommand({ tabId }, "Page.enable");
    await chrome.debugger.sendCommand({ tabId }, "Accessibility.enable");
  } catch (error) {
    session.attached = false;
    session.last_error = error instanceof Error ? error.message : "cdp_attach_failed";
    throw error;
  }
  return session;
}

export async function handleCdpEvent(tabId: number, method: string, params: Record<string, unknown>): Promise<void> {
  const session = cdpSessions.get(tabId);
  if (!session?.attached) return;
  if (method === "Network.responseReceived") {
    const requestId = typeof params.requestId === "string" ? params.requestId : null;
    const response = params.response && typeof params.response === "object" ? (params.response as Record<string, unknown>) : null;
    const url = typeof response?.url === "string" ? response.url : null;
    if (requestId && url && isLikelyAwemeResponse(url)) session.responses.set(requestId, { requestId, url });
    return;
  }
  if (method === "Network.loadingFinished") {
    const requestId = typeof params.requestId === "string" ? params.requestId : null;
    const info = requestId ? session.responses.get(requestId) : null;
    if (!requestId || !info) return;
    session.response_count += 1;
    try {
      const body = await chrome.debugger.sendCommand<{ body?: string; base64Encoded?: boolean }>({ tabId }, "Network.getResponseBody", { requestId });
      const json = parseCdpResponseBodyJson(body.body ?? "", body.base64Encoded ?? false);
      if (json !== null) session.json_response_count += 1;
      const result = findExactAwemeCandidates(json, "", "cdp_network_aweme", info.url);
      session.candidate_aweme_count += result.stats.candidate_count;
      for (const candidate of collectAllAwemeCandidates(json, info.url)) cacheCandidate(session, candidate);
    } catch (error) {
      session.last_error = error instanceof Error ? error.message : "cdp_response_body_failed";
    } finally {
      session.responses.delete(requestId);
    }
  }
}

async function scanRuntimeAweme(session: CdpSession, awemeId: string): Promise<CdpAwemeEvidence | null> {
  const expression = `(() => {
    const targetId = ${JSON.stringify(awemeId)};
    const seen = new WeakSet();
    const roots = [window.__REUP_DOUYIN_NETWORK_CACHE__, window.__DOUYIN_AWEME_CACHE__];
    for (const key of Object.keys(window).filter((name) => /state|store|router|app|douyin|aweme|detail|video/i.test(name)).slice(0, 80)) {
      if (!/cookie|authorization|auth|token|secret|credential|password|passwd|session|header|csrf/i.test(key)) roots.push(window[key]);
    }
    const stack = roots.map((value) => ({ value, depth: 0 }));
    let count = 0;
    while (stack.length && count < 30000) {
      const current = stack.pop();
      if (!current || current.depth > 8) continue;
      const value = current.value;
      if (!value || typeof value !== "object" || seen.has(value)) continue;
      seen.add(value); count += 1;
      if (String(value.aweme_id || "").trim() === targetId && (value.statistics || value.video || value.create_time || value.desc || value.author)) return JSON.parse(JSON.stringify(value));
      for (const key of Object.keys(value).slice(0, 80)) {
        if (/cookie|authorization|auth|token|secret|credential|password|passwd|session|header|csrf/i.test(key)) continue;
        const child = value[key];
        if (!child || typeof child === "function") continue;
        if (Array.isArray(child)) child.slice(0, 100).forEach((entry) => stack.push({ value: entry, depth: current.depth + 1 }));
        else if (typeof child === "object") stack.push({ value: child, depth: current.depth + 1 });
      }
    }
    return null;
  })()`;
  const result = await chrome.debugger.sendCommand<{ result?: { value?: unknown } }>({ tabId: session.tabId }, "Runtime.evaluate", { expression, returnByValue: true, awaitPromise: false });
  const search = findExactAwemeCandidates(result.result?.value ?? null, awemeId, "cdp_runtime_aweme");
  const candidate = search.candidates[0] ?? null;
  if (!candidate) return null;
  session.runtime_exact_match_count += 1;
  cacheCandidate(session, candidate);
  return evidenceFromCandidate(candidate);
}

async function captureDomSnapshotRightRailPayload(session: CdpSession): Promise<CdpDomSnapshotPayload> {
  const debuggee = { tabId: session.tabId };
  const metrics = await chrome.debugger.sendCommand<{
    layoutViewport?: { clientWidth?: number; clientHeight?: number };
    visualViewport?: { clientWidth?: number; clientHeight?: number };
    contentSize?: { width?: number; height?: number };
  }>(debuggee, "Page.getLayoutMetrics");
  const viewportWidth = Math.round(metrics.visualViewport?.clientWidth ?? metrics.layoutViewport?.clientWidth ?? metrics.contentSize?.width ?? 0);
  const viewportHeight = Math.round(metrics.visualViewport?.clientHeight ?? metrics.layoutViewport?.clientHeight ?? metrics.contentSize?.height ?? 0);
  const snapshot = await chrome.debugger.sendCommand<{
    documents?: Array<{
      nodes?: { nodeName?: unknown[]; nodeValue?: unknown[]; backendNodeId?: number[] };
      layout?: { nodeIndex?: number[]; bounds?: number[][]; text?: unknown[] };
      strings?: string[];
    }>;
  }>(debuggee, "DOMSnapshot.captureSnapshot", {
    computedStyles: [],
    includeDOMRects: true,
    includePaintOrder: true
  });
  const textEntries: CdpDomSnapshotPayload["text_entries"] = [];
  for (const document of snapshot.documents ?? []) {
    const strings = document.strings ?? [];
    const layout = document.layout;
    const bounds = layout?.bounds ?? [];
    const nodeIndexes = layout?.nodeIndex ?? [];
    const layoutTexts = layout?.text ?? [];
    for (let index = 0; index < bounds.length; index += 1) {
      const rect = snapshotBounds(bounds[index]);
      const nodeIndex = typeof nodeIndexes[index] === "number" ? nodeIndexes[index] : null;
      const text = snapshotString(layoutTexts[index], strings) ?? snapshotString(document.nodes?.nodeValue?.[nodeIndex ?? -1], strings);
      if (!text || !rect) continue;
      textEntries.push({
        text,
        rect,
        node_index: nodeIndex ?? null,
        backend_node_id: nodeIndex != null ? document.nodes?.backendNodeId?.[nodeIndex] ?? null : null
      });
    }
  }
  return {
    viewport_width: viewportWidth,
    viewport_height: viewportHeight,
    text_entries: textEntries
  };
}

async function captureVisualRightRailPayload(session: CdpSession): Promise<VisualRightRailPayload> {
  const metrics = await chrome.debugger.sendCommand<Record<string, unknown>>({ tabId: session.tabId }, "Page.getLayoutMetrics");
  const viewport = extractViewportDimensions(metrics);
  const accessibilityTree = await captureAccessibilityTreePayload(session, viewport.width, viewport.height);
  const screenshotOcr = await captureScreenshotOcrPayload(viewport.width, viewport.height);
  return { accessibility_tree: accessibilityTree, screenshot_ocr: screenshotOcr };
}

function extractViewportDimensions(metrics: Record<string, unknown>): { width: number; height: number } {
  const visualViewport = metrics.visualViewport && typeof metrics.visualViewport === "object" ? (metrics.visualViewport as Record<string, unknown>) : null;
  const layoutViewport = metrics.layoutViewport && typeof metrics.layoutViewport === "object" ? (metrics.layoutViewport as Record<string, unknown>) : null;
  const contentSize = metrics.contentSize && typeof metrics.contentSize === "object" ? (metrics.contentSize as Record<string, unknown>) : null;
  const width = Math.round(numberOrNull(visualViewport?.clientWidth) ?? numberOrNull(layoutViewport?.clientWidth) ?? numberOrNull(contentSize?.width) ?? 0);
  const height = Math.round(numberOrNull(visualViewport?.clientHeight) ?? numberOrNull(layoutViewport?.clientHeight) ?? numberOrNull(contentSize?.height) ?? 0);
  return { width, height };
}

async function captureAccessibilityTreePayload(session: CdpSession, viewportWidth: number, viewportHeight: number): Promise<AccessibilityTreePayload> {
  const response = await chrome.debugger.sendCommand<{ nodes?: unknown[] }>({ tabId: session.tabId }, "Accessibility.getFullAXTree");
  const rawNodes = Array.isArray(response.nodes) ? response.nodes : [];
  const nodes: AccessibilityTreePayload["nodes"] = [];
  for (const rawNode of rawNodes) {
    if (!rawNode || typeof rawNode !== "object") continue;
    const record = rawNode as Record<string, unknown>;
    const name = axValueToString(record.name);
    const role = axValueToString(record.role);
    const ignored = typeof record.ignored === "boolean" ? record.ignored : null;
    const backendDOMNodeId = typeof record.backendDOMNodeId === "number" ? record.backendDOMNodeId : null;
    if (!name) continue;
    nodes.push({
      name,
      role,
      backend_dom_node_id: backendDOMNodeId,
      ignored,
      rect: backendDOMNodeId ? await resolveBackendNodeRect(session, backendDOMNodeId) : null
    });
  }
  return { viewport_width: viewportWidth, viewport_height: viewportHeight, nodes };
}

async function resolveBackendNodeRect(session: CdpSession, backendNodeId: number): Promise<ActionRailRectDiagnostic | null> {
  try {
    const resolved = await chrome.debugger.sendCommand<{ object?: { objectId?: string } }>({ tabId: session.tabId }, "DOM.resolveNode", { backendNodeId });
    const objectId = resolved.object?.objectId;
    if (!objectId) return null;
    const rectResult = await chrome.debugger.sendCommand<{ result?: { value?: unknown } }>({ tabId: session.tabId }, "Runtime.callFunctionOn", {
      objectId,
      returnByValue: true,
      functionDeclaration: "function(){ const r=this.getBoundingClientRect(); return { x:r.x, y:r.y, width:r.width, height:r.height }; }"
    });
    const value = rectResult.result?.value;
    if (!value || typeof value !== "object") return null;
    const rect = value as Record<string, unknown>;
    const x = numberOrNull(rect.x);
    const y = numberOrNull(rect.y);
    const width = numberOrNull(rect.width);
    const height = numberOrNull(rect.height);
    if (x == null || y == null || width == null || height == null) return null;
    return { x, y, width, height };
  } catch (error) {
    session.last_error = error instanceof Error ? error.message : "ax_rect_resolution_failed";
    return null;
  }
}

async function captureScreenshotOcrPayload(viewportWidth: number, viewportHeight: number): Promise<ScreenshotOcrPayload> {
  const cropRegion = {
    min_x: Math.max(0, viewportWidth - 170),
    max_x: Math.max(0, viewportWidth - 20),
    min_y: 90,
    max_y: Math.max(90, viewportHeight - 130),
    source: "viewport_right_band" as const
  };
  let rawText = "";
  try {
    const dataUrl = await chrome.tabs.captureVisibleTab(null, { format: "png" });
    rawText = await runLocalScreenshotOcr(dataUrl, cropRegion);
  } catch (error) {
    rawText = "";
  }
  return { viewport_width: viewportWidth, viewport_height: viewportHeight, raw_text: rawText, parsed_lines: rawText.split(/\r?\n/).map((line) => line.trim()).filter(Boolean), confidence: null, crop_region: cropRegion };
}

async function runLocalScreenshotOcr(dataUrl: string, cropRegion: { min_x: number; max_x: number; min_y: number; max_y: number }): Promise<string> {
  const maybeWorker = (globalThis as typeof globalThis & { Tesseract?: { recognize?: (...args: unknown[]) => Promise<unknown> } }).Tesseract;
  if (!maybeWorker?.recognize) return "";
  const result = await maybeWorker.recognize(dataUrl, "eng", { tessedit_char_whitelist: "0123456789.万wWkK" });
  const data = result && typeof result === "object" ? (result as { data?: { text?: unknown } }).data : null;
  return typeof data?.text === "string" ? data.text : "";
}

function axValueToString(value: unknown): string | null {
  if (typeof value === "string") return value;
  if (value && typeof value === "object") {
    const raw = (value as { value?: unknown }).value;
    return typeof raw === "string" || typeof raw === "number" ? String(raw) : null;
  }
  return null;
}

function numberOrNull(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function snapshotString(value: unknown, strings: string[]): string | null {
  if (typeof value === "string") return value;
  if (typeof value === "number") return strings[value] ?? null;
  if (Array.isArray(value) && typeof value[0] === "number") return strings[value[0]] ?? null;
  return null;
}

function snapshotBounds(value: unknown): { x: number; y: number; width: number; height: number } | null {
  if (!Array.isArray(value) || value.length < 4) return null;
  const [x, y, width, height] = value.map((entry) => (typeof entry === "number" && Number.isFinite(entry) ? entry : null));
  if (x == null || y == null || width == null || height == null) return null;
  return { x, y, width, height };
}

export async function attachCdpAndReload(tabId: number): Promise<CdpAwemeStatus> {
  const session = await ensureCdpSession(tabId);
  session.last_error = null;
  await chrome.debugger.sendCommand({ tabId }, "Page.reload", { ignoreCache: true });
  return statusForSession(session, tabId);
}

function createCdpSession(tabId: number): CdpSession {
  return {
    tabId,
    attached: false,
    debugger_version: "1.3",
    network_enabled: false,
    runtime_enabled: false,
    response_count: 0,
    json_response_count: 0,
    candidate_aweme_count: 0,
    exact_match_count: 0,
    runtime_exact_match_count: 0,
    last_matching_aweme_id: null,
    last_matching_response_url: null,
    last_error: null,
    responses: new Map(),
    awemeById: new Map()
  };
}

function collectAllAwemeCandidates(root: unknown, responseUrl: string): CdpAwemeCandidate[] {
  const exactIds = new Set<string>();
  const candidates: CdpAwemeCandidate[] = [];
  const probe = findExactAwemeCandidates(root, "__never_exact__", "cdp_network_aweme", responseUrl, { maxObjects: 30_000, timeoutMs: 650 });
  void probe;
  collectAwemeRecords(root, (record) => {
    const awemeId = String(record.aweme_id ?? "").trim();
    if (!awemeId || exactIds.has(awemeId)) return;
    exactIds.add(awemeId);
    const exact = findExactAwemeCandidates(record, awemeId, "cdp_network_aweme", responseUrl, { maxDepth: 1, maxObjects: 20, timeoutMs: 50 }).candidates[0];
    if (exact) candidates.push(exact);
  });
  return candidates;
}

function collectAwemeRecords(root: unknown, onRecord: (record: Record<string, unknown>) => void): void {
  const visited = new WeakSet<object>();
  const stack: Array<{ value: unknown; depth: number }> = [{ value: root, depth: 0 }];
  let count = 0;
  while (stack.length && count < 30_000) {
    const current = stack.pop();
    if (!current || current.depth > 8) continue;
    const value = current.value;
    if (!value || typeof value !== "object" || visited.has(value)) continue;
    visited.add(value); count += 1;
    const record = value as Record<string, unknown>;
    if (record.aweme_id && (record.statistics || record.video || record.create_time || record.desc || record.author)) onRecord(record);
    for (const [key, child] of Object.entries(record).slice(0, 80)) {
      if (/cookie|authorization|auth|token|secret|credential|password|passwd|session|header|csrf/i.test(key) || !child || typeof child === "function") continue;
      if (Array.isArray(child)) child.slice(0, 100).forEach((entry) => stack.push({ value: entry, depth: current.depth + 1 }));
      else if (typeof child === "object") stack.push({ value: child, depth: current.depth + 1 });
    }
  }
}

function cacheCandidate(session: CdpSession, candidate: CdpAwemeCandidate): void {
  session.exact_match_count += 1;
  session.last_matching_aweme_id = candidate.aweme_id;
  session.last_matching_response_url = candidate.response_url ?? session.last_matching_response_url;
  session.awemeById.set(candidate.aweme_id, evidenceFromCandidate(candidate));
  console.info("[reup-douyin][cdp-aweme]", "cdp_aweme_match_found", { aweme_id: candidate.aweme_id, source_used: candidate.source_used, response_url: candidate.response_url ?? null });
}

function evidenceFromCandidate(candidate: CdpAwemeCandidate): CdpAwemeEvidence {
  const evidence: CdpAwemeEvidence = {
    aweme_id: candidate.aweme_id,
    source_used: candidate.source_used,
    raw_aweme: candidate.raw_aweme,
    raw_aweme_keys: candidate.raw_aweme_keys,
    duration_seconds: candidate.mapped.duration_seconds,
    duration_text: candidate.mapped.duration_text,
    view_count: candidate.mapped.view_count,
    like_count: candidate.mapped.like_count,
    comment_count: candidate.mapped.comment_count,
    favorite_count: candidate.mapped.favorite_count,
    share_count: candidate.mapped.share_count,
    posted_text: candidate.mapped.posted_text,
    posted_at: candidate.mapped.posted_at
  };
  if (typeof candidate.response_url !== "undefined") evidence.response_url = candidate.response_url;
  return evidence;
}

function statusForSession(session: CdpSession | null, tabId: number | null): CdpAwemeStatus {
  return {
    attached: session?.attached ?? false,
    tab_id: tabId,
    debugger_version: session?.debugger_version ?? "1.3",
    network_enabled: session?.network_enabled ?? false,
    runtime_enabled: session?.runtime_enabled ?? false,
    response_count: session?.response_count ?? 0,
    json_response_count: session?.json_response_count ?? 0,
    candidate_aweme_count: session?.candidate_aweme_count ?? 0,
    exact_match_count: session?.exact_match_count ?? 0,
    runtime_exact_match_count: session?.runtime_exact_match_count ?? 0,
    last_matching_aweme_id: session?.last_matching_aweme_id ?? null,
    last_matching_response_url: session?.last_matching_response_url ?? null,
    last_error: session?.last_error ?? null
  };
}

async function resolveDouyinTabRecordForBackground(preferredTabId?: number | null, preferredUrl?: string | null): Promise<{ id?: number; url?: string | null; title?: string; windowId?: number; active?: boolean; highlighted?: boolean; lastAccessed?: number }> {
  if (typeof preferredTabId === "number" && isSupportedDouyinUrl(preferredUrl ?? "")) {
    return { id: preferredTabId, url: preferredUrl ?? null };
  }
  const [current] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (current?.id && isSupportedDouyinUrl(current.url ?? "")) return current;
  const [focused] = await chrome.tabs.query({ active: true, lastFocusedWindow: true } as never);
  if (focused?.id && isSupportedDouyinUrl(focused.url ?? "")) return focused;
  const candidates = [
    ...(await chrome.tabs.query({ url: "https://www.douyin.com/*" })),
    ...(await chrome.tabs.query({ url: "https://*.douyin.com/*" }))
  ].filter((tab, index, all) => tab.id && isSupportedDouyinUrl(tab.url ?? "") && all.findIndex((candidate) => candidate.id === tab.id) === index) as Array<{ id?: number; url?: string | null; title?: string; active?: boolean; highlighted?: boolean; lastAccessed?: number }>;
  if (candidates.length === 0) {
    if (current) return current;
    return preferredUrl ? { url: preferredUrl } : {};
  }
  const preferredProfileId = preferredUrl ? profileIdentifierFromUrl(preferredUrl) : null;
  if (preferredProfileId) {
    const profileMatch = candidates.find((tab) => profileIdentifierFromUrl(tab.url ?? "") === preferredProfileId);
    if (profileMatch?.id) return profileMatch;
  }
  const picked = candidates.find((tab) => tab.active || tab.highlighted)
    ?? candidates.sort((a, b) => (b.lastAccessed ?? 0) - (a.lastAccessed ?? 0))[0];
  return picked ?? {};
}

async function resolveActiveDouyinTabId(preferredTabId?: number | null): Promise<number> {
  const tab = await resolveDouyinTabRecordForBackground(preferredTabId ?? null, null);
  if (!tab?.id || !isSupportedDouyinUrl(tab.url ?? "")) {
    throw new Error("No active supported Douyin tab found.");
  }
  return tab.id;
}

type BackgroundScanProfileTabContext22C11B = { tabId?: number | null; url?: string | null; title?: string | null; windowId?: number | null } | null;

const HOT_PATH_DIAGNOSTIC_SAMPLE_LIMITS_22C14B: Record<string, number> = {
  active_profile_post_fetch_endpoint_attempt_samples: 2,
  minimal_scan_active_profile_post_fetch_endpoint_attempt_samples_22C12B: 2,
  active_profile_post_fetch_parser_routes_tried: 4,
  minimal_scan_active_profile_post_fetch_parser_routes_tried_22C12B: 4,
  active_profile_post_fetch_parser_direct_routes_tried: 4,
  minimal_scan_active_profile_post_fetch_parser_direct_routes_tried_22C12B: 4,
  scan_round_traces: 6,
  interaction_debug_trace: 8,
  pagination_debug_trace: 8,
  api_pagination_per_page_raw_counts: 160,
  api_pagination_per_page_raw_aweme_id_counts: 160,
  api_pagination_per_page_returned_target_counts: 160,
  api_pagination_per_page_accepted_counts: 160,
  api_pagination_per_page_unique_new_counts: 160,
  api_pagination_per_page_duplicate_counts: 160,
  api_pagination_per_page_cursor_values: 160,
  api_pagination_per_page_cursor_present_flags: 160,
  api_pagination_per_page_has_more_flags: 160,
  api_pagination_per_page_status_codes: 160,
  api_pagination_per_page_parser_routes: 160,
  api_pagination_per_page_persisted_totals: 160
};

function hotPathDiagnosticArrayLimit22C14B(key: string): number | null {
  if (key in HOT_PATH_DIAGNOSTIC_SAMPLE_LIMITS_22C14B) return HOT_PATH_DIAGNOSTIC_SAMPLE_LIMITS_22C14B[key] ?? null;
  const lower = key.toLowerCase();
  if (lower.includes("endpoint") && lower.includes("sample")) return 2;
  if (lower.includes("parser") && lower.includes("routes")) return 4;
  if (lower.includes("scan_round") || lower.includes("interaction") || lower.includes("pagination")) return 8;
  return null;
}

type CanonicalScanProfile22C11BContext = {
  scanRunId: string;
  tabContext: BackgroundScanProfileTabContext22C11B;
  requestedAt: string;
  source: string;
};

function estimateStorageBytes22C11B(value: unknown): number {
  try {
    return new TextEncoder().encode(JSON.stringify(value)).length;
  } catch {
    return Number.POSITIVE_INFINITY;
  }
}

function sanitizeDiagnosticValue22C11B(value: unknown, depth = 0): unknown {
  if (value == null || typeof value === "number" || typeof value === "boolean") return value;
  if (typeof value === "string") {
    return value.length > STORAGE_COMPACT_DIAGNOSTIC_MAX_STRING_LENGTH_22C13C
      ? `${value.slice(0, STORAGE_COMPACT_DIAGNOSTIC_MAX_STRING_LENGTH_22C13C)}…`
      : value;
  }
  if (typeof value === "bigint") return Number(value);
  if (typeof value === "function") return "[omitted_function]";
  if (typeof value === "symbol") return "[omitted_symbol]";
  if (depth >= STORAGE_COMPACT_DIAGNOSTIC_MAX_DEPTH_22C13C) return "[omitted_depth_limit]";
  if (Array.isArray(value)) {
    return value.map((entry) => sanitizeDiagnosticValue22C11B(entry, depth + 1));
  }
  if (!value || typeof value !== "object") return String(value);
  const record = value as Record<string, unknown>;
  const entries = Object.entries(record);
  const compact: Record<string, unknown> = {};
  for (const [key, nested] of entries.slice(0, STORAGE_COMPACT_DIAGNOSTIC_MAX_KEYS_22C13C)) {
    if (typeof key !== "string" || !key.trim()) continue;
    compact[key] = sanitizeDiagnosticValue22C11B(nested, depth + 1);
  }
  if (entries.length > STORAGE_COMPACT_DIAGNOSTIC_MAX_KEYS_22C13C) {
    compact.__omitted_keys_count_22C13C = entries.length - STORAGE_COMPACT_DIAGNOSTIC_MAX_KEYS_22C13C;
  }
  return compact;
}

function sanitizeScannerDiagnostics22C11B(diagnostics: Record<string, unknown> | null | undefined): Record<string, unknown> {
  const source = diagnostics ?? {};
  const sourceEntries = Object.entries(source);
  const sanitized: Record<string, unknown> = {};
  const stickyKeys = [
    "diagnostics_channel",
    "diagnostics_channel_isolated",
    "extension_runtime_build_id",
    "background_runtime_build_id",
    "runtime_build_id_consistent",
    "extension_build_timestamp",
    "lastScannerAction",
    "lastScannerResult",
    "lastScannerError",
    "scanStop",
    "scan_stop",
    "scan_stop_authoritative",
    "scan_stop_authority_source",
    "scan_stop_authority_version",
    "scan_stop_authority_migrated",
    "expected_gap_recovery_checked",
    "expected_gap_recovery_sources_checked",
    "expected_gap_recovery_unrecoverable_reason",
    "expected_gap_recovery_tail_candidates",
    "expected_gap_recovery_tail_added",
    "final_gap_reconciliation_attempted",
    "final_gap_reconciliation_sources_checked",
    "final_gap_recovered_count",
    "final_gap_unrecovered_count",
    "final_gap_unrecovered_reason",
    "final_gap_cursor_summary",
    "final_gap_active_fetch_count",
    "final_gap_passive_profile_post_count",
    "final_gap_dom_anchor_count",
    "final_gap_dedupe_drop_count",
    "final_gap_invalid_drop_count",
    "scan_progress_update_seq",
    "scan_progress_updated_at",
    "scan_progress_delivery_channel",
    "scan_progress_discovered",
    "scan_progress_expected",
    "scan_progress_remaining",
    "scan_progress_pages",
    "scan_progress_requests",
    "scan_progress_status_code",
    "scan_progress_phase_label",
    "scan_job_status",
    "scan_job_retry_count",
    "scan_job_next_retry_at",
    "scan_job_last_error",
    "scan_job_pages_fetched",
    "scan_job_page_count",
    "scan_job_request_count",
    "scan_job_total_discovered",
    "scan_job_total_persisted",
    "scan_job_duplicate_or_existing_count",
    "scan_job_page_budget",
    "scan_job_stop_reason",
    "scan_job_has_more_at_stop",
    "scan_mode",
    "scan_mode_visible_scroll_required",
    "scan_mode_scroll_policy",
    "api_pagination_attempted",
    "api_pagination_page_count",
    "api_pagination_request_count",
    "api_pagination_total_raw_targets",
    "api_pagination_total_accepted_targets",
    "api_pagination_total_persisted_targets",
    "api_pagination_total_persisted",
    "api_pagination_expected",
    "api_pagination_remaining",
    "api_pagination_duplicate_or_existing_count",
    "api_pagination_final_has_more",
    "api_pagination_has_more_final",
    "api_pagination_final_cursor",
    "api_pagination_stop_reason",
    "current_run_found_count",
    "persisted_total_count",
    "display_mode",
    "active_profile_post_fetch_response_shape",
    "active_profile_post_fetch_error",
    "active_profile_post_fetch_endpoint_attempt_samples",
    "active_profile_post_fetch_endpoint_variant_attempt_count",
    "active_profile_post_fetch_endpoint_variant_success",
    "active_profile_post_fetch_response_status_code",
    "active_profile_post_fetch_response_status_msg",
    "active_profile_post_fetch_response_top_level_keys",
    "active_profile_post_fetch_response_data_keys",
    "active_profile_post_fetch_response_result_keys",
    "active_profile_post_fetch_parser_route",
    "active_profile_post_fetch_parser_path_counts",
    "active_profile_post_fetch_parser_routes_tried",
    "active_profile_post_fetch_parser_direct_routes_tried",
    "active_profile_post_fetch_parser_direct_match_count",
    "active_profile_post_fetch_parser_fallback_attempted",
    "active_profile_post_fetch_parser_fallback_match_count",
    "active_profile_post_fetch_parser_fallback_candidate_count",
    "active_profile_post_fetch_parser_fallback_visited_nodes",
    "active_profile_post_fetch_list_sample_keys",
    "active_profile_post_fetch_reject_reasons",
    "active_profile_post_fetch_stop_reason",
    "active_profile_post_fetch_not_attempted_reason",
    "active_profile_post_template_found",
    "active_profile_post_template_required_query_keys_available",
    "expected_count_finalization_gate_active_profile_post_meaningful_attempt_22C13B",
    "expected_count_finalization_gate_active_profile_post_effective_attempt_reason_22C13B",
    "expected_count_gate_meaningful_active_fetch",
    "expected_count_gate_active_fetch_reason",
    "expected_count_gate_dom_only_convergence_allowed",
    "active_profile_post_template_source",
    "active_profile_post_template_endpoint_path",
    "active_profile_post_template_query_keys",
    "active_profile_post_template_required_query_keys",
    "active_profile_post_template_missing_required_query_keys",
    "active_profile_post_template_secret_keys_present",
    "active_profile_post_template_secret_query_keys",
    "expected_count_finalization_gate_dom_only_convergence_detected_22C13B",
    "expected_count_finalization_gate_dom_only_convergence_allowed_22C13B",
    "network_post_continuation_likely_22C13B",
    "network_collection_stop_reason_effective",
    "network_post_exhausted_signal_by_probe_22C12B",
    "network_post_exhausted_signal_by_has_more_state_22C12B",
    "network_post_exhausted_signal_by_stop_reason_22C12B",
    "network_post_exhausted_evidence_gate_passed_22C12B",
    "scan_completeness_gate_result",
    "scan_completeness_gate_reason",
    "scan_completeness_expected_count",
    "scan_completeness_found_count",
    "scan_completeness_missing_count",
    "scan_completeness_active_fetch_meaningful",
    "scan_completeness_dom_only_fallback",
    "scan_completeness_ready_blocked",
    "profileScanReady",
    "profile_scan_completion_ratio",
    "missing_profile_video_count",
    "over_collected_count",
    "count_delta",
    "count_reconciliation_state",
    "active_works_tab_filter_result",
    "scan_finalization_result",
    "scan_finalized_at",
    "scan_health_verdict",
    "scan_health_verdict_reason",
    "scan_health_required_user_action",
    "displayed_profile_count",
    "displayed_profile_count_source",
    "displayed_profile_count_raw_text",
    "api_raw_count",
    "api_unique_count",
    "api_has_more_final",
    "collectable_count",
    "persisted_count",
    "secondary_recovery_attempted",
    "unavailable_or_unlisted_count",
    "count_semantics_status",
    "count_semantics_reason",
    "terminal_small_gap_reason",
    "expected_gap_count",
    "expected_gap_ratio",
    "expected_gap_small_threshold_count",
    "expected_gap_small_threshold_ratio",
    "terminal_small_gap_reclassified",
    "final_gap_count",
    "final_gap_reason",
    "final_gap_classification",
    "final_gap_evidence",
    "final_gap_other_profile_drop_count",
    "expected_count",
    "expected_count_source",
    "expected_count_selector",
    "expected_count_raw_text",
    "expected_count_semantics_verified",
    "api_exhausted_has_more_false",
    "secondary_gap_probe_attempted",
    "secondary_gap_probe_unavailable_reason",
    "secondary_gap_probe_sources",
    "secondary_dom_candidate_count",
    "secondary_dom_new_candidate_count",
    "secondary_passive_network_candidate_count",
    "secondary_passive_network_new_candidate_count",
    "secondary_recovered_count",
    "final_gap_count_before_secondary_probe",
    "final_gap_count_after_secondary_probe",
    "secondary_duplicate_drop_count",
    "secondary_invalid_drop_count",
    "secondary_other_profile_drop_count",
    "api_pages_fetched_total",
    "api_requests_total",
    "api_raw_items_total",
    "api_raw_aweme_ids_total",
    "api_unique_aweme_ids_total",
    "api_duplicate_aweme_ids_total",
    "api_targets_returned_to_background_total",
    "background_targets_received_total",
    "background_targets_after_validation_total",
    "background_duplicate_drop_total",
    "background_invalid_drop_total",
    "background_other_profile_drop_total",
    "repository_write_input_total",
    "repository_existing_before_total",
    "repository_new_inserted_total",
    "repository_duplicate_existing_total",
    "repository_total_after",
    "scan_source_ledger",
    "scan_source_ledger_22C11B",
    "queue_source_mode",
    "queue_authority_locked",
    "queue_authority_mode",
    "queue_authority_reason",
    "queue_authority_health",
    "queue_authority_fallback_used",
    "scan_fallback_used",
    "scan_fallback_original_active_fetch_error",
    "scan_fallback_candidate_total_count",
    "active_profile_post_response_status_code",
    "active_profile_post_recovery_attempted",
    "active_profile_post_recovery_result",
    "active_profile_post_recovery_reason",
    "active_profile_post_non_zero_status_retryable",
    "queue_authority_source_mix_checked",
    "queue_authority_non_active_queue_source_count",
    "queue_authority_non_active_target_source_count",
    "post_scan_backend_reconciliation_ran",
    "post_scan_backend_reconciliation_status",
    "post_scan_backend_reconciliation_endpoint",
    "post_scan_backend_reconciliation_profile_identifier",
    "post_scan_backend_reconciliation_used_capture_inbox_card_source",
    "post_scan_backend_captured_count",
    "post_scan_backend_ready_count",
    "post_scan_backend_duplicate_count",
    "post_scan_backend_failed_count",
    "post_scan_backend_incomplete_count",
    "post_scan_new_count",
    "post_scan_queue_count",
    "post_scan_counter_snapshot_applied",
    "post_scan_counter_snapshot_source",
    "tail_reconcile_attempted",
    "tail_reconcile_candidates",
    "tail_reconcile_added",
    "tail_reconcile_rejected",
    "tail_reconcile_reason",
    "expected_gap_recovery_checked",
    "expected_gap_recovery_sources_checked",
    "expected_gap_recovery_unrecoverable_reason",
    "final_gap_reconciliation_attempted",
    "final_gap_reconciliation_result",
    "final_gap_recovered_count",
    "final_gap_unrecovered_count",
    "final_gap_dom_anchor_count",
    "final_gap_passive_profile_post_count",
    "final_gap_missing_count_before_reconcile",
    "final_gap_missing_count_after_reconcile",
    "final_gap_terminal_has_more",
    "api_pagination_raw_items_total",
    "api_pagination_raw_aweme_ids_total",
    "api_pagination_unique_aweme_ids_total",
    "api_pagination_accepted_targets_total",
    "api_pagination_persisted_targets_total",
    "api_pagination_duplicate_drop_count",
    "api_pagination_invalid_drop_count",
    "api_pagination_other_profile_drop_count",
    "api_pagination_favorite_endpoint_drop_count",
    "api_pagination_empty_or_missing_aweme_id_count",
    "api_pagination_repository_write_input_count",
    "api_pagination_repository_write_total_after",
    "api_pagination_repository_new_inserted_total",
    "api_pagination_repository_duplicate_existing_total",
    "api_pagination_first_page_raw_count",
    "api_pagination_last_page_raw_count",
    "api_pagination_last_page_accepted_count",
    "api_pagination_last_page_persisted_delta",
    "api_pagination_per_page_raw_counts",
    "api_pagination_per_page_raw_aweme_id_counts",
    "api_pagination_per_page_returned_target_counts",
    "api_pagination_per_page_accepted_counts",
    "api_pagination_per_page_unique_new_counts",
    "api_pagination_per_page_duplicate_counts",
    "api_pagination_per_page_cursor_values",
    "api_pagination_per_page_cursor_present_flags",
    "api_pagination_per_page_has_more_flags",
    "api_pagination_per_page_status_codes",
    "api_pagination_per_page_parser_routes",
    "api_pagination_per_page_persisted_totals",
    "large_profile_mode",
    "profile_queue_total_count",
    "persisted_total_count",
    "scan_total_found",
    "scan_total_expected",
    "active_source_terminal_policy",
    "active_source_degraded_fallback_policy",
    "canonical_lock_release_ran",
    "canonical_lock_release_reason",
    "scan_total_missing",
    "queue_window_size",
    "queue_window_offset",
    "queue_total_persisted",
    "queue_total_visible",
    "large_profile_storage_backend",
    "large_profile_storage_degraded",
    "large_profile_storage_degraded_reason",
    "collect_cursor",
    "last_processed_aweme_id",
    "last_checkpoint_at",
    "chunk_processed_count",
    "chunk_total_count"
  ] as const;
  const stickySet = new Set<string>(stickyKeys);

  for (const key of stickyKeys) {
    if (!(key in source)) continue;
    const value = source[key];
    const lower = key.toLowerCase();
    if (lower.includes("screenshot") || lower.includes("base64") || lower.includes("blob") || lower.includes("html")) {
      sanitized[`${key}_omitted`] = true;
      continue;
    }
    sanitized[key] = sanitizeDiagnosticValue22C11B(value);
  }

  let includedCount = Object.keys(sanitized).length;
  for (const [key, value] of sourceEntries) {
    if (includedCount >= STORAGE_COMPACT_DIAGNOSTIC_MAX_KEYS_22C13C) break;
    if (stickySet.has(key) || key in sanitized) continue;
    const lower = key.toLowerCase();
    if (lower.includes("screenshot") || lower.includes("base64") || lower.includes("blob") || lower.includes("html")) {
      sanitized[`${key}_omitted`] = true;
      includedCount += 1;
      continue;
    }
    const sampleLimit = Array.isArray(value) ? hotPathDiagnosticArrayLimit22C14B(key) : null;
    sanitized[key] = sampleLimit == null ? sanitizeDiagnosticValue22C11B(value) : sanitizeDiagnosticValue22C11B((value as unknown[]).slice(0, sampleLimit));
    if (sampleLimit != null && (value as unknown[]).length > sampleLimit) sanitized[`${key}_omitted_count_22C14B`] = (value as unknown[]).length - sampleLimit;
    includedCount += 1;
  }

  if (sourceEntries.length > STORAGE_COMPACT_DIAGNOSTIC_MAX_KEYS_22C13C) {
    sanitized.diagnostics_omitted_key_count_22C13C = sourceEntries.length - STORAGE_COMPACT_DIAGNOSTIC_MAX_KEYS_22C13C;
  }
  return sanitized;
}

function canonicalScanDiagnostics22C11B(scanRunId: string, stage: string, patch: Record<string, unknown> = {}): Record<string, unknown> {
  const terminalLockDiagnostics = scanStagePriority22C14D(stage) >= 100 || typeof patch.scan_finalization_result === "string" || typeof patch.scan_finalized_at === "string"
    ? {
      terminal_write_lock_active: "yes",
      terminal_write_lock_run_id: scanRunId
    }
    : {};
  // 22C-14I build identity diagnostics are generated at build time so background scan writes can prove Chrome loaded the current service worker dist.
  return {
    traceVersion: SCAN_PROFILE_BACKGROUND_TRACE_VERSION,
    extension_runtime_build_id: EXTENSION_RUNTIME_BUILD_ID,
    background_runtime_build_id: BACKGROUND_RUNTIME_BUILD_ID,
    runtime_build_id_consistent: EXTENSION_RUNTIME_BUILD_ID === BACKGROUND_RUNTIME_BUILD_ID ? "yes" : "no",
    extension_build_timestamp: EXTENSION_BUILD_TIMESTAMP,
    scanner_runtime_version: SCAN_PROFILE_BACKGROUND_TRACE_VERSION,
    state_machine_version: SCAN_PROFILE_BACKGROUND_TRACE_VERSION,
    runtime_authority_version: SCAN_PROFILE_BACKGROUND_TRACE_VERSION,
    diagnostics_runtime_version: SCAN_PROFILE_BACKGROUND_TRACE_VERSION,
    controller_runtime_version: SCAN_PROFILE_BACKGROUND_CONTROLLER_VERSION,
    scan_controller_version: SCAN_PROFILE_BACKGROUND_CONTROLLER_VERSION,
    scan_action_trace_version: SCAN_PROFILE_BACKGROUND_TRACE_VERSION,
    canonical_storage_version: SCAN_PROFILE_BACKGROUND_TRACE_VERSION,
    storage_budget_guard_enabled: "yes",
    scan_run_id: scanRunId,
    scan_stage_current: stage,
    ...terminalLockDiagnostics,
    active_scan_profile_engine: "minimal_active_works_grid_scanner_22C11B",
    canonical_orchestrator_entered: "yes",
    old_scan_profile_paths_deleted: "yes",
    old_scan_profile_paths_deleted_or_unreachable: "yes",
    reset_buttons_isolated: "yes",
    ...sanitizeScannerDiagnostics22C11B(patch)
  };
}

type CanonicalScanDiagnosticsChannels22C11B = {
  scanAuthorityDiagnostics: Record<string, unknown>;
  runtimeDebugDiagnostics: Record<string, unknown>;
};

function splitCanonicalScanDiagnosticsChannels22C11B(diagnostics: Record<string, unknown>): CanonicalScanDiagnosticsChannels22C11B {
  const sanitized = sanitizeScannerDiagnostics22C11B(diagnostics);
  return {
    scanAuthorityDiagnostics: {
      ...sanitized,
      diagnostics_channel: "scan_authority_diagnostics",
      diagnostics_channel_isolated: "yes"
    },
    runtimeDebugDiagnostics: {
      ...sanitized,
      diagnostics_channel: "runtime_debug_diagnostics",
      diagnostics_channel_isolated: "yes"
    }
  };
}

async function safeSetScannerStorage22C11B(payload: Record<string, unknown>, options: { stage: string; compact?: (payload: Record<string, unknown>) => Record<string, unknown> }): Promise<{ estimatedBytes: number; result: "success" | "success_after_compaction" }> {
  const firstBytes = estimateStorageBytes22C11B(payload);
  const firstPayload = firstBytes <= SCAN_PROFILE_STORAGE_BUDGET_BYTES_22C11B ? payload : options.compact?.(payload) ?? payload;
  const secondBytes = estimateStorageBytes22C11B(firstPayload);
  try {
    await chrome.storage.local.set(firstPayload);
    return { estimatedBytes: secondBytes, result: firstPayload === payload ? "success" : "success_after_compaction" };
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    if (/quota|kQuotaBytes/i.test(message)) throw new Error("canonical_storage_quota_exceeded_after_compaction");
    throw error;
  }
}

function diagnosticRecordByChannel22C14C(value: unknown, channel: "scan_authority_diagnostics" | "runtime_debug_diagnostics"): Record<string, unknown> {
  if (!value || typeof value !== "object") return {};
  const record = value as Record<string, unknown>;
  return record.diagnostics_channel === channel ? record : {};
}

function scanAuthorityDiagnostics22C14D(state: WholeProfileHarvestState): Record<string, unknown> {
  const profile = diagnosticRecordByChannel22C14C(state.profile_scan.diagnostics, "scan_authority_diagnostics");
  const verify = diagnosticRecordByChannel22C14C(state.verify.diagnostics, "scan_authority_diagnostics");
  return Object.keys(verify).length > 0 ? { ...profile, ...verify } : profile;
}

function scanStagePriority22C14D(stage: unknown): number {
  const value = typeof stage === "string" ? stage.toLowerCase() : "";
  if (/scan_finished|finished|success|failed|terminal|complete|verified/.test(value)) return 100;
  if (/finaliz/.test(value)) return 90;
  if (/retry_wait|running|checkpoint|network_probe|dom_probe|scan/.test(value)) return 50;
  if (/cleanup|start|accepted|resolving/.test(value)) return 30;
  return 10;
}

function scanStateIsTerminal22C14D(state: WholeProfileHarvestState, authority: Record<string, unknown> = scanAuthorityDiagnostics22C14D(state)): boolean {
  return state.phase === "scan_finished"
    || state.status === "verified"
    || state.status === "failed"
    || state.profile_scan.status === "success"
    || state.profile_scan.status === "failed"
    || state.verify.status === "success"
    || state.verify.status === "failed"
    || typeof authority.scan_finalization_result === "string"
    || typeof authority.scan_finalized_at === "string"
    || scanStagePriority22C14D(authority.scan_stage_current) >= 100;
}

function scanAuthorityWriteRejection22C14D(state: WholeProfileHarvestState, incoming: { scanRunId: string; stage: string; at: string; source: string; terminal?: boolean }): Record<string, unknown> | null {
  const authority = scanAuthorityDiagnostics22C14D(state);
  const currentRunId = typeof authority.scan_run_id === "string" ? authority.scan_run_id : state.run_id ?? state.scan_job.scan_job_id ?? null;
  const currentUpdatedAt = typeof state.updated_at === "string" ? state.updated_at : typeof state.scan_job.updated_at === "string" ? state.scan_job.updated_at : null;
  const currentStage = typeof authority.scan_stage_current === "string" ? authority.scan_stage_current : typeof state.phase === "string" ? state.phase : null;
  const currentFinalizationResult = typeof authority.scan_finalization_result === "string" ? authority.scan_finalization_result : null;
  const currentTerminalSuccess = scanStateIsTerminal22C14D(state, authority) && (state.status === "verified" || state.workflow.scan.status === "success" || state.scan_job.status === "completed" || currentFinalizationResult === "success" || currentFinalizationResult === "completed_with_warning");
  const incomingTerminalFailure = incoming.terminal === true && (/failed|exception|missing|zero_verified|not_ready|unverified/i.test(incoming.stage) || incoming.source.includes("failCanonicalScanProfile22C11B"));
  const sameRunTerminalRegression = Boolean(currentRunId && currentRunId === incoming.scanRunId && scanStateIsTerminal22C14D(state, authority) && !incoming.terminal && scanStagePriority22C14D(incoming.stage) < 100);
  const sameRunTerminalFailureOverwrite = Boolean(currentRunId && currentRunId === incoming.scanRunId && currentTerminalSuccess && incomingTerminalFailure);
  const olderRunOverwrite = Boolean(currentRunId && currentRunId !== incoming.scanRunId && state.workflow.active_task !== "scan_profile");
  const olderTimestamp = Boolean(currentUpdatedAt && incoming.at < currentUpdatedAt);
  const lowerPriorityStage = Boolean(currentRunId && currentRunId === incoming.scanRunId && currentStage && scanStagePriority22C14D(currentStage) >= 90 && scanStagePriority22C14D(incoming.stage) < scanStagePriority22C14D(currentStage));
  if (!sameRunTerminalRegression && !sameRunTerminalFailureOverwrite && !olderRunOverwrite && !olderTimestamp && !lowerPriorityStage) return null;
  return {
    diagnostics_channel: "runtime_debug_diagnostics",
    diagnostics_channel_isolated: "yes",
    terminal_write_lock_active: sameRunTerminalRegression || sameRunTerminalFailureOverwrite || lowerPriorityStage ? "yes" : "no",
    terminal_write_lock_run_id: sameRunTerminalRegression || sameRunTerminalFailureOverwrite || lowerPriorityStage ? currentRunId ?? incoming.scanRunId : "none",
    terminal_write_rejected_source: incoming.source,
    terminal_write_rejected_stage: incoming.stage,
    stale_update_rejected: "yes",
    stale_update_source: incoming.source,
    stale_update_run_id: incoming.scanRunId,
    stale_update_stage: incoming.stage,
    stale_update_current_run_id: currentRunId ?? "none",
    stale_update_current_stage: currentStage ?? "none",
    stale_update_current_updated_at: currentUpdatedAt ?? "none",
    stale_update_incoming_updated_at: incoming.at,
    stale_update_reason: sameRunTerminalRegression ? "terminal_state_blocks_non_terminal_write" : sameRunTerminalFailureOverwrite ? "same_run_terminal_success_blocks_failed_overwrite" : olderRunOverwrite ? "older_scan_run_id" : olderTimestamp ? "older_updated_at" : "lower_priority_than_terminal_stage"
  };
}

async function persistRuntimeDebugStaleRejection22C14D(state: WholeProfileHarvestState, rejection: Record<string, unknown>, stage: string, at: string): Promise<void> {
  const currentDebug = diagnosticRecordByChannel22C14C(state.debug.last_response_summary, "runtime_debug_diagnostics");
  const debug = sanitizeScannerDiagnostics22C11B({ ...currentDebug, ...rejection, updated_at: at });
  await safeSetScannerStorage22C11B({
    [WHOLE_PROFILE_HARVEST_STATE_KEY]: prepareWholeProfileHarvestStateForStorage22C11B({
      ...state,
      debug: { ...state.debug, last_request_summary: debug, last_response_summary: debug }
    })
  }, { stage });
}

/**
 * Keep Hybrid-required metric fields when compacting queue evidence for storage.
 * Stripping to only aweme_id/source_url made large-profile collect depend entirely
 * on live network_cache (recent window only) — production: 500 items selected,
 * all skipped_pending with src=["profile_repository"] and every metric missing.
 */
function compactProfileCardEvidenceForHybridStorage(
  item: WholeProfileHarvestQueueItem,
  state: WholeProfileHarvestState
): Record<string, unknown> {
  const base = item.profile_card_evidence && typeof item.profile_card_evidence === "object"
    ? item.profile_card_evidence as Record<string, unknown>
    : {};
  return buildHybridProfileCardEvidence(base, [{
    aweme_id: item.aweme_id,
    source_url: item.source_url,
    profile_url: state.profile_url,
    discovered_at: state.updated_at,
    discovery_source: "network_profile_post_22C11B"
  }]);
}

function prepareWholeProfileHarvestStateForStorage22C11B(state: WholeProfileHarvestState): WholeProfileHarvestState {
  const profileAuthoritySource = diagnosticRecordByChannel22C14C(state.profile_scan.diagnostics, "scan_authority_diagnostics");
  const verifyAuthoritySource = diagnosticRecordByChannel22C14C(state.verify.diagnostics, "scan_authority_diagnostics");
  const authoritySource = Object.keys(verifyAuthoritySource).length > 0 ? { ...profileAuthoritySource, ...verifyAuthoritySource } : profileAuthoritySource;
  const runtimeSource = diagnosticRecordByChannel22C14C(state.debug.last_response_summary, "runtime_debug_diagnostics");
  const compactAuthorityDiagnostics = sanitizeScannerDiagnostics22C11B(authoritySource);
  const compactRuntimeDiagnostics = sanitizeScannerDiagnostics22C11B(runtimeSource);
  const compactQueue = state.harvest.queue
    .slice(0, STORAGE_COMPACT_QUEUE_LIMIT_22C13C)
    .map((item, index) => ({
      index: item.index ?? index + 1,
      aweme_id: item.aweme_id,
      capture_status: item.capture_status,
      status: item.status,
      attempts: item.attempts ?? 0,
      checkpoint_sequence: item.checkpoint_sequence ?? null,
      extraction_result: item.extraction_result ?? null,
      last_error: item.last_error ?? null,
      capture_inbox_item_id: item.capture_inbox_item_id ?? null,
      source_url: item.source_url,
      profile_card_evidence: compactProfileCardEvidenceForHybridStorage(item, state)
    }));
  const compactTargetDetails = state.profile_scan.target_details.slice(0, compactQueue.length);
  const compactHarvestResults = state.harvest.results
    .slice(-STORAGE_COMPACT_RESULTS_LIMIT_22C13C)
    .map((result, index) => ({
      ...result,
      index: index + 1,
      extraction_payload: null
    }));
  const compactCollectTrace = Array.isArray(state.harvest.collect_trace)
    ? state.harvest.collect_trace.slice(-STORAGE_COMPACT_TRACE_LIMIT_22C13C).map((entry) => ({ ...entry, details: null }))
    : [];
  const compactDebugTrace = Array.isArray(state.debug.trace)
    ? state.debug.trace.slice(-STORAGE_COMPACT_DEBUG_TRACE_LIMIT_22C13C).map((entry) => ({ ...entry, details: null }))
    : [];
  return {
    ...state,
    profile_scan: { ...state.profile_scan, target_details: compactTargetDetails, diagnostics: compactAuthorityDiagnostics },
    verify: { ...state.verify, target_details: state.verify.target_details.slice(0, compactQueue.length), diagnostics: compactAuthorityDiagnostics },
    classification: { ...state.classification, targets: state.classification.targets.slice(0, compactQueue.length).map((target) => ({ ...target, thumbnail_url: null, caption: null })), diagnostics: sanitizeScannerDiagnostics22C11B(state.classification.diagnostics as Record<string, unknown> | undefined) },
    harvest: {
      ...state.harvest,
      queue: compactQueue,
      queue_preview: buildCollectQueuePreviewFromQueue(compactQueue, compactTargetDetails),
      results: compactHarvestResults,
      collect_trace: compactCollectTrace
    },
    debug: { ...state.debug, trace: compactDebugTrace, last_request_summary: compactRuntimeDiagnostics, last_response_summary: compactRuntimeDiagnostics }
  };
}

async function persistCanonicalScanAccepted22C11B(scanRunId: string, tabContext: BackgroundScanProfileTabContext22C11B): Promise<void> {
  const at = new Date().toISOString();
  const stored = await chrome.storage.local.get(WHOLE_PROFILE_HARVEST_STATE_KEY);
  const existing = (stored[WHOLE_PROFILE_HARVEST_STATE_KEY] as WholeProfileHarvestState | undefined) ?? createWholeProfileHarvestIdleState(at);
  const requestedProfileUrl = typeof tabContext?.url === "string" && tabContext.url.trim() ? tabContext.url.trim() : null;
  const profileIdentifier = requestedProfileUrl ? profileIdentifierFromUrl(requestedProfileUrl) : null;
  const diagnostics = canonicalScanDiagnostics22C11B(scanRunId, "canonical_start", {
    requested_tab_id: tabContext?.tabId ?? null,
    requested_tab_url: tabContext?.url ?? null,
    lastScannerAction: "scan_profile",
    lastScannerResult: "running",
    lastScannerError: "none",
    profileScanReady: "no",
    profile_queue_total_count: 0,
    scan_job_total_persisted: 0,
    queue_total_persisted: 0,
    expected_profile_video_count: null,
    canonical_scan_requested_at: at
  });
  const diagnosticsChannels = splitCanonicalScanDiagnosticsChannels22C11B(diagnostics);
  const resetScanJob = {
    ...createPersistentScanJobRecord(at),
    scan_job_id: scanRunId,
    profile_identifier: profileIdentifier,
    status: "running" as const,
    expected_count: null,
    total_persisted: 0,
    total_discovered: 0,
    page_count: 0,
    request_count: 0,
    started_at: at,
    updated_at: at
  };
  const next: WholeProfileHarvestState = appendWholeProfileTrace({
    ...existing,
    profile_url: (requestedProfileUrl ? normalizeDouyinProfileUrl(requestedProfileUrl) : null) ?? existing.profile_url,
    source_url: (requestedProfileUrl ? normalizeDouyinProfileUrl(requestedProfileUrl) : null) ?? existing.source_url,
    status: "verifying",
    phase: "canonical_scan_starting",
    run_id: scanRunId,
    workflow: {
      ...existing.workflow,
      scan: { status: "running", started_at: at, updated_at: at, completed_at: null, last_error: null },
      classification: { ...existing.workflow.classification, status: "idle", started_at: null, updated_at: at, completed_at: null, last_error: null },
      active_task: "scan_profile",
      action_lock: "scan_profile"
    },
    layer: { ...existing.layer, profile_scan_ready: false, harvest_ready: false },
    scan_job: resetScanJob,
    profile_scan: { ...existing.profile_scan, status: "running", raw_candidate_count: 0, accepted_target_count: 0, rejected_target_count: 0, targets: [], target_details: [], rejected_candidates_sample: [], scan_rounds: 0, stop_reason: null, diagnostics: diagnosticsChannels.scanAuthorityDiagnostics },
    verify: { ...existing.verify, status: "running", started_at: at, completed_at: null, raw_candidate_count: 0, accepted_target_count: 0, rejected_target_count: 0, verified_target_count: 0, targets: [], target_details: [], rejected_candidates_sample: [], scan_rounds: 0, stop_reason: null, diagnostics: diagnosticsChannels.scanAuthorityDiagnostics },
    post_scan_counter_snapshot: null,
    harvest: { ...existing.harvest, queue: [], queue_preview: [], planned_total: 0, pending: 0, current_index: 0, current_aweme_id: null },
    classification: emptyClassificationState(),
    debug: {
      ...existing.debug,
      last_action_clicked: "scan_profile",
      last_action_result: "running",
      last_action_error: null,
      last_action_started_at: at,
      last_action_finished_at: null,
      active_task: "scan_profile",
      busy_source: "scan_profile",
      last_request_summary: diagnosticsChannels.runtimeDebugDiagnostics,
      last_response_summary: diagnosticsChannels.runtimeDebugDiagnostics
    },
    last_error: null,
    updated_at: at
  }, "scan_profile.22C11B.accepted", "Scan Profile accepted.", diagnosticsChannels.scanAuthorityDiagnostics, at);
  await safeSetScannerStorage22C11B({ [WHOLE_PROFILE_HARVEST_STATE_KEY]: prepareWholeProfileHarvestStateForStorage22C11B(next) }, { stage: "canonical_start" });
}

async function cleanupObsoleteScanStorage22C11B(scanRunId: string): Promise<Record<string, unknown>> {
  const at = new Date().toISOString();
  const stored = await chrome.storage.local.get(WHOLE_PROFILE_HARVEST_STATE_KEY);
  const state = (stored[WHOLE_PROFILE_HARVEST_STATE_KEY] as WholeProfileHarvestState | undefined) ?? null;
  if (!state) return { pre_scan_storage_cleanup_result: "no_existing_state", pre_scan_storage_cleanup_at: at };
  const diagnostics = canonicalScanDiagnostics22C11B(scanRunId, "pre_scan_storage_cleanup", {
    pre_scan_storage_cleanup_result: "compacted_existing_scan_state",
    pre_scan_storage_cleanup_at: at,
    pre_scan_cleanup_preserved_calibration: state.calibration ? "yes" : "no"
  });
  const diagnosticsChannels = splitCanonicalScanDiagnosticsChannels22C11B(diagnostics);
  const cleaned = prepareWholeProfileHarvestStateForStorage22C11B({
    ...state,
    profile_scan: { ...state.profile_scan, targets: [], target_details: [], rejected_candidates_sample: [], diagnostics: diagnosticsChannels.scanAuthorityDiagnostics },
    verify: { ...state.verify, targets: [], target_details: [], rejected_candidates_sample: [], diagnostics: diagnosticsChannels.scanAuthorityDiagnostics },
    harvest: { ...state.harvest, queue: [], queue_preview: [], planned_total: 0, pending: 0, current_index: 0, current_aweme_id: null },
    classification: emptyClassificationState(),
    debug: { ...state.debug, last_request_summary: diagnosticsChannels.runtimeDebugDiagnostics, last_response_summary: diagnosticsChannels.runtimeDebugDiagnostics },
    updated_at: at
  });
  await safeSetScannerStorage22C11B({ [WHOLE_PROFILE_HARVEST_STATE_KEY]: cleaned }, { stage: "pre_scan_storage_cleanup" });
  return diagnostics;
}

async function persistCanonicalScanDiagnostics22C11B(scanRunId: string, stage: string, patch: Record<string, unknown>): Promise<void> {
  const at = new Date().toISOString();
  const stored = await chrome.storage.local.get(WHOLE_PROFILE_HARVEST_STATE_KEY);
  const state = (stored[WHOLE_PROFILE_HARVEST_STATE_KEY] as WholeProfileHarvestState | undefined) ?? createWholeProfileHarvestIdleState(at);
  const rejection = scanAuthorityWriteRejection22C14D(state, { scanRunId, stage, at, source: "background.persistCanonicalScanDiagnostics22C11B", terminal: scanStagePriority22C14D(stage) >= 100 });
  if (rejection) return persistRuntimeDebugStaleRejection22C14D(state, rejection, stage, at);
  const current = scanAuthorityDiagnostics22C14D(state);
  let sanitizedCurrent = sanitizeScannerDiagnostics22C11B(current);
  const stateRunId = typeof state.run_id === "string" ? state.run_id.trim() : "";
  const jobRunId = typeof state.scan_job.scan_job_id === "string" ? state.scan_job.scan_job_id.trim() : "";
  const activeRunId = stateRunId || jobRunId;
  if (activeRunId && scanRunId !== activeRunId) {
    sanitizedCurrent = {
      ...sanitizedCurrent,
      expected_profile_video_count: null,
      scan_progress_expected: null,
      current_run_found_count: null,
      current_run_new_inserted_total: null,
      current_run_effective_progress_total: null,
      scan_progress_discovered: null,
      scan_job_total_persisted: null
    };
  }
  const mergedPatch = withCanonicalActiveProfilePostDiagnostics22C12B({
    ...sanitizedCurrent,
    ...sanitizeScannerDiagnostics22C11B(patch),
    updated_at: at
  });
  const diagnostics = canonicalScanDiagnostics22C11B(scanRunId, stage, mergedPatch);
  const diagnosticsChannels = splitCanonicalScanDiagnosticsChannels22C11B(diagnostics);
  const next = prepareWholeProfileHarvestStateForStorage22C11B({
    ...state,
    phase: stage,
    profile_scan: { ...state.profile_scan, diagnostics: diagnosticsChannels.scanAuthorityDiagnostics },
    verify: { ...state.verify, diagnostics: diagnosticsChannels.scanAuthorityDiagnostics },
    debug: { ...state.debug, last_request_summary: diagnosticsChannels.runtimeDebugDiagnostics, last_response_summary: diagnosticsChannels.runtimeDebugDiagnostics },
    updated_at: at
  });
  await safeSetScannerStorage22C11B({ [WHOLE_PROFILE_HARVEST_STATE_KEY]: next }, { stage });
}

async function failCanonicalScanProfile22C11B(scanRunId: string, errorCode: string, stage: string, patch: Record<string, unknown> = {}): Promise<void> {
  const at = new Date().toISOString();
  const stored = await chrome.storage.local.get(WHOLE_PROFILE_HARVEST_STATE_KEY);
  const state = (stored[WHOLE_PROFILE_HARVEST_STATE_KEY] as WholeProfileHarvestState | undefined) ?? createWholeProfileHarvestIdleState(at);
  const rejection = scanAuthorityWriteRejection22C14D(state, { scanRunId, stage, at, source: "background.failCanonicalScanProfile22C11B", terminal: true });
  if (rejection) return persistRuntimeDebugStaleRejection22C14D(state, rejection, stage, at);
  const current = scanAuthorityDiagnostics22C14D(state);
  const currentRunPersisted = state.scan_job.scan_job_id === scanRunId ? state.scan_job.total_persisted : 0;
  const terminalFailForRun = state.scan_job.scan_job_id === scanRunId;
  const clearStalePersistedCounters = terminalFailForRun;
  const diagnostics = canonicalScanDiagnostics22C11B(scanRunId, "scan_finished", withCanonicalActiveProfilePostDiagnostics22C12B({
    ...current,
    ...(clearStalePersistedCounters ? {
      scan_job_total_persisted: 0,
      queue_total_persisted: 0,
      profile_queue_total_count: 0,
      count_semantics_status: null,
      final_cumulative_collectable_count: 0,
      collectable_count: 0
    } : {}),
    ...patch,
    lastScannerResult: "failed",
    lastScannerError: errorCode,
    scan_failure_stage: stage,
    canonical_finalizer_version: "22C-11B",
    canonical_finalizer_ran: "yes",
    canonical_terminal_state: "failed",
    scan_finalization_result: "failed",
    scan_finalized_at: at,
    canonical_lock_release_ran: "yes",
    canonical_lock_release_reason: errorCode,
    profileScanReady: "no"
  }));
  const diagnosticsChannels = splitCanonicalScanDiagnosticsChannels22C11B(diagnostics);
  const failedState = appendWholeProfileTrace({
      ...state,
      status: "failed",
      phase: "scan_finished",
      post_scan_counter_snapshot: clearStalePersistedCounters ? null : state.post_scan_counter_snapshot,
      scan_job: clearStalePersistedCounters ? {
        ...state.scan_job,
        status: "failed",
        total_persisted: 0,
        updated_at: at,
        completed_at: at,
        last_error: errorCode
      } : state.scan_job,
      harvest: clearStalePersistedCounters ? {
        ...state.harvest,
        queue: [],
        queue_preview: [],
        pending: 0,
        planned_total: 0,
        current_index: 0,
        current_aweme_id: null,
        updated: 0,
        skipped: 0,
        failed: 0,
        flushed: 0,
        processed: 0,
        checkpoint_count: 0,
        resume_from_index: null,
        results: [],
        failure_summary: null
      } : state.harvest,
      workflow: {
        ...state.workflow,
        scan: { ...state.workflow.scan, status: "failed", updated_at: at, completed_at: at, last_error: errorCode },
        active_task: null,
        action_lock: null
      },
      profile_scan: { ...state.profile_scan, status: "failed", diagnostics: diagnosticsChannels.scanAuthorityDiagnostics },
      verify: { ...state.verify, status: "failed", completed_at: at, diagnostics: diagnosticsChannels.scanAuthorityDiagnostics },
      debug: {
        ...state.debug,
        last_action_result: "failed",
        last_action_error: errorCode,
        last_action_finished_at: at,
        active_task: null,
        busy_source: null,
        last_request_summary: diagnosticsChannels.runtimeDebugDiagnostics,
        last_response_summary: diagnosticsChannels.runtimeDebugDiagnostics
      },
      last_error: `${errorCode}: Canonical Scan Profile failed.`,
      updated_at: at
    }, "scan_profile.22C11B.failed", errorCode, diagnosticsChannels.scanAuthorityDiagnostics, at);
  const latestStored = await chrome.storage.local.get(WHOLE_PROFILE_HARVEST_STATE_KEY).catch(() => ({} as Record<string, unknown>));
  const latestState = (latestStored[WHOLE_PROFILE_HARVEST_STATE_KEY] as WholeProfileHarvestState | undefined) ?? state;
  const latestRejection = scanAuthorityWriteRejection22C14D(latestState, { scanRunId, stage, at, source: "background.failCanonicalScanProfile22C11B.latest_guard", terminal: true });
  if (latestRejection) return persistRuntimeDebugStaleRejection22C14D(latestState, latestRejection, `${stage}.latest_guard`, at);
  await safeSetScannerStorage22C11B({ [WHOLE_PROFILE_HARVEST_STATE_KEY]: prepareWholeProfileHarvestStateForStorage22C11B(failedState) }, { stage });
}

function awemeIdFromCanonicalDetail(detail: unknown, fallback: string | null): string | null {
  const record = detail && typeof detail === "object" ? detail as Record<string, unknown> : {};
  const raw = record.aweme_id ?? record.awemeId ?? record.id ?? fallback;
  const value = typeof raw === "string" || typeof raw === "number" ? String(raw).trim() : "";
  return /^\d{8,}$/.test(value) ? value : null;
}

function canonicalDetailString(detail: Record<string, unknown>, ...keys: string[]): string | null {
  for (const key of keys) {
    const value = detail[key];
    if (typeof value === "string" && value.trim()) return value.trim();
  }
  return null;
}

function canonicalScannerResponseDiagnostics22C11B(response: unknown): Record<string, unknown> {
  const record = response && typeof response === "object" ? response as Record<string, unknown> : null;
  return {
    canonical_scanner_response_seen: record ? "yes" : "no",
    canonical_scanner_response_ok: record ? record.ok === true ? "yes" : "no" : "no",
    canonical_scanner_response_keys: record ? Object.keys(record).slice(0, 40) : [],
    canonical_scanner_response_parse_error: record ? null : "canonical_scanner_response_missing"
  };
}

type CanonicalFallbackCandidate22C14F = {
  aweme_id: string;
  source_url: string;
  profile_url: string;
  caption: string | null;
  thumbnail_url: string | null;
  discovery_source: string;
  source_rank: number;
};

function validAwemeId22C14F(value: unknown): string | null {
  const text = typeof value === "string" || typeof value === "number" ? String(value).trim() : "";
  return /^\d{8,22}$/.test(text) ? text : null;
}

function fallbackCandidateDetail22C14F(value: unknown, profileUrl: string, discoverySource: string, sourceRank: number): CanonicalFallbackCandidate22C14F | null {
  const record = value && typeof value === "object" ? value as Record<string, unknown> : {};
  const fromUrl = (...keys: string[]): string | null => {
    for (const key of keys) {
      const raw = record[key];
      if (typeof raw !== "string") continue;
      const match = raw.match(/(?:video|modal)\/(\d{8,22})/i) ?? raw.match(/[?&](?:modal_id|aweme_id|awemeId)=(\d{8,22})/i);
      if (match?.[1]) return match[1];
    }
    return null;
  };
  const awemeId = validAwemeId22C14F(record.aweme_id ?? record.awemeId ?? record.id ?? record.modal_id ?? record.modalId) ?? fromUrl("source_url", "video_url", "href", "url");
  if (!awemeId) return null;
  const sourceUrl = canonicalDetailString(record, "source_url", "video_url", "href", "url") ?? `https://www.douyin.com/video/${awemeId}`;
  return {
    aweme_id: awemeId,
    source_url: sourceUrl,
    profile_url: canonicalDetailString(record, "profile_url") ?? profileUrl,
    caption: canonicalDetailString(record, "caption", "title", "desc", "text_sample"),
    thumbnail_url: canonicalDetailString(record, "thumbnail_url", "cover_url", "image_url"),
    discovery_source: discoverySource,
    source_rank: sourceRank
  };
}

function fallbackCandidateString22C14F(value: unknown, profileUrl: string, discoverySource: string, sourceRank: number): CanonicalFallbackCandidate22C14F | null {
  if (value && typeof value === "object") return fallbackCandidateDetail22C14F(value, profileUrl, discoverySource, sourceRank);
  const raw = typeof value === "string" || typeof value === "number" ? String(value).trim() : "";
  const awemeId = validAwemeId22C14F(raw) ?? (raw.match(/(?:video|modal)\/(\d{8,22})/i) ?? raw.match(/[?&](?:modal_id|aweme_id|awemeId)=(\d{8,22})/i))?.[1] ?? null;
  if (!awemeId) return null;
  return { aweme_id: awemeId, source_url: `https://www.douyin.com/video/${awemeId}`, profile_url: profileUrl, caption: null, thumbnail_url: null, discovery_source: discoverySource, source_rank: sourceRank };
}

function collectCanonicalFallbackCandidates22C14F(diagnostics: Record<string, unknown>, profileUrl: string): { candidates: CanonicalFallbackCandidate22C14F[]; diagnostics: Record<string, unknown> } {
  const groups: Array<{ key: string; source: string; rank: number; value: unknown }> = [
    { key: "network_profile_post_targets", source: "network_profile_post_fallback_22C14F", rank: 1, value: diagnostics.network_profile_post_targets },
    { key: "profile_dom_probe_video_anchors", source: "dom_video_anchor_fallback_22C14F", rank: 2, value: diagnostics.profile_dom_probe_video_anchors },
    { key: "videoAnchors", source: "dom_video_anchor_fallback_22C14F", rank: 2, value: diagnostics.videoAnchors },
    { key: "tail_reconcile_candidates", source: "dom_tail_reconcile_fallback_22C14F", rank: 2, value: diagnostics.tail_reconcile_candidates },
    { key: "tail_reconcile_candidate_ids", source: "dom_tail_reconcile_fallback_22C14F", rank: 2, value: diagnostics.tail_reconcile_candidate_ids },
    { key: "profile_dom_probe_aweme_ids", source: "dom_aweme_id_fallback_22C14F", rank: 2, value: diagnostics.profile_dom_probe_aweme_ids },
    { key: "awemeIds", source: "dom_aweme_id_fallback_22C14F", rank: 2, value: diagnostics.awemeIds },
    { key: "verified_target_details", source: "accepted_scanner_candidate_fallback_22C14F", rank: 3, value: diagnostics.verified_target_details },
    { key: "verified_targets", source: "accepted_scanner_candidate_fallback_22C14F", rank: 3, value: diagnostics.verified_targets }
  ];
  const byAweme = new Map<string, CanonicalFallbackCandidate22C14F>();
  const sourceCounts: Record<string, number> = {};
  let invalidCount = 0;
  for (const group of groups) {
    const entries = Array.isArray(group.value) ? group.value : [];
    sourceCounts[group.key] = entries.length;
    for (const entry of entries) {
      const candidate = fallbackCandidateString22C14F(entry, profileUrl, group.source, group.rank);
      if (!candidate) {
        invalidCount += 1;
        continue;
      }
      const existing = byAweme.get(candidate.aweme_id);
      if (!existing || candidate.source_rank < existing.source_rank) byAweme.set(candidate.aweme_id, candidate);
    }
  }
  const candidates = Array.from(byAweme.values()).sort((left, right) => left.source_rank - right.source_rank);
  return { candidates, diagnostics: { scan_fallback_candidate_source_counts: sourceCounts, scan_fallback_candidate_invalid_count: invalidCount, scan_fallback_candidate_total_count: candidates.length } };
}

function buildCanonicalFallbackAdapter22C14F(diagnostics: Record<string, unknown>, profileUrl: string, at: string): ReturnType<typeof adaptCanonicalVerifiedTargets22C11B> | null {
  const fallback = collectCanonicalFallbackCandidates22C14F(diagnostics, profileUrl);
  if (fallback.candidates.length === 0) return null;
  const response = {
    ok: true,
    verified_targets: fallback.candidates.map((candidate) => candidate.aweme_id),
    verified_target_details: fallback.candidates.map((candidate) => ({ aweme_id: candidate.aweme_id, source_url: candidate.source_url, profile_url: candidate.profile_url, caption: candidate.caption, thumbnail_url: candidate.thumbnail_url, discovery_source: candidate.discovery_source, extraction_source: candidate.discovery_source })),
    diagnostics
  } as ExtensionMessageResponse;
  const adapted = adaptCanonicalVerifiedTargets22C11B(response, profileUrl, at);
  return { ...adapted, diagnostics: { ...adapted.diagnostics, ...fallback.diagnostics, scan_fallback_used: "yes", scan_fallback_reason: diagnostics.scan_job_last_error ?? diagnostics.active_profile_post_fetch_stop_reason ?? "active_profile_post_unusable", scan_fallback_original_active_fetch_error: diagnostics.scan_job_last_error ?? diagnostics.active_profile_post_fetch_stop_reason ?? null } };
}

function adaptCanonicalVerifiedTargets22C11B(response: ExtensionMessageResponse, profileUrl: string, at: string): {
  targetDetails: WholeProfileHarvestTargetDetail[];
  queue: WholeProfileHarvestQueueItem[];
  targets: string[];
  diagnostics: Record<string, unknown>;
} {
  const responseDiagnostics = response.diagnostics && typeof response.diagnostics === "object"
    ? response.diagnostics as Record<string, unknown>
    : {};
  const queueBuilderName = "scan_queue_adapter_22C11B";
  const rawTargets = Array.isArray(response.verified_targets) ? response.verified_targets.map((value) => String(value)) : [];
  const rawDetails = Array.isArray(response.verified_target_details) ? response.verified_target_details : [];
  const detailsByAweme = new Map<string, Record<string, unknown>>();
  let detailDuplicateCount = 0;
  let detailInvalidCount = 0;
  rawDetails.forEach((detail, index) => {
    const record = detail && typeof detail === "object" ? detail as Record<string, unknown> : {};
    const awemeId = awemeIdFromCanonicalDetail(record, rawTargets[index] ?? null);
    if (!awemeId || !/^\d{8,}$/.test(awemeId)) {
      detailInvalidCount += 1;
      return;
    }
    if (detailsByAweme.has(awemeId)) {
      detailDuplicateCount += 1;
      return;
    }
    detailsByAweme.set(awemeId, record);
  });
  const ordered: string[] = [];
  const rejectedSamples: Array<{ value: string; reason: string }> = [];
  let duplicateCount = detailDuplicateCount;
  let invalidCount = detailInvalidCount;
  for (const value of [...rawTargets, ...Array.from(detailsByAweme.keys())]) {
    if (!/^\d{8,}$/.test(value)) {
      invalidCount += 1;
      if (rejectedSamples.length < 5) rejectedSamples.push({ value, reason: "invalid_aweme_id" });
      continue;
    }
    if (ordered.includes(value)) {
      duplicateCount += 1;
      if (rejectedSamples.length < 5) rejectedSamples.push({ value, reason: "duplicate_aweme_id" });
      continue;
    }
    ordered.push(value);
  }
  const targetDetails = ordered.map((awemeId, index): WholeProfileHarvestTargetDetail => {
    const record = detailsByAweme.get(awemeId) ?? {};
    const sourceUrl = canonicalDetailString(record, "source_url", "video_url", "href", "url") ?? `https://www.douyin.com/video/${awemeId}`;
    const thumbnailUrl = canonicalDetailString(record, "thumbnail_url", "cover_url", "image_url");
    const caption = canonicalDetailString(record, "caption", "title", "desc", "text_sample");
    const postedText = canonicalDetailString(record, "posted_text", "posted_text_raw");
    const durationText = canonicalDetailString(record, "duration_text");
    const recordEvidence = record.profile_card_evidence && typeof record.profile_card_evidence === "object" ? record.profile_card_evidence as Record<string, unknown> : {};
    const resolvedProfileUrl = canonicalDetailString(record, "profile_url") ?? canonicalDetailString(recordEvidence, "profile_url") ?? profileUrl;
    const discoverySource = canonicalDetailString(record, "discovery_source", "extraction_source") ?? "active_works_grid_22C11B";
    const profileCardEvidence = buildHybridProfileCardEvidence(recordEvidence, [{
      aweme_id: awemeId,
      source_url: sourceUrl,
      profile_url: resolvedProfileUrl,
      discovery_source: discoverySource,
      discovered_at: at,
      card_index: index + 1,
      thumbnail_url: thumbnailUrl,
      cover_url: thumbnailUrl ?? recordEvidence.cover_url,
      caption,
      title: caption,
      posted_text: postedText,
      posted_at: canonicalDetailString(record, "posted_at"),
      duration_seconds: typeof record.duration_seconds === "number" ? record.duration_seconds : recordEvidence.duration_seconds,
      duration: typeof record.duration === "number" ? record.duration : recordEvidence.duration,
      like_count: typeof record.like_count === "number" ? record.like_count : recordEvidence.like_count,
      comment_count: typeof record.comment_count === "number" ? record.comment_count : recordEvidence.comment_count,
      favorite_count: typeof record.favorite_count === "number" ? record.favorite_count : recordEvidence.favorite_count,
      share_count: typeof record.share_count === "number" ? record.share_count : recordEvidence.share_count,
      create_time: typeof record.create_time === "number" ? record.create_time : recordEvidence.create_time
    }]);
    return {
      index: index + 1,
      aweme_id: awemeId,
      source_url: sourceUrl,
      profile_url: resolvedProfileUrl,
      thumbnail_url: thumbnailUrl,
      title: caption,
      caption,
      text_sample: caption,
      posted_text: postedText,
      posted_at: canonicalDetailString(record, "posted_at"),
      duration_text: durationText,
      duration_seconds: typeof record.duration_seconds === "number" ? record.duration_seconds : null,
      view_text: canonicalDetailString(record, "view_text"),
      view_count: typeof record.view_count === "number" ? record.view_count : null,
      candidate_validation: { status: "accepted", source: "video_link", reason: null, source_url: sourceUrl },
      metadata_completeness: {
        has_profile_identity: true,
        has_thumbnail: Boolean(thumbnailUrl),
        has_title_or_caption: Boolean(caption),
        has_posted_text: Boolean(postedText),
        has_duration: Boolean(durationText || typeof record.duration_seconds === "number"),
        has_view_count: typeof record.view_count === "number",
        has_detail_metrics: evidenceHasHybridRequiredMetrics(profileCardEvidence)
      },
      capture_status: "new",
      backend_item: null,
      extraction_source: discoverySource,
      profile_card_evidence: profileCardEvidence
    };
  });
  const queue: WholeProfileHarvestQueueItem[] = targetDetails.map((target) => ({
    index: target.index,
    aweme_id: target.aweme_id,
    capture_status: "new",
    status: "pending",
    attempts: 0,
    checkpoint_sequence: null,
    extraction_result: null,
    last_error: null,
    capture_inbox_item_id: null,
    source_url: target.source_url,
    profile_card_evidence: target.profile_card_evidence ?? buildHybridProfileCardEvidence(null, [{
      aweme_id: target.aweme_id,
      source_url: target.source_url,
      profile_url: target.profile_url,
      discovery_source: target.extraction_source ?? "active_works_grid_22C11B"
    }])
  }));
  return {
    targetDetails,
    queue,
    targets: targetDetails.map((target) => target.aweme_id),
    diagnostics: {
      canonical_queue_adapter_result: queue.length > 0 ? "success" : "canonical_queue_adapter_zero_output",
      canonical_queue_adapter_input_count: rawTargets.length || rawDetails.length,
      canonical_queue_adapter_output_count: queue.length,
      canonical_queue_adapter_name: queueBuilderName,
      scan_queue_builder_used: queueBuilderName,
      unique_seen_aweme_count: ordered.length,
      unique_verified_target_count: targetDetails.length,
      unique_queue_output_count: queue.length,
      adapter_input_count: rawTargets.length + rawDetails.length,
      adapter_output_count: queue.length,
      adapter_duplicate_count: duplicateCount,
      adapter_invalid_count: invalidCount,
      adapter_rejected_count: duplicateCount + invalidCount,
      adapter_rejected_reason_counts: { duplicate_aweme_id: duplicateCount, invalid_aweme_id: invalidCount },
      adapter_rejected_sample: rejectedSamples,
      queue_missing_after_adapter_count: Math.max(ordered.length - queue.length, 0),
      profile_queue_total_count: queue.length,
      profile_batch_limit: "disabled_all_profile_queue_22C13A",
      profile_batch_pending_count: queue.length,
      profile_batch_mode: "all_profile_queue_22C11B_13A",
      next_10_safe_finalization_mode: "disabled",
      profile_queue_limit_reason: "disabled_for_scan_finalization_22C13A"
    }
  };
}

type CountReconciliationState22C11B = "exact" | "under_collected" | "over_collected" | "expected_semantics_unverified";
type QueueSourceMode22C11B = "active_profile_post_only" | "dom_scoped_fallback_degraded";
type ActiveFetchFailureReason22C11B = "required_query_keys_unavailable" | "active_profile_post_response_status_non_zero" | "active_profile_post_extractor_no_targets" | "active_profile_post_usable" | "active_profile_post_unusable";

function underExpectedStopReasonForActiveFetchFailure22C11B(reason: ActiveFetchFailureReason22C11B): string {
  if (reason === "required_query_keys_unavailable") return "active_profile_post_required_query_keys_unavailable_below_expected";
  if (reason === "active_profile_post_response_status_non_zero") return "active_profile_post_response_status_non_zero_below_expected";
  if (reason === "active_profile_post_extractor_no_targets") return "active_profile_post_extractor_no_targets_below_expected";
  if (reason === "active_profile_post_unusable") return "active_profile_post_unusable_below_expected";
  return "active_profile_post_terminal_failure_below_expected";
}

type QueueAuthorityResolution22C11B = {
  mode: QueueSourceMode22C11B;
  reason: string;
  health: "healthy" | "degraded";
  queue: WholeProfileHarvestQueueItem[];
  targetDetails: WholeProfileHarvestTargetDetail[];
  targets: string[];
  stalePreviousQueueCount: number;
  preservedPreviousQueueCount: number;
  fallbackUsed: boolean;
  authoritativeTargetCount: number;
};

function queueAuthorityInvariantDiagnostics22C11B(input: {
  queueAuthority: QueueAuthorityResolution22C11B;
  queueSourceMode: QueueSourceMode22C11B;
  activeFetchReason: ActiveFetchFailureReason22C11B;
}): Record<string, unknown> {
  const violations: string[] = [];
  if (input.queueAuthority.mode !== input.queueSourceMode) {
    violations.push("canonical_queue_authority_mode_mismatch");
  }
  if (input.queueSourceMode === "active_profile_post_only" && input.activeFetchReason !== "active_profile_post_usable") {
    violations.push("canonical_queue_authority_mode_unexpected_for_active_profile_post_unusable");
  }
  if (input.queueSourceMode === "dom_scoped_fallback_degraded" && input.activeFetchReason === "active_profile_post_usable") {
    violations.push("canonical_queue_authority_mode_unexpected_for_active_profile_post_usable");
  }

  const queueDiscoverySources = Array.from(new Set(input.queueAuthority.queue.map((item): string => {
    const value = item.profile_card_evidence?.discovery_source;
    return typeof value === "string" && value.trim() ? value.trim() : "unknown";
  })));
  const targetDiscoverySources = Array.from(new Set(input.queueAuthority.targetDetails.map((item): string => {
    const value = item.profile_card_evidence?.discovery_source ?? item.extraction_source;
    return typeof value === "string" && value.trim() ? value.trim() : "unknown";
  })));
  const activeAuthoritySourceAliases = new Set(["active_profile_post_22C12B"]);
  const domFallbackSourceAliases = new Set(["dom_scoped_fallback_22C11B", "active_works_grid_22C11B"]);
  const authoritativeSources = input.queueSourceMode === "active_profile_post_only"
    ? activeAuthoritySourceAliases
    : domFallbackSourceAliases;
  const nonAuthoritativeQueueSources = queueDiscoverySources.filter((source) => !authoritativeSources.has(source));
  const nonAuthoritativeTargetSources = targetDiscoverySources.filter((source) => !authoritativeSources.has(source));

  if (input.queueSourceMode === "active_profile_post_only" && nonAuthoritativeQueueSources.length > 0) {
    violations.push("canonical_queue_authority_active_only_queue_source_mix_detected");
  }
  if (input.queueSourceMode === "active_profile_post_only" && nonAuthoritativeTargetSources.length > 0) {
    violations.push("canonical_queue_authority_active_only_target_source_mix_detected");
  }
  if (input.queueSourceMode === "dom_scoped_fallback_degraded" && nonAuthoritativeQueueSources.length > 0) {
    violations.push("canonical_queue_authority_dom_fallback_queue_source_mix_detected");
  }
  if (input.queueSourceMode === "dom_scoped_fallback_degraded" && nonAuthoritativeTargetSources.length > 0) {
    violations.push("canonical_queue_authority_dom_fallback_target_source_mix_detected");
  }

  const domScopedSupplementCount = input.queueSourceMode === "active_profile_post_only"
    ? input.queueAuthority.queue.filter((item) => item.profile_card_evidence?.discovery_source === "dom_scoped_fallback_22C11B" || item.profile_card_evidence?.discovery_source === "active_works_grid_22C11B").length
    : 0;
  if (input.queueSourceMode === "active_profile_post_only" && domScopedSupplementCount > 0) {
    violations.push("canonical_queue_authority_active_only_dom_supplement_detected");
  }

  return {
    queue_authority_invariants_checked: "yes",
    queue_authority_invariants_ok: violations.length === 0 ? "yes" : "no",
    queue_authority_invariant_violation_count: violations.length,
    queue_authority_invariant_violations: violations,
    queue_authority_source_mix_checked: "yes",
    queue_authority_expected_source_mode: input.queueSourceMode,
    queue_authority_expected_source_aliases: Array.from(authoritativeSources),
    queue_authority_queue_sources: queueDiscoverySources,
    queue_authority_target_sources: targetDiscoverySources,
    queue_authority_non_active_queue_source_count: nonAuthoritativeQueueSources.length,
    queue_authority_non_active_target_source_count: nonAuthoritativeTargetSources.length,
    queue_authority_dom_scoped_supplement_count: domScopedSupplementCount
  };
}

function underExpectedStopReasonMappingInvariantDiagnostics22C11B(): Record<string, unknown> {
  const violations: string[] = [];
  if (underExpectedStopReasonForActiveFetchFailure22C11B("required_query_keys_unavailable") !== "active_profile_post_required_query_keys_unavailable_below_expected") {
    violations.push("canonical_under_expected_stop_reason_required_query_keys_unavailable_mismatch");
  }
  if (underExpectedStopReasonForActiveFetchFailure22C11B("active_profile_post_response_status_non_zero") !== "active_profile_post_response_status_non_zero_below_expected") {
    violations.push("canonical_under_expected_stop_reason_response_status_non_zero_mismatch");
  }
  if (underExpectedStopReasonForActiveFetchFailure22C11B("active_profile_post_extractor_no_targets") !== "active_profile_post_extractor_no_targets_below_expected") {
    violations.push("canonical_under_expected_stop_reason_extractor_no_targets_mismatch");
  }
  if (underExpectedStopReasonForActiveFetchFailure22C11B("active_profile_post_unusable") !== "active_profile_post_unusable_below_expected") {
    violations.push("canonical_under_expected_stop_reason_unusable_mismatch");
  }
  return {
    under_expected_stop_reason_invariants_checked: "yes",
    under_expected_stop_reason_invariants_ok: violations.length === 0 ? "yes" : "no",
    under_expected_stop_reason_invariant_violation_count: violations.length,
    under_expected_stop_reason_invariant_violations: violations
  };
}

function resolveCanonicalQueueAuthority22C11B(args: {
  adapted: { queue: WholeProfileHarvestQueueItem[]; targetDetails: WholeProfileHarvestTargetDetail[]; targets: string[] };
  previousQueue: WholeProfileHarvestQueueItem[];
  previousTargetDetails: WholeProfileHarvestTargetDetail[];
  activeFetchUsable: boolean;
  activeFetchSetupUnavailable: boolean;
  activeFetchTerminalFailure: boolean;
  activeFetchReason: string;
}): QueueAuthorityResolution22C11B {
  const adaptedAwemeIds = new Set(args.adapted.queue.map((item) => item.aweme_id));
  const stalePreviousQueue = args.previousQueue.filter((item) => item.aweme_id && !adaptedAwemeIds.has(item.aweme_id));
  const stalePreviousIds = new Set(stalePreviousQueue.map((item) => item.aweme_id));
  const previousDetailByAweme = new Map(args.previousTargetDetails.map((target) => [target.aweme_id, target]));

  const mode: QueueSourceMode22C11B = args.activeFetchUsable
    ? "active_profile_post_only"
    : "dom_scoped_fallback_degraded";
  const reason = args.activeFetchUsable
    ? "active_profile_post_usable"
    : args.activeFetchSetupUnavailable
      ? "active_profile_post_setup_unavailable"
      : args.activeFetchTerminalFailure
        ? args.activeFetchReason
        : "active_profile_post_unusable";
  const health: "healthy" | "degraded" = args.activeFetchUsable ? "healthy" : "degraded";

  const expectedSource = mode === "active_profile_post_only" ? "active_profile_post_22C12B" : "dom_scoped_fallback_22C11B";
  const mergedQueue = args.adapted.queue.map((item, index) => ({
    ...item,
    index: index + 1,
    profile_card_evidence: { ...(item.profile_card_evidence ?? {}), discovery_source: expectedSource }
  }));
  const mergedTargetDetails = args.adapted.targetDetails.map((target, index) => ({
    ...target,
    index: index + 1,
    extraction_source: expectedSource,
    profile_card_evidence: { ...(target.profile_card_evidence ?? {}), discovery_source: expectedSource }
  }));

  return {
    mode,
    reason,
    health,
    queue: mergedQueue,
    targetDetails: mergedTargetDetails,
    targets: mergedTargetDetails.map((target) => target.aweme_id),
    stalePreviousQueueCount: stalePreviousQueue.length,
    preservedPreviousQueueCount: 0,
    fallbackUsed: !args.activeFetchUsable,
    authoritativeTargetCount: mergedQueue.length
  };
}

type CountReconciliationInput22C11B = {
  scanRunId: string;
  profileUrl: string;
  expectedProfileVideoCount: number | null;
  expectedCountRawText: string | null;
  expectedCountSource: string | null;
  expectedCountSemanticsVerified: boolean;
  currentRunResolvedTargetCount: number;
  previousQueueCount: number;
  mergedQueueCount: number;
  finalQueueCount: number;
  activeWorksHighConfidenceCount: number;
  activeWorksFilteredQueueCount: number;
  queueSourceMode: QueueSourceMode22C11B;
  countDelta: number | null;
  networkPostHasMoreState: boolean | null;
  networkPostExhausted: boolean;
  networkPostExhaustedEvidenceStrong: boolean;
  networkPostContinuationLikely: boolean;
  networkPostBatchCount: number;
  activeProfilePostMeaningfulAttempt: boolean;
  activeFetchUsable: boolean;
  activeFetchTerminalFailure: boolean;
  activeFetchExhaustedStrong: boolean;
  activeFetchSetupUnavailable: boolean;
  activeFetchFailureReason: ActiveFetchFailureReason22C11B;
};

function terminalStateFromReconciliation22C11B(input: CountReconciliationInput22C11B): { state: CountReconciliationState22C11B; result: string; error: string | null; ready: boolean; stopReason: string } {
  if (input.finalQueueCount <= 0) {
    return { state: "expected_semantics_unverified", result: "failed", error: "canonical_no_targets_found", ready: false, stopReason: "scroll_converged_no_queue_22C11B" };
  }

  if (input.expectedProfileVideoCount == null || !input.expectedCountSemanticsVerified) {
    if (input.networkPostContinuationLikely) {
      return {
        state: "expected_semantics_unverified",
        result: "incomplete",
        error: "canonical_expected_count_semantics_unverified_has_more_true",
        ready: false,
        stopReason: "network_profile_post_has_more_true_expected_unverified_22C13B"
      };
    }
    if (input.networkPostExhausted) {
      if (!input.networkPostExhaustedEvidenceStrong) {
        return {
          state: "expected_semantics_unverified",
          result: "incomplete",
          error: "canonical_expected_count_semantics_unverified_exhausted_without_strong_evidence",
          ready: false,
          stopReason: "network_profile_post_exhausted_without_strong_evidence_22C13B"
        };
      }
      if (!input.activeProfilePostMeaningfulAttempt) {
        return {
          state: "expected_semantics_unverified",
          result: "incomplete",
          error: "canonical_expected_count_semantics_unverified_exhausted_without_meaningful_active_attempt",
          ready: false,
          stopReason: "network_profile_post_exhausted_without_meaningful_active_attempt_22C13B"
        };
      }
      return {
        state: "expected_semantics_unverified",
        result: "success",
        error: null,
        ready: true,
        stopReason: "network_profile_post_exhausted_expected_unverified_22C12B"
      };
    }
    return {
      state: "expected_semantics_unverified",
      result: "incomplete",
      error: "canonical_expected_count_semantics_unverified",
      ready: false,
      stopReason: "network_profile_post_not_exhausted_expected_unverified_22C12B"
    };
  }

  if (input.finalQueueCount < input.expectedProfileVideoCount) {
    const underExpectedActiveFetchStopReason = underExpectedStopReasonForActiveFetchFailure22C11B(input.activeFetchFailureReason);
    if (input.activeFetchSetupUnavailable) {
      return {
        state: "under_collected",
        result: "incomplete",
        error: "canonical_under_collected_expected_count_active_profile_post_setup_unavailable",
        ready: false,
        stopReason: underExpectedActiveFetchStopReason
      };
    }
    if (input.activeFetchTerminalFailure) {
      return {
        state: "under_collected",
        result: "incomplete",
        error: "canonical_under_collected_expected_count_active_profile_post_terminal_failure",
        ready: false,
        stopReason: underExpectedActiveFetchStopReason
      };
    }
    if (!input.activeFetchUsable) {
      return {
        state: "under_collected",
        result: "incomplete",
        error: "canonical_under_collected_expected_count_active_profile_post_unusable",
        ready: false,
        stopReason: underExpectedActiveFetchStopReason
      };
    }
    return {
      state: "under_collected",
      result: "incomplete",
      error: "canonical_under_collected_expected_count",
      ready: false,
      stopReason: input.activeFetchExhaustedStrong && input.networkPostExhausted && input.networkPostExhaustedEvidenceStrong
        ? "network_profile_post_exhausted_below_expected_22C12B"
        : "scroll_converged_queue_below_expected_22C11B"
    };
  }

  if (input.finalQueueCount > input.expectedProfileVideoCount) {
    return {
      state: "over_collected",
      result: "success",
      error: null,
      ready: true,
      stopReason: "network_profile_post_queue_above_expected_accepted_22C12B"
    };
  }

  return { state: "exact", result: "success", error: null, ready: true, stopReason: "scroll_converged_queue_accepted_22C11B" };
}

type BackgroundPostScanCounterReconciliation22C11B = {
  diagnostics: Record<string, unknown>;
  snapshot: PostScanCounterSnapshot;
};

function backgroundPostScanNumber22C11B(value: unknown, fallback = 0): number {
  const numberValue = typeof value === "number" ? value : Number(value ?? fallback);
  return Number.isFinite(numberValue) ? Math.max(0, Math.round(numberValue)) : fallback;
}

function backgroundSecUidFromProfileUrl22C11B(profileUrl: string): string | null {
  const match = profileUrl.match(/\/user\/([^/?#]+)/i);
  return match?.[1] ? decodeURIComponent(match[1]) : null;
}

let backgroundApiBaseUrlCache22C11B = "http://127.0.0.1:8000";

async function readBackgroundApiBaseUrl22C11B(): Promise<string> {
  const stored = await chrome.storage.sync.get("apiBaseUrl").catch(() => ({} as Record<string, unknown>));
  const baseUrl = (typeof stored.apiBaseUrl === "string" && stored.apiBaseUrl.trim() ? stored.apiBaseUrl.trim() : "http://127.0.0.1:8000").replace(/\/+$/, "");
  backgroundApiBaseUrlCache22C11B = baseUrl;
  return baseUrl;
}

async function reconcileBackgroundPostScanCounters22C11B(args: { profileUrl: string; scannedTotal: number; appliedAt: string }): Promise<BackgroundPostScanCounterReconciliation22C11B> {
  const { profileUrl, scannedTotal, appliedAt } = args;
  const endpoint = "/douyin-extension/capture-inbox/profile-items";
  const fallbackProfileIdentifier = backgroundSecUidFromProfileUrl22C11B(profileUrl) ?? profileUrl ?? "unknown";
  const baseDiagnostics = {
    backend_reconciliation_source: "capture_inbox_profile_items",
    backend_reconciliation_endpoint: endpoint,
    backend_reconciliation_profile_identifier: fallbackProfileIdentifier,
    post_scan_backend_reconciliation_ran: "yes",
    post_scan_backend_reconciliation_status: "unavailable",
    post_scan_backend_reconciliation_endpoint: endpoint,
    post_scan_backend_reconciliation_profile_identifier: fallbackProfileIdentifier,
    post_scan_backend_reconciliation_used_capture_inbox_card_source: "no",
    post_scan_backend_captured_count: 0,
    post_scan_backend_ready_count: 0,
    post_scan_backend_duplicate_count: 0,
    post_scan_backend_failed_count: 0,
    post_scan_backend_incomplete_count: 0,
    post_scan_scanned_total_count: scannedTotal,
    post_scan_new_count: scannedTotal,
    post_scan_queue_count: scannedTotal,
    post_scan_counter_snapshot_applied: "no",
    post_scan_counter_snapshot_source: "capture_inbox_profile_items",
    post_scan_counter_overwrite_blocked: "no",
    post_scan_counter_fallback_reason: "backend_profile_source_unavailable",
    post_scan_backend_summary_called_at: appliedAt
  };
  const fallbackSnapshot: PostScanCounterSnapshot = {
    status: "backend_unavailable",
    source: "local_fallback_backend_unavailable",
    profile_identifier: fallbackProfileIdentifier,
    scanned_total: scannedTotal,
    backend_captured: null,
    backend_ready: null,
    backend_dup: null,
    backend_fail: null,
    already_collected: 0,
    incomplete: 0,
    need_retry: 0,
    new: scannedTotal,
    queue: scannedTotal,
    applied_at: appliedAt
  };
  try {
    const baseUrl = await readBackgroundApiBaseUrl22C11B();
    const path = `${endpoint}?profile_url=${encodeURIComponent(profileUrl)}&limit=1000`;
    const response = await postToBackend(await withStoredAuthHeader({ base_url: baseUrl, path, method: "GET", keepalive: false }));
    const body = response.body && typeof response.body === "object" ? response.body : null;
    const counts = body?.counts && typeof body.counts === "object" ? body.counts as Record<string, unknown> : {};
    if (!response.ok || !body || !Array.isArray(body.items)) {
      return {
        diagnostics: {
          ...baseDiagnostics,
          post_scan_backend_profile_response_status: response.status_code,
          post_scan_backend_reconciliation_error: response.error_message ?? "backend_profile_source_unavailable"
        },
        snapshot: fallbackSnapshot
      };
    }
    const captured = backgroundPostScanNumber22C11B(counts.captured, backgroundPostScanNumber22C11B(body.items_count, body.items.length));
    const ready = backgroundPostScanNumber22C11B(counts.ready);
    const duplicate = backgroundPostScanNumber22C11B(counts.dup ?? counts.duplicate);
    const failed = backgroundPostScanNumber22C11B(counts.fail ?? counts.failed);
    const incomplete = Math.max(0, captured - ready - duplicate - failed);
    const newCount = Math.max(0, scannedTotal - captured);
    const profileIdentifier = typeof body.profile_identifier === "string" && body.profile_identifier ? body.profile_identifier : fallbackProfileIdentifier;
    return {
      diagnostics: {
        ...baseDiagnostics,
        backend_reconciliation_status: "success",
        backend_reconciliation_profile_identifier: profileIdentifier,
        backend_reconciliation_profile_normalized_url: typeof body.normalized_profile_url === "string" ? body.normalized_profile_url : profileUrl,
        backend_reconciliation_profile_scope: typeof body.profile_scope === "string" ? body.profile_scope : "same_profile_only",
        backend_reconciliation_counter_source: "capture_inbox_profile_card_counts",
        backend_reconciliation_applied_to_profile_counters: "yes",
        backend_reconciliation_backend_profile_captured_count: captured,
        backend_reconciliation_backend_ready_count: ready,
        backend_reconciliation_backend_duplicate_count: duplicate,
        backend_reconciliation_backend_failed_count: failed,
        backend_reconciliation_backend_incomplete_count: incomplete,
        post_scan_backend_reconciliation_status: "success",
        post_scan_backend_reconciliation_profile_identifier: profileIdentifier,
        post_scan_backend_reconciliation_used_capture_inbox_card_source: "yes",
        post_scan_backend_profile_response_status: response.status_code,
        post_scan_backend_profile_response_items_count: body.items.length,
        post_scan_backend_captured_count: captured,
        post_scan_backend_ready_count: ready,
        post_scan_backend_duplicate_count: duplicate,
        post_scan_backend_failed_count: failed,
        post_scan_backend_incomplete_count: incomplete,
        post_scan_new_count: newCount,
        post_scan_queue_count: newCount,
        post_scan_counter_snapshot_applied: "yes",
        post_scan_counter_snapshot_source: "capture_inbox_profile_card_counts",
        post_scan_counter_overwrite_blocked: "yes",
        post_scan_counter_fallback_reason: null
      },
      snapshot: {
        status: "applied",
        source: "backend_capture_inbox_profile_summary",
        profile_identifier: profileIdentifier,
        scanned_total: scannedTotal,
        backend_captured: captured,
        backend_ready: ready,
        backend_dup: duplicate,
        backend_fail: failed,
        already_collected: captured,
        incomplete,
        need_retry: failed,
        new: newCount,
        queue: newCount,
        applied_at: appliedAt
      }
    };
  } catch (error) {
    return {
      diagnostics: {
        ...baseDiagnostics,
        post_scan_backend_reconciliation_error: error instanceof Error ? error.message : String(error)
      },
      snapshot: fallbackSnapshot
    };
  }
}

async function finalizeCanonicalScanSuccess22C11B(scanRunId: string, profileUrl: string, response: ExtensionMessageResponse, options: { tabId?: number | null } = {}): Promise<void> {
  const at = new Date().toISOString();
  const stored = await chrome.storage.local.get(WHOLE_PROFILE_HARVEST_STATE_KEY);
  const state = (stored[WHOLE_PROFILE_HARVEST_STATE_KEY] as WholeProfileHarvestState | undefined) ?? createWholeProfileHarvestIdleState(at);
  let adapted = adaptCanonicalVerifiedTargets22C11B(response, profileUrl, at);
  const responseDiagnosticsRaw = response.diagnostics && typeof response.diagnostics === "object" ? response.diagnostics as Record<string, unknown> : {};
  const responseDiagnostics = withCanonicalActiveProfilePostDiagnostics22C12B(responseDiagnosticsRaw);
  // 22C-14F fallback intentionally runs before zero-queue failure: active profile-post may be terminally unusable while DOM/passive profile-post evidence is still valid and must release the scan lock through normal finalization.
  if (adapted.queue.length === 0) {
    const fallbackAdapted = buildCanonicalFallbackAdapter22C14F(responseDiagnostics, profileUrl, at);
    if (fallbackAdapted) adapted = fallbackAdapted;
  }
  const activeProfilePostDiagnostics = objectValue(responseDiagnostics.active_profile_post) ?? canonicalActiveProfilePostDiagnostics22C12B(responseDiagnostics);
  const expectedCountRaw = responseDiagnostics.expected_profile_video_count ?? responseDiagnostics.expectedProfileVideoCount ?? responseDiagnostics.expected_count_value;
  const expectedCount = typeof expectedCountRaw === "number" ? expectedCountRaw : typeof expectedCountRaw === "string" ? Number(expectedCountRaw) : null;
  const expectedProfileVideoCount = expectedCount != null && Number.isFinite(expectedCount) && expectedCount > 0 ? Math.round(expectedCount) : null;
  const expectedSemanticsVerified = expectedProfileVideoCount != null
    && (responseDiagnostics.expected_profile_video_count_semantics_verified === "yes" || responseDiagnostics.expected_profile_video_count_semantics_verified === true)
    && responseDiagnostics.expected_profile_video_count_raw_text != null;
  const networkPostHasMoreRaw = responseDiagnostics.minimal_scan_network_probe_post_has_more_state_22C11B
    ?? responseDiagnostics.network_profile_post_has_more_state
    ?? responseDiagnostics.post_has_more_state
    ?? null;
  const networkPostHasMoreState = typeof networkPostHasMoreRaw === "boolean"
    ? networkPostHasMoreRaw
    : String(networkPostHasMoreRaw) === "true"
      ? true
      : String(networkPostHasMoreRaw) === "false"
        ? false
        : null;
  const networkPostBatchCountRaw = responseDiagnostics.minimal_scan_network_probe_post_batch_count_22C11B
    ?? responseDiagnostics.network_profile_post_batch_count
    ?? 0;
  const networkPostBatchCount = typeof networkPostBatchCountRaw === "number"
    ? networkPostBatchCountRaw
    : Number(networkPostBatchCountRaw);
  const networkPostExhaustedSignalByProbe = responseDiagnostics.minimal_scan_network_probe_post_exhausted_22C11B === "yes";
  const networkPostExhaustedSignalByHasMoreState = networkPostHasMoreState === false;
  const networkCollectionStopReasonRaw = typeof responseDiagnostics.network_collection_stop_reason === "string" && responseDiagnostics.network_collection_stop_reason.trim()
    ? responseDiagnostics.network_collection_stop_reason.trim()
    : null;
  const networkPostExhaustedSignalByStopReason = networkCollectionStopReasonRaw === "network_post_has_more_false";
  const networkPostExhausted = networkPostExhaustedSignalByProbe || networkPostExhaustedSignalByHasMoreState;
  const activeProfilePostTargetCount = numberFromDiagnostics(activeProfilePostDiagnostics.target_count);
  const activeProfilePostBatchCount = numberFromDiagnostics(activeProfilePostDiagnostics.batch_count);
  const activeProfilePostParserDirectMatchCount = numberFromDiagnostics(activeProfilePostDiagnostics.parser_direct_match_count);
  const activeProfilePostParserRoute = typeof activeProfilePostDiagnostics.parser_route === "string" && activeProfilePostDiagnostics.parser_route.trim()
    ? activeProfilePostDiagnostics.parser_route.trim()
    : null;
  const activeProfilePostResponseStatusCode = numberFromDiagnostics(activeProfilePostDiagnostics.response_status_code);
  const activeProfilePostResponseShapeUsable = activeProfilePostDiagnostics.response_shape === "ok";
  const activeProfilePostRequiredQueryKeysUnavailable = activeProfilePostDiagnostics.stop_reason === "required_query_keys_unavailable"
    || activeProfilePostDiagnostics.not_attempted_reason === "required_query_keys_unavailable"
    || activeProfilePostDiagnostics.template_required_query_keys_available === "no"
    || activeProfilePostDiagnostics.template_found === "no";
  const activeProfilePostExtractorNoTargets = activeProfilePostDiagnostics.stop_reason === "extractor_no_targets"
    || (activeProfilePostTargetCount <= 0 && activeProfilePostParserDirectMatchCount <= 0 && (activeProfilePostParserRoute == null || activeProfilePostParserRoute === "none"));
  const activeFetchSetupUnavailable = activeProfilePostRequiredQueryKeysUnavailable;
  const activeFetchTerminalFailure = !activeFetchSetupUnavailable && (activeProfilePostResponseStatusCode !== 0 || activeProfilePostExtractorNoTargets);
  const activeFetchUsable = !activeFetchSetupUnavailable
    && !activeFetchTerminalFailure
    && activeProfilePostResponseStatusCode === 0
    && activeProfilePostResponseShapeUsable
    && (activeProfilePostTargetCount > 0 || activeProfilePostBatchCount > 0 || (activeProfilePostParserRoute != null && activeProfilePostParserRoute !== "none" && activeProfilePostParserDirectMatchCount > 0));
  const activeProfilePostHasMoreState = activeProfilePostDiagnostics.has_more_state === "true"
    ? true
    : activeProfilePostDiagnostics.has_more_state === "false"
      ? false
      : null;
  const activeFetchExhaustedStrong = activeFetchUsable
    && activeProfilePostHasMoreState === false
    && activeProfilePostDiagnostics.stop_reason === "network_post_has_more_false";
  const activeProfilePostMeaningfulAttempt = activeFetchUsable;
  const activeFetchReason: ActiveFetchFailureReason22C11B = activeFetchSetupUnavailable
    ? "required_query_keys_unavailable"
    : activeProfilePostResponseStatusCode !== 0
      ? "active_profile_post_response_status_non_zero"
      : activeProfilePostExtractorNoTargets
        ? "active_profile_post_extractor_no_targets"
        : activeFetchUsable
          ? "active_profile_post_usable"
          : "active_profile_post_unusable";
  const queueAuthority = resolveCanonicalQueueAuthority22C11B({
    adapted,
    previousQueue: state.harvest.queue,
    previousTargetDetails: state.profile_scan.target_details,
    activeFetchUsable,
    activeFetchSetupUnavailable,
    activeFetchTerminalFailure,
    activeFetchReason: activeFetchReason
  });
  const mergedQueueBeforeFilter = queueAuthority.queue;
  const mergedTargetDetailsBeforeFilter = queueAuthority.targetDetails;
  const queueAuthorityInvariantDiagnostics = queueAuthorityInvariantDiagnostics22C11B({
    queueAuthority,
    queueSourceMode: queueAuthority.mode,
    activeFetchReason
  });
  const underExpectedStopReasonInvariantDiagnostics = underExpectedStopReasonMappingInvariantDiagnostics22C11B();
  const highConfidenceCount = mergedQueueBeforeFilter.filter((item) => item.profile_card_evidence?.active_works_confidence === "high").length;
  const lowConfidenceExtras: WholeProfileHarvestQueueItem[] = [];
  const filteredAwemeIds = new Set(lowConfidenceExtras.map((item) => item.aweme_id));
  const filteredToExpected = false;
  let mergedQueue = (filteredToExpected ? mergedQueueBeforeFilter.filter((item) => !filteredAwemeIds.has(item.aweme_id)) : mergedQueueBeforeFilter).map((item, index) => ({ ...item, index: index + 1 }));
  let mergedTargetDetails = (filteredToExpected ? mergedTargetDetailsBeforeFilter.filter((target) => !filteredAwemeIds.has(target.aweme_id)) : mergedTargetDetailsBeforeFilter).map((target, index) => ({ ...target, index: index + 1 }));

  const domOnlyConvergenceDetected = responseDiagnostics.minimal_scan_expected_count_finalization_gate_dom_only_convergence_detected_22C13B === "yes";
  const domOnlyConvergenceAllowedByScanner = responseDiagnostics.minimal_scan_expected_count_finalization_gate_dom_only_convergence_allowed_22C13B === "yes";
  const underExpected = expectedProfileVideoCount != null && mergedQueue.length < expectedProfileVideoCount;
  const domOnlyConvergenceAllowed = !domOnlyConvergenceDetected || (domOnlyConvergenceAllowedByScanner && activeProfilePostMeaningfulAttempt);
  const domOnlyConvergenceAllowedFinal = underExpected
    ? (activeFetchUsable && activeFetchExhaustedStrong)
    : domOnlyConvergenceAllowed;
  const networkPostExhaustedEvidenceStrong = (networkPostExhaustedSignalByProbe || networkPostExhaustedSignalByHasMoreState)
    && domOnlyConvergenceAllowedFinal
    && activeFetchUsable;
  const activeProfilePostRuntimeTimeoutHit = activeProfilePostDiagnostics.runtime_timeout_hit === "yes";
  const activeProfilePostPageCapHitWhileHasMoreCount = numberFromDiagnostics(activeProfilePostDiagnostics.page_cap_hit_while_has_more_count);
  const networkPostContinuationLikely = networkPostHasMoreState === true
    || (activeFetchUsable && activeProfilePostHasMoreState === true)
    || (activeFetchUsable && activeProfilePostRuntimeTimeoutHit)
    || (activeFetchUsable && activeProfilePostPageCapHitWhileHasMoreCount > 0);
  const networkCollectionStopReasonEffective = networkCollectionStopReasonRaw == null
    ? null
    : networkCollectionStopReasonRaw === "network_post_has_more_false" && !networkPostExhaustedEvidenceStrong
      ? "no + exhaustion_evidence_not_strong"
      : networkCollectionStopReasonRaw;

  const activeTerminalEvidenceStrongForTailReconcile = activeFetchExhaustedStrong
    || (activeProfilePostResponseStatusCode === 0
      && activeProfilePostHasMoreState === false
      && (activeProfilePostDiagnostics.stop_reason === "network_post_has_more_false" || activeProfilePostDiagnostics.stop_reason === "has_more_false"));
  const tailReconcile = await reconcileScanTailCandidates22C14E({
    scanRunId,
    tabId: options.tabId ?? null,
    profileUrl,
    expectedCount: expectedProfileVideoCount,
    queue: mergedQueue,
    targetDetails: mergedTargetDetails,
    activeTerminalEvidence: activeTerminalEvidenceStrongForTailReconcile,
    at,
    responseDiagnostics,
    activeDiagnostics: activeProfilePostDiagnostics
  });
  mergedQueue = tailReconcile.queue;
  mergedTargetDetails = tailReconcile.targetDetails;
  const apiDiscoveredBeforeDisplayedCap = mergedQueue.length;
  let displayedProfileQueueCapDiagnostics: Record<string, unknown> = {};
  if (expectedProfileVideoCount != null && expectedProfileVideoCount > 0 && mergedQueue.length > expectedProfileVideoCount) {
    const overDisplayedExtraIdSet = resolveOverDisplayedExtraAwemeIdSet({
      displayed_profile_count: expectedProfileVideoCount,
      over_displayed_count: mergedQueue.length - expectedProfileVideoCount,
      over_displayed_extra_ids_exact: mergedQueue.slice(expectedProfileVideoCount).map((item) => item.aweme_id)
    });
    const capResult = capOrderedQueueToDisplayedProfileLimit(
      mergedQueue,
      expectedProfileVideoCount,
      overDisplayedExtraIdSet
    );
    mergedQueue = capResult.queue.map((item, index) => ({ ...item, index: index + 1 }));
    const allowedAwemeIds = new Set(mergedQueue.map((item) => item.aweme_id));
    mergedTargetDetails = capTargetDetailsToAwemeIds(mergedTargetDetails, allowedAwemeIds)
      .map((target, index) => ({ ...target, index: index + 1 }));
    displayedProfileQueueCapDiagnostics = {
      ...buildDisplayedProfileQueueCapDiagnostics({
        beforeCount: apiDiscoveredBeforeDisplayedCap,
        result: capResult,
        apiDiscoveredCount: apiDiscoveredBeforeDisplayedCap
      }),
      displayed_profile_count: expectedProfileVideoCount,
      api_collectable_count: apiDiscoveredBeforeDisplayedCap,
      final_cumulative_collectable_count: apiDiscoveredBeforeDisplayedCap,
      collectable_count: apiDiscoveredBeforeDisplayedCap,
      over_displayed_count: capResult.excludedCount,
      over_displayed_extra_ids_exact: capResult.excludedIds,
      count_semantics_status: "completed_with_api_over_displayed_count"
    };
  }
  const mergedTargets = mergedTargetDetails.map((target) => target.aweme_id);

  const countReconciliationInput: CountReconciliationInput22C11B = {
    scanRunId,
    profileUrl,
    expectedProfileVideoCount,
    expectedCountRawText: typeof responseDiagnostics.expected_profile_video_count_raw_text === "string" ? responseDiagnostics.expected_profile_video_count_raw_text : null,
    expectedCountSource: typeof responseDiagnostics.expected_profile_video_count_source === "string" ? responseDiagnostics.expected_profile_video_count_source : typeof responseDiagnostics.expected_count_source === "string" ? responseDiagnostics.expected_count_source : null,
    expectedCountSemanticsVerified: expectedSemanticsVerified,
    currentRunResolvedTargetCount: adapted.queue.length,
    previousQueueCount: state.harvest.queue.length,
    mergedQueueCount: mergedQueueBeforeFilter.length,
    finalQueueCount: mergedQueue.length,
    activeWorksHighConfidenceCount: highConfidenceCount,
    activeWorksFilteredQueueCount: filteredAwemeIds.size,
    queueSourceMode: queueAuthority.mode,
    countDelta: expectedProfileVideoCount != null ? mergedQueue.length - expectedProfileVideoCount : null,
    networkPostHasMoreState,
    networkPostExhausted,
    networkPostExhaustedEvidenceStrong,
    networkPostContinuationLikely,
    networkPostBatchCount: Number.isFinite(networkPostBatchCount) ? Math.max(0, Math.round(networkPostBatchCount)) : 0,
    activeProfilePostMeaningfulAttempt,
    activeFetchUsable,
    activeFetchTerminalFailure,
    activeFetchExhaustedStrong,
    activeFetchSetupUnavailable,
    activeFetchFailureReason: activeFetchReason
  };
  const terminal = terminalStateFromReconciliation22C11B(countReconciliationInput);
  const countDelta = countReconciliationInput.countDelta;
  const missingProfileVideoCount = expectedProfileVideoCount != null ? Math.max(expectedProfileVideoCount - countReconciliationInput.finalQueueCount, 0) : null;
  const overCollectedCount = expectedProfileVideoCount != null ? Math.max(countReconciliationInput.finalQueueCount - expectedProfileVideoCount, 0) : null;
  const expectedGapSmallThresholdCount = 5;
  const expectedGapSmallThresholdRatio = 0.01;
  const expectedGapRatio = expectedProfileVideoCount != null && expectedProfileVideoCount > 0 && missingProfileVideoCount != null ? missingProfileVideoCount / expectedProfileVideoCount : null;
  const terminalSmallGapSourceHealthy = activeProfilePostResponseStatusCode === 0
    && (
      activeProfilePostHasMoreState === false
      || activeProfilePostHasMoreState === true
      || activeProfilePostHasMoreState == null
    );
  const terminalSmallGapDetected = terminal.state === "under_collected"
    && terminal.result === "incomplete"
    && expectedProfileVideoCount != null
    && missingProfileVideoCount != null
    && missingProfileVideoCount > 0
    && terminalSmallGapSourceHealthy
    && (missingProfileVideoCount <= expectedGapSmallThresholdCount || (expectedGapRatio != null && expectedGapRatio <= expectedGapSmallThresholdRatio));
  const terminalSmallGapReclassified = terminalSmallGapDetected;
  const strictExpectedGapBlocked = terminal.state === "under_collected"
    && terminal.result === "incomplete"
    && expectedProfileVideoCount != null
    && missingProfileVideoCount != null
    && missingProfileVideoCount > 0
    && !terminalSmallGapReclassified;
  const terminalSmallGapReason = terminalSmallGapDetected ? "expected_gap_unresolved_after_terminal_reconcile" : null;
  const strictExpectedGapReason = strictExpectedGapBlocked ? "expected_gap_unresolved_strict_completeness_gate" : null;
  const countReconciliationState = terminal.state;
  const degradedFallbackReady = adapted.diagnostics.scan_fallback_used === "yes" && mergedQueue.length > 0;
  const nearCompleteThreshold = expectedProfileVideoCount != null ? Math.max(expectedGapSmallThresholdCount, Math.ceil(expectedProfileVideoCount * expectedGapSmallThresholdRatio)) : expectedGapSmallThresholdCount;
  const domOnlyFallback = degradedFallbackReady && !activeProfilePostMeaningfulAttempt;
  const completenessExpectedKnown = expectedProfileVideoCount != null && expectedProfileVideoCount > 0;
  const completenessFoundCount = countReconciliationInput.finalQueueCount;
  const completenessMissingCount = missingProfileVideoCount ?? 0;
  const severeDomOnlyUndercount = domOnlyFallback
    && completenessExpectedKnown
    && completenessMissingCount > nearCompleteThreshold
    && activeFetchReason !== "active_profile_post_usable";
  // Completion gate: DOM/page fallback can preserve partial evidence, but it must not promote a severe expected-count underrun when the active profile-post source never produced meaningful terminal evidence.
  const completenessReadyBlocked = strictExpectedGapBlocked || severeDomOnlyUndercount;
  const scanCompletenessGateResult = completenessReadyBlocked
    ? "blocked"
    : terminalSmallGapReclassified || terminal.ready || (degradedFallbackReady && !completenessExpectedKnown)
      ? "ready"
      : "incomplete";
  const scanCompletenessGateReason = completenessReadyBlocked
    ? `dom_only_fallback_under_expected_active_fetch_${activeFetchReason}`
    : terminalSmallGapReclassified
      ? terminalSmallGapReason
      : degradedFallbackReady && !completenessExpectedKnown
        ? "dom_only_fallback_expected_count_unavailable"
        : strictExpectedGapReason ?? terminal.stopReason;
  const fallbackCanBeReady = degradedFallbackReady && !strictExpectedGapBlocked && !completenessReadyBlocked && (!completenessExpectedKnown || terminal.ready);
  const terminalReady = terminalSmallGapReclassified || fallbackCanBeReady ? true : completenessReadyBlocked ? false : terminal.ready;
  const terminalResult = terminalSmallGapReclassified || fallbackCanBeReady ? "completed_with_warning" : completenessReadyBlocked ? "incomplete" : terminal.result;
  const terminalError = terminalSmallGapReclassified || fallbackCanBeReady ? null : severeDomOnlyUndercount ? scanCompletenessGateReason : terminal.error;
  const incompleteExpectedCount = countReconciliationState === "under_collected" || terminalResult === "incomplete";
  const acceptedOverCollection = countReconciliationState === "over_collected" && terminalReady;
  const reconciledStopReason = terminalSmallGapReclassified ? "network_profile_post_exhausted_below_expected_small_gap_22C14C" : severeDomOnlyUndercount ? scanCompletenessGateReason : terminal.stopReason;
  if (Array.isArray(response.verified_targets) && response.verified_targets.length > 0 && adapted.queue.length === 0) {
    await failCanonicalScanProfile22C11B(scanRunId, "canonical_queue_adapter_zero_output", "canonical_queue_adapter", { ...adapted.diagnostics, canonical_queue_adapter_invoked: "yes" });
    return;
  }
  if (adapted.queue.length === 0) {
    await failCanonicalScanProfile22C11B(scanRunId, "canonical_scanner_zero_verified_targets", "canonical_queue_adapter", { ...adapted.diagnostics, canonical_queue_adapter_invoked: "yes" });
    return;
  }
  const missingProfileVideoClassification = missingProfileVideoCount != null && missingProfileVideoCount > 0
    ? ((adapted.diagnostics.queue_missing_after_adapter_count as number | undefined) ?? 0) > 0
      ? "adapter_dropped_seen_targets"
      : ((responseDiagnostics.final_unique_aweme_id_count as number | undefined) ?? mergedQueue.length) >= expectedProfileVideoCount!
        ? "seen_but_not_queueable"
        : reconciledStopReason === "bottom_reached_before_expected_count" || reconciledStopReason === "scroll_stalled_before_expected_count" || reconciledStopReason === "bottom_reached_no_more_ids"
          ? "unrenderable_or_scroll_converged_before_expected_count"
          : "never_seen_before_scan_stop"
    : null;
  const profileIdentifier = profileIdentifierFromUrl(profileUrl);
  const targetRepository = createProfileTargetRepository();
  const shouldReplaceProfileTargets = state.scan_job.scan_job_id !== scanRunId || state.scan_job.profile_identifier !== profileIdentifier || state.scan_job.status === "idle";
  const targetPersistResult = await (shouldReplaceProfileTargets
    ? targetRepository.upsertProfileTargets(profileIdentifier, mergedQueue, mergedTargetDetails, at)
    : targetRepository.upsertProfileTargetPage(profileIdentifier, mergedQueue, mergedTargetDetails, at)
  ).catch((error: unknown): null => {
    console.warn("large_profile_target_repository_scan_commit_failed", error instanceof Error ? error.message : String(error));
    return null;
  });
  const queueWindow = targetPersistResult
    ? await targetRepository.getProfileTargetsByStatus(profileIdentifier, ["new", "pending", "processing", "retry", "incomplete", "needs_metadata", "failed_recoverable"], LARGE_PROFILE_QUEUE_PREVIEW_WINDOW_SIZE, 0).catch(() => null)
    : null;
  const persistedTotal = targetPersistResult?.total ?? mergedQueue.length;
  const windowRecords = queueWindow?.records ?? [];
  const queueWindowState = windowRecords.length > 0 ? buildQueueWindowFromRecords(windowRecords) : { queue: mergedQueue.slice(0, LARGE_PROFILE_QUEUE_PREVIEW_WINDOW_SIZE), targetDetails: mergedTargetDetails.slice(0, LARGE_PROFILE_QUEUE_PREVIEW_WINDOW_SIZE) };
  const queueTotalVisible = queueWindowState.queue.length;
  const largeProfileStorageBackend = targetPersistResult?.backend ?? "local";
  const largeProfileStorageDegraded = targetPersistResult?.degraded === true || targetPersistResult == null;
  const largeProfileStorageDegradedReason = targetPersistResult?.degraded_reason ?? (targetPersistResult == null ? "profile_target_repository_unavailable" : null);
  const activeProfilePostCursorRaw = activeProfilePostDiagnostics.cursor ?? activeProfilePostDiagnostics.last_cursor ?? null;
  const activeProfilePostCursor = typeof activeProfilePostCursorRaw === "string" || typeof activeProfilePostCursorRaw === "number" ? activeProfilePostCursorRaw : null;
  const activeProfilePostPerPageRawCounts = Array.isArray(activeProfilePostDiagnostics.per_page_raw_counts)
    ? activeProfilePostDiagnostics.per_page_raw_counts.filter((entry): entry is number => typeof entry === "number" && Number.isFinite(entry)).map((entry) => Math.max(0, Math.round(entry)))
    : [];
  const activeProfilePostPerPageAcceptedCounts = Array.isArray(activeProfilePostDiagnostics.per_page_accepted_counts)
    ? activeProfilePostDiagnostics.per_page_accepted_counts.filter((entry): entry is number => typeof entry === "number" && Number.isFinite(entry)).map((entry) => Math.max(0, Math.round(entry)))
    : [];
  const activeProfilePostRepositoryBeforeTotal = shouldReplaceProfileTargets ? 0 : Math.max(state.scan_job.total_persisted, 0);
  const activeProfilePostPersistedDelta = Math.max(persistedTotal - activeProfilePostRepositoryBeforeTotal, 0);
  const activeProfilePostPerPagePersistedTotals = activeProfilePostPerPageAcceptedCounts.length > 0
    ? activeProfilePostPerPageAcceptedCounts.map((_, index) => {
      const acceptedThroughPage = activeProfilePostPerPageAcceptedCounts.slice(0, index + 1).reduce((sum, count) => sum + count, 0);
      return index === activeProfilePostPerPageAcceptedCounts.length - 1
        ? persistedTotal
        : Math.min(activeProfilePostRepositoryBeforeTotal + acceptedThroughPage, persistedTotal);
    })
    : [];
  const activeProfilePostPerPageHasMore = Array.isArray(activeProfilePostDiagnostics.per_page_has_more)
    ? activeProfilePostDiagnostics.per_page_has_more.filter((entry): entry is boolean => typeof entry === "boolean")
    : [];
  const activeProfilePostPerPageCursorPresent = Array.isArray(activeProfilePostDiagnostics.per_page_cursor_present)
    ? activeProfilePostDiagnostics.per_page_cursor_present.filter((entry): entry is boolean => typeof entry === "boolean")
    : [];
  const activeProfilePostPerPageStatusCodes = Array.isArray(activeProfilePostDiagnostics.per_page_status_codes)
    ? activeProfilePostDiagnostics.per_page_status_codes.map((entry) => typeof entry === "number" || typeof entry === "string" ? entry : null)
    : [];
  const activeProfilePostFinalStatusCode: number | string | null = activeProfilePostPerPageStatusCodes.length > 0
    ? activeProfilePostPerPageStatusCodes[activeProfilePostPerPageStatusCodes.length - 1] ?? null
    : activeProfilePostDiagnostics.response_status_code == null
      ? null
      : activeProfilePostDiagnostics.response_status_code as number | string;
  const activeProfilePostReturnedTotal = numberFromDiagnostics(activeProfilePostDiagnostics.accepted_targets_total, mergedQueue.length);
  const activeProfilePostRawAwemeIdsTotal = numberFromDiagnostics(activeProfilePostDiagnostics.raw_aweme_ids_total, activeProfilePostDiagnostics.raw_items_total, activeProfilePostPerPageRawCounts.reduce((sum, count) => sum + count, 0));
  const activeProfilePostUniqueIds = new Set(mergedQueue.map((item) => item.aweme_id));
  const activeProfilePostSameProfileEvidence = new Map<string, PaginatedSameProfileEvidence22C14Q>(mergedTargetDetails.map((target) => {
    const detailEvidence = target.profile_card_evidence && typeof target.profile_card_evidence === "object"
      ? target.profile_card_evidence as Record<string, unknown>
      : {};
    const profileUrl = canonicalDetailString(detailEvidence, "profile_url");
    const profileIdentifier = profileUrl != null ? profileIdentifierFromUrl(profileUrl) : null;
    const targetProfileIdentifier = profileUrl != null ? profileIdentifierFromUrl(profileUrl) : null;
    const sameProfileValidated = profileIdentifier != null && targetProfileIdentifier != null && profileIdentifier === targetProfileIdentifier ? "yes" : "no";
    const safeDesc = target.caption ?? target.title ?? target.text_sample ?? target.posted_text ?? null;
    return [target.aweme_id, {
      awemeId: target.aweme_id,
      profileUrl,
      profileIdentifier,
      pageIndexFound: null,
      requestIndexFound: null,
      rawIndexFound: typeof target.index === "number" ? target.index : null,
      sourceEndpoint: null,
      sourceCursor: null,
      sourceProfileIdentifier: profileIdentifier,
      targetProfileIdentifier,
      authorId: canonicalDetailString(detailEvidence, "author_id", "uid", "user_id"),
      authorSecUid: canonicalDetailString(detailEvidence, "author_sec_uid", "sec_uid", "secUid"),
      desc: safeDesc,
      createTime: null,
      sameProfileValidated,
      sameProfileValidationReason: sameProfileValidated === "yes" ? "profile_identifier_exact_match" : profileIdentifier == null ? "profile_identity_not_proven" : "profile_identifier_mismatch",
      isPinnedCandidate: "unknown",
      isSpecialTabCandidate: "unknown",
      appearsInDomGrid: "unknown",
      appearsInVisibleProfileCountBasis: "unknown",
      itemReason: sameProfileValidated === "yes" ? "valid_same_profile_item_hidden_from_visible_count_basis" : profileIdentifier != null && targetProfileIdentifier != null ? "possible_cross_profile_contamination" : "profile_identity_not_proven"
    }];
  }));
  const activeProfilePostAccounting: PaginatedScanAccounting22C14B = {
    rawItemsTotal: numberFromDiagnostics(activeProfilePostDiagnostics.raw_items_total, activeProfilePostPerPageRawCounts.reduce((sum, count) => sum + count, 0)),
    rawAwemeIdsTotal: activeProfilePostRawAwemeIdsTotal,
    uniqueAwemeIds: activeProfilePostUniqueIds,
    uniqueAwemeIdOrder: mergedQueue.map((item) => item.aweme_id),
    orderedAcceptedTargets: mergedQueue.map((item, index) => ({
      ...(activeProfilePostSameProfileEvidence.get(item.aweme_id) ?? {
        awemeId: item.aweme_id,
        profileUrl: null,
        profileIdentifier: null,
        pageIndexFound: null,
        requestIndexFound: null,
        sourceEndpoint: null,
        sourceCursor: null,
        sourceProfileIdentifier: null,
        targetProfileIdentifier: profileIdentifier,
        sameProfileValidated: "no" as const,
        sameProfileValidationReason: "profile_identity_not_proven",
        isPinnedCandidate: "unknown" as const,
        isSpecialTabCandidate: "unknown" as const,
        appearsInDomGrid: "unknown" as const,
        appearsInVisibleProfileCountBasis: "unknown" as const,
        itemReason: "profile_identity_not_proven" as const
      }),
      acceptedIndex: index,
      sourceTemplateId: typeof activeProfilePostDiagnostics.template_id === "string" ? activeProfilePostDiagnostics.template_id : null
    })),
    sameProfileEvidenceByAwemeId: activeProfilePostSameProfileEvidence,
    requestedProfileIdentifier: profileIdentifier,
    apiResponseProfileIdentifier: mergedTargetDetails.map((target) => activeProfilePostSameProfileEvidence.get(target.aweme_id)?.profileIdentifier ?? null).find((value) => value != null) ?? null,
    targetsReturnedToBackgroundTotal: activeProfilePostReturnedTotal,
    backgroundTargetsReceivedTotal: activeProfilePostReturnedTotal,
    backgroundTargetsAfterValidationTotal: mergedQueue.length,
    backgroundDuplicateDropTotal: numberFromDiagnostics(activeProfilePostDiagnostics.duplicate_drop_count),
    backgroundInvalidDropTotal: numberFromDiagnostics(activeProfilePostDiagnostics.invalid_drop_count, adapted.diagnostics.adapter_invalid_count),
    otherProfileDropCount: numberFromDiagnostics(activeProfilePostDiagnostics.other_profile_drop_count, responseDiagnostics.minimal_scan_active_profile_post_cross_profile_excluded_count_22C12B),
    favoriteEndpointDropCount: numberFromDiagnostics(activeProfilePostDiagnostics.favorite_endpoint_drop_count),
    emptyOrMissingAwemeIdCount: numberFromDiagnostics(activeProfilePostDiagnostics.missing_aweme_id_count),
    repositoryExistingBeforeTotal: Math.max(persistedTotal - activeProfilePostPersistedDelta, 0),
    repositoryWriteInputCount: mergedQueue.length,
    repositoryNewInsertedTotal: activeProfilePostPersistedDelta,
    repositoryDuplicateExistingTotal: Math.max(mergedQueue.length - activeProfilePostPersistedDelta, 0),
    repositoryWriteTotalAfter: persistedTotal,
    perPageRawCounts: activeProfilePostPerPageRawCounts,
    perPageRawAwemeIdCounts: activeProfilePostPerPageRawCounts,
    perPageReturnedTargetCounts: activeProfilePostPerPageAcceptedCounts,
    perPageUniqueNewCounts: activeProfilePostPerPageAcceptedCounts,
    perPageDuplicateCounts: activeProfilePostPerPageAcceptedCounts.map(() => 0),
    perPageCursorValues: activeProfilePostPerPageCursorPresent.map((present) => present ? activeProfilePostCursor : null),
    perPageCursorPresentFlags: activeProfilePostPerPageCursorPresent,
    perPageHasMoreFlags: activeProfilePostPerPageHasMore,
    perPageStatusCodes: activeProfilePostPerPageStatusCodes,
    perPageParserRoutes: [],
    perPagePersistedTotals: activeProfilePostPerPagePersistedTotals,
    firstPageRawCount: activeProfilePostPerPageRawCounts[0] ?? null,
    lastPageRawCount: activeProfilePostPerPageRawCounts[activeProfilePostPerPageRawCounts.length - 1] ?? null,
    lastPageAcceptedCount: activeProfilePostPerPageAcceptedCounts[activeProfilePostPerPageAcceptedCounts.length - 1] ?? null,
    lastPagePersistedDelta: activeProfilePostPersistedDelta,
    finalHasMore: activeProfilePostPerPageHasMore.length > 0 ? activeProfilePostPerPageHasMore[activeProfilePostPerPageHasMore.length - 1] ?? null : activeProfilePostHasMoreState,
    finalCursorPresent: activeProfilePostPerPageCursorPresent.length > 0 ? activeProfilePostPerPageCursorPresent[activeProfilePostPerPageCursorPresent.length - 1] ?? null : activeProfilePostCursorRaw != null,
    finalStatusCode: activeProfilePostFinalStatusCode
  };
  const accountingPersistedTotalForSemantics = apiDiscoveredBeforeDisplayedCap > persistedTotal
    ? apiDiscoveredBeforeDisplayedCap
    : persistedTotal;
  const activeProfilePostAccountingDiagnostics = paginatedScanAccountingDiagnostics22C14B(
    activeProfilePostAccounting,
    expectedProfileVideoCount,
    accountingPersistedTotalForSemantics
  );
  const activeProfilePostPageCount = numberFromDiagnostics(activeProfilePostDiagnostics.page_count, activeProfilePostDiagnostics.request_count, activeProfilePostDiagnostics.batch_count, response.scan_rounds);
  const activeProfilePostRequestCount = numberFromDiagnostics(activeProfilePostDiagnostics.request_count, activeProfilePostDiagnostics.batch_count);
  const activeProfilePostAccountingPageCount = numberFromDiagnostics(activeProfilePostAccountingDiagnostics.active_profile_post_fetch_page_count);
  const activeProfilePostAccountingRequestCount = numberFromDiagnostics(activeProfilePostAccountingDiagnostics.active_profile_post_fetch_request_count);
  const canonicalActiveProfilePostPageCount = activeProfilePostAccountingPageCount > 0 ? activeProfilePostAccountingPageCount : activeProfilePostPageCount;
  const canonicalActiveProfilePostRequestCount = activeProfilePostAccountingRequestCount > 0 ? activeProfilePostAccountingRequestCount : activeProfilePostRequestCount;
  const scanJob = {
    ...createPersistentScanJobRecord(at),
    ...state.scan_job,
    scan_job_id: scanRunId,
    status: terminalReady ? "completed" as const : "failed" as const,
    profile_identifier: profileIdentifier,
    cursor: activeProfilePostCursor,
    has_more_state: activeProfilePostHasMoreState,
    page_count: canonicalActiveProfilePostPageCount,
    request_count: canonicalActiveProfilePostRequestCount,
    last_http_status: numberFromDiagnostics(activeProfilePostDiagnostics.last_http_status) || null,
    last_status_code: activeProfilePostDiagnostics.response_status_code == null ? null : activeProfilePostDiagnostics.response_status_code as number | string,
    last_error: terminalError,
    started_at: state.scan_job.started_at ?? at,
    updated_at: at,
    completed_at: terminalReady || terminalResult === "failed" || terminalResult === "incomplete" ? at : null,
    next_retry_at: terminalReady ? null : at,
    consecutive_no_new_pages: activeProfilePostDiagnostics.stop_reason === "cursor_stalled" || activeProfilePostDiagnostics.stop_reason === "extractor_no_targets" ? 1 : 0,
    total_discovered: mergedQueue.length,
    total_persisted: persistedTotal,
    expected_count: expectedProfileVideoCount,
    remaining_estimate: missingProfileVideoCount
  };
  const largeProfileDiagnostics = {
    large_profile_mode: mergedQueue.length > LARGE_PROFILE_QUEUE_PREVIEW_WINDOW_SIZE ? "yes" : "no",
    scan_total_found: mergedQueue.length,
    scan_total_expected: expectedProfileVideoCount,
    scan_total_missing: missingProfileVideoCount,
    queue_window_size: LARGE_PROFILE_QUEUE_PREVIEW_WINDOW_SIZE,
    queue_window_offset: 0,
    queue_total_persisted: persistedTotal,
    queue_total_visible: queueTotalVisible,
    queue_counter_authority: "queue_total_persisted",
    expected_gap_count: missingProfileVideoCount,
    expected_gap_ratio: expectedGapRatio,
    expected_gap_small_threshold_count: expectedGapSmallThresholdCount,
    expected_gap_small_threshold_ratio: expectedGapSmallThresholdRatio,
    terminal_small_gap_reclassified: terminalSmallGapReclassified ? "yes" : "no",
    terminal_small_gap_reason: terminalSmallGapReason,
    scan_job_id: scanJob.scan_job_id,
    scan_job_status: scanJob.status,
    scan_job_page_count: scanJob.page_count,
    scan_job_request_count: scanJob.request_count,
    scan_job_has_more: scanJob.has_more_state,
    scan_job_cursor: scanJob.cursor,
    scan_job_last_status_code: scanJob.last_status_code,
    scan_job_consecutive_no_new_pages: scanJob.consecutive_no_new_pages,
    large_profile_storage_backend: largeProfileStorageBackend,
    large_profile_storage_degraded: largeProfileStorageDegraded ? "yes" : "no",
    large_profile_storage_degraded_reason: largeProfileStorageDegradedReason ?? (largeProfileStorageDegraded ? "indexeddb_unavailable_using_local_memory_fallback" : null),
    large_profile_durable_persistence: largeProfileStorageDegraded ? "no" : "yes",
    collect_cursor: state.harvest.current_index ?? 0,
    last_processed_aweme_id: state.harvest.current_aweme_id ?? null,
    last_checkpoint_at: state.harvest.last_checkpoint_at ?? null,
    chunk_processed_count: 0,
    chunk_total_count: queueTotalVisible
  };
  const classification = {
    ...emptyClassificationState(),
    status: "success" as const,
    started_at: at,
    completed_at: at,
    last_error: null,
    profile_url: profileUrl,
    schema_version: "douyin_profile_video_classification_result.v1" as const,
    collection_mode: "minimal_active_works_grid_scanner_22C11B",
    database_lookup_status: "not_checked_canonical_scan",
    total_candidates: mergedTargetDetails.length,
    counts: { ...emptyClassificationCounts(), new: mergedQueue.length, collect: mergedQueue.length },
    targets: mergedTargetDetails.map((target) => ({
      aweme_id: target.aweme_id,
      classification: "new" as const,
      collect: true,
      reason: "minimal_active_works_grid_scanner_22C11B",
      required_missing_fields: [],
      existing_item_id: null,
      metadata_status: null,
      review_status: null,
      video_url: target.source_url,
      source_url: target.source_url,
      thumbnail_url: target.thumbnail_url,
      caption: target.caption
    })),
    collect_aweme_ids: mergedTargets,
    skip_aweme_ids: [],
    diagnostics: { source: "scan_queue_adapter_22C11B", classification_bypassed: true }
  };
  const incompleteScanBlocksCounterAuthority = !terminalReady || terminalResult === "incomplete" || completenessReadyBlocked;
  const postScanCounters = incompleteScanBlocksCounterAuthority
    ? {
      snapshot: null,
      diagnostics: {
        backend_reconciliation_skipped_for_incomplete_scan: "yes",
        post_scan_snapshot_skipped_for_incomplete_scan: "yes",
        counter_authority_blocked_for_incomplete_scan: "yes",
        post_scan_backend_reconciliation_ran: "no",
        post_scan_backend_reconciliation_status: "skipped_incomplete_scan",
        post_scan_counter_snapshot_applied: "no",
        post_scan_counter_snapshot_source: "skipped_incomplete_scan",
        post_scan_counter_overwrite_blocked: "yes"
      }
    }
    : await reconcileBackgroundPostScanCounters22C11B({
      profileUrl,
      scannedTotal: expectedProfileVideoCount ?? mergedQueue.length,
      appliedAt: at
    });
  const scanSourceLedger = {
    requested_profile_url: canonicalRequestedProfileUrlFromDiagnostics(responseDiagnostics, profileUrl),
    network_profile_post_count: numberFromDiagnostics(responseDiagnostics.minimal_scan_network_probe_target_count_22C11B, responseDiagnostics.network_profile_post_unique_count, activeProfilePostDiagnostics.target_count),
    network_profile_post_passive_count: numberFromDiagnostics(responseDiagnostics.minimal_scan_network_probe_target_count_22C11B, responseDiagnostics.network_profile_post_unique_count),
    network_profile_post_active_count: numberFromDiagnostics(activeProfilePostDiagnostics.target_count),
    network_profile_post_active_only_count: numberFromDiagnostics(activeProfilePostDiagnostics.only_aweme_count),
    active_profile_post_fetch_attempted: activeProfilePostDiagnostics.attempted,
    active_profile_post_fetch_stop_reason: typeof activeProfilePostDiagnostics.stop_reason === "string" && activeProfilePostDiagnostics.stop_reason ? activeProfilePostDiagnostics.stop_reason : "none",
    active_profile_post_fetch_not_attempted_reason: typeof activeProfilePostDiagnostics.not_attempted_reason === "string" && activeProfilePostDiagnostics.not_attempted_reason ? activeProfilePostDiagnostics.not_attempted_reason : "none",
    active_profile_post_fetch_error: typeof activeProfilePostDiagnostics.error === "string" && activeProfilePostDiagnostics.error ? activeProfilePostDiagnostics.error : "none",
    dom_profile_scoped_target_count: numberFromDiagnostics(responseDiagnostics.minimal_scan_dom_profile_scoped_target_count_22C11B, responseDiagnostics.minimal_scan_dom_target_count_22C11B),
    dom_profile_scoped_supplement_count: numberFromDiagnostics(responseDiagnostics.minimal_scan_dom_profile_scoped_supplement_count_22C11B),
    dom_profile_scoped_rejected_count: numberFromDiagnostics(responseDiagnostics.minimal_scan_dom_profile_scoped_rejected_count_22C12B),
    current_video_supplemented: responseDiagnostics.minimal_scan_current_vid_supplemented_22C11B === "yes",
    current_video_aweme_id: typeof responseDiagnostics.minimal_scan_current_vid_aweme_id_22C11B === "string" ? responseDiagnostics.minimal_scan_current_vid_aweme_id_22C11B : null,
    merged_target_count: numberFromDiagnostics(responseDiagnostics.minimal_scan_merged_target_count_22C11B, mergedQueue.length),
    active_profile_post_fetch_effective_attempted: activeProfilePostMeaningfulAttempt,
    active_profile_post_fetch_effective_attempt_reason: typeof activeProfilePostDiagnostics.effective_attempt_reason === "string" && activeProfilePostDiagnostics.effective_attempt_reason
      ? activeProfilePostDiagnostics.effective_attempt_reason
      : "none",
    active_profile_post_template_warmup_attempted: activeProfilePostDiagnostics.template_warmup_attempted === "yes",
    active_profile_post_template_warmup_attempt_count: numberFromDiagnostics(activeProfilePostDiagnostics.template_warmup_attempt_count),
    active_profile_post_template_warmup_applied_template: activeProfilePostDiagnostics.template_warmup_applied_template === "yes",
    active_profile_post_template_warmup_stop_reason: typeof activeProfilePostDiagnostics.template_warmup_stop_reason === "string" && activeProfilePostDiagnostics.template_warmup_stop_reason
      ? activeProfilePostDiagnostics.template_warmup_stop_reason
      : "none",
    queue_authority_mode: queueAuthority.mode,
    queue_authority_reason: queueAuthority.reason,
    queue_authority_health: queueAuthority.health,
    queue_authority_fallback_used: queueAuthority.fallbackUsed ? "yes" : "no"
  };
  const diagnostics = canonicalScanDiagnostics22C11B(scanRunId, "scan_finished", withCanonicalActiveProfilePostDiagnostics22C12B({
    ...sanitizeScannerDiagnostics22C11B(responseDiagnostics),
    ...largeProfileDiagnostics,
    ...displayedProfileQueueCapDiagnostics,
    ...activeProfilePostAccountingDiagnostics,
    active_profile_post_fetch_page_count: canonicalActiveProfilePostPageCount,
    active_profile_post_fetch_request_count: canonicalActiveProfilePostRequestCount,
    ...tailReconcile.diagnostics,
    ...adapted.diagnostics,
    ...postScanCounters.diagnostics,
    ...queueAuthorityInvariantDiagnostics,
    ...underExpectedStopReasonInvariantDiagnostics,
    canonical_queue_adapter_invoked: "yes",
    canonical_queue_adapter_skipped_reason: null,
    canonical_result_parse_status: "parsed",
    canonical_scanner_result: terminalResult,
    canonical_scanner_rounds: response.scan_rounds ?? 0,
    canonical_scanner_stop_reason: reconciledStopReason,
    canonical_scanner_verified_target_count: mergedQueue.length,
    canonical_scan_message_sent: "yes",
    canonical_handler_self_test: "success",
    scan_engine_used: typeof responseDiagnostics.scan_engine_used === "string" ? responseDiagnostics.scan_engine_used : "minimal_active_works_grid_scanner_22C11B",
    production_profile_scan_engine: typeof responseDiagnostics.scan_engine_used === "string" ? responseDiagnostics.scan_engine_used : "minimal_active_works_grid_scanner_22C11B",
    scan_fallback_used: adapted.diagnostics.scan_fallback_used ?? responseDiagnostics.scan_fallback_used ?? "no",
    scan_fallback_reason: adapted.diagnostics.scan_fallback_reason ?? responseDiagnostics.scan_fallback_reason ?? null,
    scan_fallback_original_active_fetch_error: adapted.diagnostics.scan_fallback_original_active_fetch_error ?? responseDiagnostics.scan_fallback_original_active_fetch_error ?? null,
    scan_fallback_candidate_source_counts: adapted.diagnostics.scan_fallback_candidate_source_counts ?? responseDiagnostics.scan_fallback_candidate_source_counts ?? null,
    scan_fallback_candidate_total_count: adapted.diagnostics.scan_fallback_candidate_total_count ?? responseDiagnostics.scan_fallback_candidate_total_count ?? 0,
    expected_profile_video_count: expectedProfileVideoCount,
    expected_profile_video_count_source: responseDiagnostics.expected_profile_video_count_source ?? responseDiagnostics.expected_count_source ?? (expectedProfileVideoCount == null ? "unavailable" : "profile_tab_text"),
    expected_profile_video_count_raw_text: responseDiagnostics.expected_profile_video_count_raw_text ?? null,
    expected_profile_video_count_selector: responseDiagnostics.expected_profile_video_count_selector ?? null,
    expected_profile_video_count_parse_ok: expectedProfileVideoCount != null ? "yes" : "no",
    expected_profile_video_count_parse_error: expectedProfileVideoCount == null ? responseDiagnostics.expected_profile_video_count_parse_error ?? "expected_count_unavailable" : null,
    missing_profile_video_count: missingProfileVideoCount,
    expected_gap_count: missingProfileVideoCount,
    expected_gap_ratio: expectedGapRatio,
    expected_gap_small_threshold_count: expectedGapSmallThresholdCount,
    expected_gap_small_threshold_ratio: expectedGapSmallThresholdRatio,
    terminal_small_gap_reclassified: terminalSmallGapReclassified ? "yes" : "no",
    terminal_small_gap_reason: terminalSmallGapReason,
    over_collected_count: overCollectedCount,
    count_delta: countDelta,
    count_reconciliation_input: countReconciliationInput,
    count_reconciliation_state: countReconciliationState,
    network_post_exhausted_signal_by_probe_22C12B: networkPostExhaustedSignalByProbe ? "yes" : "no",
    network_post_exhausted_signal_by_has_more_state_22C12B: networkPostExhaustedSignalByHasMoreState ? "yes" : "no",
    network_post_exhausted_signal_by_stop_reason_22C12B: networkPostExhaustedSignalByStopReason ? "yes" : "no",
    network_post_exhausted_evidence_gate_passed_22C12B: networkPostExhaustedEvidenceStrong ? "yes" : "no",
    expected_count_finalization_gate_active_profile_post_meaningful_attempt_22C13B: activeProfilePostMeaningfulAttempt ? "yes" : "no",
    expected_count_finalization_gate_active_profile_post_effective_attempt_reason_22C13B: typeof activeProfilePostDiagnostics.effective_attempt_reason === "string" && activeProfilePostDiagnostics.effective_attempt_reason
      ? activeProfilePostDiagnostics.effective_attempt_reason
      : "none",
    scan_completeness_gate_result: scanCompletenessGateResult,
    scan_completeness_gate_reason: scanCompletenessGateReason,
    scan_completeness_expected_count: expectedProfileVideoCount,
    scan_completeness_found_count: completenessFoundCount,
    scan_completeness_missing_count: missingProfileVideoCount,
    scan_completeness_active_fetch_meaningful: activeProfilePostMeaningfulAttempt ? "yes" : "no",
    scan_completeness_dom_only_fallback: domOnlyFallback ? "yes" : "no",
    scan_completeness_ready_blocked: completenessReadyBlocked ? "yes" : "no",
    active_profile_post_recovery_attempted: numberFromDiagnostics(responseDiagnostics.active_profile_post_template_retry_count, responseDiagnostics.active_profile_post_fetch_status_non_zero_retry_count, activeProfilePostDiagnostics.template_warmup_attempt_count) > 0 ? "yes" : "no",
    active_profile_post_recovery_result: activeProfilePostMeaningfulAttempt ? "recovered" : activeFetchReason,
    active_profile_post_recovery_reason: activeFetchReason,
    active_profile_post_template_retry_count: numberFromDiagnostics(responseDiagnostics.active_profile_post_template_retry_count, activeProfilePostDiagnostics.template_warmup_attempt_count),
    active_profile_post_non_zero_status_retryable: activeProfilePostResponseStatusCode !== 0 ? "yes" : "no",
    expected_count_finalization_gate_dom_only_convergence_detected_22C13B: domOnlyConvergenceDetected ? "yes" : "no",
    expected_count_finalization_gate_dom_only_convergence_allowed_22C13B: domOnlyConvergenceAllowedFinal ? "yes" : "no",
    expected_count_finalization_gate_policy_22C13B: "require_usable_active_profile_post_exhausted_evidence_for_under_expected_dom_convergence_22C13C",
    expected_count_gate_meaningful_active_fetch: activeProfilePostMeaningfulAttempt ? "yes" : "no",
    expected_count_gate_active_fetch_reason: activeFetchReason,
    expected_count_gate_dom_only_convergence_allowed: domOnlyConvergenceAllowedFinal ? "yes" : "no",
    network_post_continuation_likely_22C13B: networkPostContinuationLikely ? "yes" : "no",
    network_collection_stop_reason_effective: networkCollectionStopReasonEffective ?? "none",
    scan_source_ledger_22C11B: scanSourceLedger,
    scan_source_ledger: scanSourceLedger,
    count_reconciliation_reason: incompleteExpectedCount ? "queue_below_expected_count" : acceptedOverCollection ? "queue_above_expected_count_accepted_network_first" : countReconciliationState === "expected_semantics_unverified" ? "expected_count_unavailable_but_queue_valid" : "queue_matches_expected_count",
    final_queue_output_count: mergedQueue.length,
    profile_queue_total_count: persistedTotal,
    profile_batch_limit: "large_profile_windowed_preview_22C14A",
    profile_batch_pending_count: persistedTotal,
    profile_batch_mode: "all_profile_queue_22C11B_13A",
    next_10_safe_finalization_mode: "disabled",
    profile_queue_limit_reason: "disabled_for_scan_finalization_22C13A",
    active_works_tab_filter_result: filteredToExpected ? "filtered_to_expected" : acceptedOverCollection ? "accepted_overcollection" : "not_needed",
    active_works_filtered_out_count: filteredAwemeIds.size,
    active_works_filtered_out_sample: Array.from(filteredAwemeIds).slice(0, 5),
    queue_source_mode: countReconciliationInput.queueSourceMode,
    queue_authority_locked: "yes",
    queue_authority_mode: queueAuthority.mode,
    queue_authority_reason: queueAuthority.reason,
    queue_authority_health: queueAuthority.health,
    queue_authority_fallback_used: queueAuthority.fallbackUsed ? "yes" : "no",
    queue_authority_degraded_reason: queueAuthority.fallbackUsed ? queueAuthority.reason : null,
    queue_authority_resolved_target_count: queueAuthority.authoritativeTargetCount,
    current_run_resolved_target_count: countReconciliationInput.currentRunResolvedTargetCount,
    previous_queue_count: countReconciliationInput.previousQueueCount,
    merged_queue_count: countReconciliationInput.mergedQueueCount,
    final_queue_count: countReconciliationInput.finalQueueCount,
    expected_count_semantics_verified: countReconciliationInput.expectedCountSemanticsVerified ? "yes" : "no",
    previous_queue_stale_excluded_count: queueAuthority.stalePreviousQueueCount,
    previous_queue_preserved_high_confidence_count: queueAuthority.preservedPreviousQueueCount,
    missing_profile_video_classification: missingProfileVideoClassification,
    missing_profile_video_forensics: {
      expected: expectedProfileVideoCount,
      collected: mergedQueue.length,
      missing: missingProfileVideoCount,
      unique_seen: responseDiagnostics.final_unique_aweme_id_count ?? adapted.diagnostics.unique_seen_aweme_count ?? mergedQueue.length,
      adapter_output: adapted.diagnostics.adapter_output_count ?? mergedQueue.length,
      adapter_rejected: adapted.diagnostics.adapter_rejected_count ?? 0,
      adapter_duplicate: adapted.diagnostics.adapter_duplicate_count ?? 0,
      adapter_invalid: adapted.diagnostics.adapter_invalid_count ?? 0,
      stop_reason: reconciledStopReason ?? null,
      bottom_reached: responseDiagnostics.bottom_reached ?? null,
      new_ids_stopped_appearing: responseDiagnostics.new_ids_stopped_appearing ?? null,
      scroll_stalled_rounds: responseDiagnostics.scroll_stalled_rounds ?? null
    },
    profile_scan_completion_ratio: expectedProfileVideoCount != null ? `${countReconciliationInput.finalQueueCount}/${expectedProfileVideoCount}` : null,
    profile_scan_incomplete: incompleteExpectedCount ? "yes" : "no",
    profile_scan_partial_ready: terminalReady ? "no" : "yes",
    profile_scan_incomplete_reason: terminalSmallGapReclassified ? terminalSmallGapReason : terminalError,
    lastScannerResult: terminalResult,
    lastScannerError: terminalError ?? "none",
    profileScanReady: terminalReady ? "yes" : "no",
    scanRounds: response.scan_rounds ?? 0,
    scanStop: reconciledStopReason,
    scan_stop: reconciledStopReason,
    scan_stop_authoritative: reconciledStopReason,
    scan_stop_authority_source: "canonical_terminal_reconciliation",
    scan_stop_authority_version: "22C-13D",
    scan_stop_authority_migrated: "yes",
    expected_gap_recovery_checked: missingProfileVideoCount != null && missingProfileVideoCount > 0 ? "yes" : "not_needed",
    expected_gap_recovery_sources_checked: tailReconcile.diagnostics.tail_reconcile_sources_checked ?? [],
    expected_gap_recovery_unrecoverable_reason: missingProfileVideoCount != null && missingProfileVideoCount > 0 ? tailReconcile.diagnostics.tail_reconcile_unrecoverable_reason ?? null : null,
    expected_gap_recovery_tail_candidates: tailReconcile.diagnostics.tail_reconcile_candidates ?? 0,
    expected_gap_recovery_tail_added: tailReconcile.diagnostics.tail_reconcile_added ?? 0,
    scan_finalization_result: terminalResult,
    scan_finalized_at: at,
    canonical_finalizer_version: "22C-11B",
    canonical_finalizer_ran: "yes",
    canonical_terminal_state: terminalResult,
    canonical_lock_release_ran: "yes",
    canonical_lock_release_reason: terminalResult,
    active_profile_post: activeProfilePostDiagnostics
  }));
  const diagnosticsChannels = splitCanonicalScanDiagnosticsChannels22C11B(diagnostics);
  const harvestQueueForState = queueWindowState.queue.length > 0 ? queueWindowState.queue : mergedQueue.slice(0, LARGE_PROFILE_QUEUE_PREVIEW_WINDOW_SIZE);
  const draftStateForContract: WholeProfileHarvestState = {
    ...state,
    profile_url: profileUrl,
    profile_scan: {
      ...state.profile_scan,
      status: terminalReady ? "success" : "failed",
      diagnostics: diagnosticsChannels.scanAuthorityDiagnostics
    },
    harvest: {
      ...state.harvest,
      queue: harvestQueueForState
    },
    post_scan_counter_snapshot: terminalReady ? postScanCounters.snapshot : state.post_scan_counter_snapshot
  };
  const patchedPostScanSnapshot = terminalReady && postScanCounters.snapshot
    ? applyProfileCollectContractToPostScanSnapshot(
      postScanCounters.snapshot,
      buildProfileCollectContractFromState(draftStateForContract)
    )
    : null;
  const next: WholeProfileHarvestState = appendWholeProfileTrace({
    ...state,
    status: terminalReady ? "verified" : "failed",
    phase: "scan_finished",
    profile_url: profileUrl,
    page_context: { ...state.page_context, current_url: profileUrl, page_type: responseDiagnostics.detector_page_type === "profile" || responseDiagnostics.page_type === "profile" ? "profile" : state.page_context.page_type },
    layer: { ...state.layer, profile_scan_ready: terminalReady, harvest_ready: terminalReady },
    workflow: {
      ...state.workflow,
      scan: { ...state.workflow.scan, status: terminalReady ? "success" : "failed", updated_at: at, completed_at: at, last_error: terminalError },
      classification: { status: terminalReady ? "success" : "idle", started_at: terminalReady ? at : null, updated_at: at, completed_at: terminalReady ? at : null, last_error: terminalError },
      active_task: null,
      action_lock: null
    },
    scan_job: scanJob,
    profile_scan: {
      status: terminalReady ? "success" : "failed",
      raw_candidate_count: Number(response.total_candidates ?? mergedQueue.length),
      accepted_target_count: mergedQueue.length,
      rejected_target_count: Number(response.rejected_count ?? 0),
      targets: mergedTargets,
      target_details: queueWindowState.targetDetails,
      rejected_candidates_sample: [],
      scan_rounds: Number(response.scan_rounds ?? 0),
      stop_reason: reconciledStopReason,
      scroll_container_found: Boolean((response.diagnostics as Record<string, unknown> | undefined)?.scroll_container_found ?? true),
      diagnostics: diagnosticsChannels.scanAuthorityDiagnostics
    },
    post_scan_counter_snapshot: patchedPostScanSnapshot,
    target_status: computeTargetStatusSummary(mergedTargetDetails),
    classification: terminalReady ? classification : { ...emptyClassificationState(), status: "idle", completed_at: null, last_error: terminalError },
    verify: {
      ...state.verify,
      status: terminalReady ? "success" : "failed",
      completed_at: at,
      raw_candidate_count: Number(response.total_candidates ?? mergedQueue.length),
      accepted_target_count: mergedQueue.length,
      rejected_target_count: Number(response.rejected_count ?? 0),
      verified_target_count: mergedQueue.length,
      targets: mergedTargets,
      target_details: queueWindowState.targetDetails,
      rejected_candidates_sample: [],
      scan_rounds: Number(response.scan_rounds ?? 0),
      stop_reason: reconciledStopReason,
      scroll_container_found: Boolean((response.diagnostics as Record<string, unknown> | undefined)?.scroll_container_found ?? true),
      diagnostics: diagnosticsChannels.scanAuthorityDiagnostics
    },
    harvest: {
      ...state.harvest,
      queue: queueWindowState.queue,
      queue_preview: buildCollectQueuePreviewFromQueue(queueWindowState.queue, queueWindowState.targetDetails),
      planned_total: persistedTotal,
      pending: persistedTotal,
      current_index: 0,
      current_aweme_id: null
    },
    debug: {
      ...state.debug,
      last_action_result: terminalResult,
      last_action_error: terminalError,
      last_action_finished_at: at,
      active_task: null,
      busy_source: null,
      last_request_summary: diagnosticsChannels.runtimeDebugDiagnostics,
      last_response_summary: diagnosticsChannels.runtimeDebugDiagnostics
    },
    last_error: terminalError ? `${terminalError}: Canonical Scan Profile did not produce a collect-ready queue.` : null,
    updated_at: at
  }, terminalReady ? "scan_profile.22C11B.success" : `scan_profile.22C11B.${terminalResult}`, terminalReady ? "Scan Profile completed." : `Scan Profile requires review: ${terminalResult}.`, diagnosticsChannels.scanAuthorityDiagnostics, at);
  const compactNext = prepareWholeProfileHarvestStateForStorage22C11B(next);
  const estimatedBytes = estimateStorageBytes22C11B({ [WHOLE_PROFILE_HARVEST_STATE_KEY]: compactNext });
  const writeDiagnostics = canonicalScanDiagnostics22C11B(scanRunId, "scan_finished", { ...diagnostics, storage_compaction_applied: "yes", storage_write_estimated_bytes: estimatedBytes, storage_write_result: "pending" });
  const writeDiagnosticsChannels = splitCanonicalScanDiagnosticsChannels22C11B(writeDiagnostics);
  compactNext.profile_scan.diagnostics = writeDiagnosticsChannels.scanAuthorityDiagnostics;
  compactNext.verify.diagnostics = writeDiagnosticsChannels.scanAuthorityDiagnostics;
  compactNext.debug.last_request_summary = writeDiagnosticsChannels.runtimeDebugDiagnostics;
  compactNext.debug.last_response_summary = writeDiagnosticsChannels.runtimeDebugDiagnostics;
  const write = await safeSetScannerStorage22C11B({ [WHOLE_PROFILE_HARVEST_STATE_KEY]: compactNext }, { stage: "scan_finished", compact: (payload) => payload });
  const storedDiagnostics = { ...writeDiagnostics, storage_write_estimated_bytes: write.estimatedBytes, storage_write_result: write.result };
  const storedDiagnosticsChannels = splitCanonicalScanDiagnosticsChannels22C11B(storedDiagnostics);
  compactNext.profile_scan.diagnostics = storedDiagnosticsChannels.scanAuthorityDiagnostics;
  compactNext.verify.diagnostics = storedDiagnosticsChannels.scanAuthorityDiagnostics;
  compactNext.debug.last_request_summary = storedDiagnosticsChannels.runtimeDebugDiagnostics;
  compactNext.debug.last_response_summary = storedDiagnosticsChannels.runtimeDebugDiagnostics;
  await safeSetScannerStorage22C11B({ [WHOLE_PROFILE_HARVEST_STATE_KEY]: compactNext }, { stage: "scan_finished_storage_result" });
}

function normalizePaginatedScanDiagnostics22C14B(args: {
  diagnostics: Record<string, unknown>;
  status: "running" | "retry_wait" | "completed" | "failed";
  retryCount: number;
  nextRetryAt?: string | null;
  lastError: string | null;
  totalDiscovered: number;
  totalPersisted: number;
  expectedCount: number | null;
  pageIndex: number;
  requestCount?: number;
  responseOk?: boolean;
  responseReason?: unknown;
}): Record<string, unknown> {
  const statusCode = args.diagnostics.active_profile_post_fetch_response_status_code
    ?? args.diagnostics.active_profile_post_page_fetch_last_status_code_22C14B
    ?? args.diagnostics.scan_job_last_status_code
    ?? "unknown";
  const nonZeroStatus = statusCode !== "unknown" && statusCode !== 0 && statusCode !== "0";
  const templateFound = args.diagnostics.active_profile_post_template_found
    ?? args.diagnostics.minimal_scan_active_profile_post_template_found_22C13B
    ?? (nonZeroStatus ? "no" : "unknown");
  const requiredKeysAvailable = args.diagnostics.active_profile_post_template_required_query_keys_available
    ?? args.diagnostics.minimal_scan_active_profile_post_template_required_query_keys_available_22C13B
    ?? (nonZeroStatus || args.lastError?.includes("required_query_keys_unavailable") ? "no" : "unknown");
  const activeStopReason = args.diagnostics.active_profile_post_fetch_stop_reason
    ?? args.diagnostics.active_profile_post_page_fetch_stop_reason_22C14B
    ?? (nonZeroStatus ? "active_profile_post_response_status_non_zero" : args.lastError ?? args.responseReason ?? "unknown");
  const activeUnusable = nonZeroStatus || templateFound === "no" || requiredKeysAvailable === "no" || args.status === "retry_wait" || (args.status === "failed" && args.lastError != null);
  const expectedKnown = args.expectedCount != null && args.expectedCount > 0;
  const currentRunFound = Math.max(args.totalPersisted, 0);
  const authoritativeStop = activeUnusable && expectedKnown
    ? String(activeStopReason)
    : args.status === "retry_wait"
      ? "active_profile_post_retry_wait"
      : args.status === "failed"
        ? (args.lastError ?? "scan_job_failed")
        : args.status === "completed"
          ? "active_profile_post_completed"
          : "active_profile_post_running";
  const normalized = {
    ...args.diagnostics,
    scan_stop_authoritative: args.diagnostics.scan_stop_authoritative ?? authoritativeStop,
    scan_stop_authority_source: args.diagnostics.scan_stop_authority_source ?? "paginated_active_profile_post_scan_job_22C14B",
    scan_job_status: args.status,
    scan_job_retry_count: args.retryCount,
    scan_job_next_retry_at: args.nextRetryAt ?? null,
    scan_job_last_error: args.lastError,
    scan_job_pages_fetched: args.pageIndex + 1,
    scan_job_total_discovered: args.totalDiscovered,
    scan_job_total_persisted: args.totalPersisted,
    scan_job_duplicate_or_existing_count: Math.max(args.totalDiscovered - args.totalPersisted, 0),
    api_pagination_attempted: "yes",
    api_pagination_page_count: args.pageIndex + 1,
    api_pagination_request_count: args.requestCount ?? args.pageIndex + 1,
    api_pagination_total_raw_targets: args.totalDiscovered,
    api_pagination_total_accepted_targets: args.totalPersisted,
    api_pagination_total_persisted_targets: args.totalPersisted,
    api_pagination_total_persisted: args.totalPersisted,
    api_pagination_expected: args.expectedCount,
    api_pagination_remaining: args.expectedCount == null ? null : Math.max(args.expectedCount - args.totalPersisted, 0),
    api_pagination_duplicate_or_existing_count: Math.max(args.totalDiscovered - args.totalPersisted, 0),
    api_pagination_final_has_more: args.diagnostics.scan_job_has_more_state ?? args.diagnostics.active_profile_post_page_fetch_has_more_state_22C14B ?? null,
    api_pagination_has_more_final: args.diagnostics.scan_job_has_more_state ?? args.diagnostics.active_profile_post_page_fetch_has_more_state_22C14B ?? null,
    api_pagination_final_cursor: args.diagnostics.scan_job_cursor ?? args.diagnostics.active_profile_post_page_fetch_next_cursor_22C14B ?? null,
    api_pagination_stop_reason: args.diagnostics.scan_job_stop_reason ?? args.diagnostics.scan_stop_authoritative ?? authoritativeStop,
    current_run_found_count: currentRunFound,
    persisted_total_count: args.totalPersisted,
    display_mode: args.status === "completed" ? "current_run_authority" : "scan_progress_authority",
    scan_progress_update_seq: args.requestCount ?? args.pageIndex + 1,
    scan_progress_updated_at: new Date().toISOString(),
    scan_progress_delivery_channel: "storage.local.checkpoint",
    scan_progress_discovered: currentRunFound,
    scan_progress_expected: args.expectedCount,
    scan_progress_remaining: args.expectedCount == null ? null : Math.max(args.expectedCount - currentRunFound, 0),
    scan_progress_pages: args.pageIndex + 1,
    scan_progress_requests: args.requestCount ?? args.pageIndex + 1,
    scan_progress_status_code: statusCode,
    scan_progress_phase_label: args.status === "retry_wait"
      ? "Retry wait"
      : args.status === "running"
        ? (args.expectedCount != null && args.expectedCount > 0 && currentRunFound >= args.expectedCount
          ? "Finalizing scan"
          : "Scanning profile")
        : args.status === "completed"
          ? "Finalizing scan"
          : "Scan failed",
    scan_finalization_stage: args.status === "running" && args.expectedCount != null && args.expectedCount > 0 && currentRunFound >= args.expectedCount
      ? "count_semantics"
      : args.status === "completed"
        ? "inbox_sync"
        : null,
    active_profile_post_fetch_response_status_code: statusCode,
    active_profile_post_fetch_stop_reason: activeStopReason,
    active_profile_post_template_found: templateFound,
    active_profile_post_template_required_query_keys_available: requiredKeysAvailable,
    expected_count_gate_meaningful_active_fetch: activeUnusable ? "no" : "yes",
    expected_count_gate_dom_only_convergence_allowed: activeUnusable && expectedKnown ? "no" : (args.diagnostics.expected_count_gate_dom_only_convergence_allowed ?? "unknown")
  };
  return { ...normalized, ...scanHealthVerdictDiagnostics22C14R(normalized) };
}

async function checkpointPaginatedScanJob22C14B(args: {
  scanRunId: string;
  profileUrl: string;
  expectedCount: number | null;
  response: ExtensionMessageResponse;
  pageIndex: number;
  cursor: string | number | null;
  totalDiscovered: number;
  totalPersisted: number;
  status: "running" | "retry_wait" | "completed" | "failed";
  retryCount: number;
  consecutiveNoNewPages: number;
  resumeSource: "new" | "resume_existing";
  lastError: string | null;
  nextRetryAt?: string | null;
}): Promise<void> {
  const at = new Date().toISOString();
  const diagnostics = args.response.diagnostics && typeof args.response.diagnostics === "object" ? args.response.diagnostics as Record<string, unknown> : {};
  const profileIdentifier = profileIdentifierFromUrl(args.profileUrl);
  const stored = await chrome.storage.local.get(WHOLE_PROFILE_HARVEST_STATE_KEY).catch(() => ({} as Record<string, unknown>));
  const current = (stored?.[WHOLE_PROFILE_HARVEST_STATE_KEY] && typeof stored[WHOLE_PROFILE_HARVEST_STATE_KEY] === "object" ? stored[WHOLE_PROFILE_HARVEST_STATE_KEY] : createWholeProfileHarvestIdleState(at)) as WholeProfileHarvestState;
  const rejection = scanAuthorityWriteRejection22C14D(current, { scanRunId: args.scanRunId, stage: args.status === "completed" || args.status === "failed" ? "scan_finished" : "scan_running", at, source: "background.checkpointPaginatedScanJob22C14B", terminal: args.status === "completed" || args.status === "failed" });
  if (rejection) return persistRuntimeDebugStaleRejection22C14D(current, rejection, "scan_job_checkpoint_stale_rejected_22C14D", at);
  const hasMoreState = diagnostics.scan_job_has_more_state === true || diagnostics.active_profile_post_page_fetch_has_more_state_22C14B === true
    ? true
    : diagnostics.scan_job_has_more_state === false || diagnostics.active_profile_post_page_fetch_has_more_state_22C14B === false
      ? false
      : null;
  const lastHttpStatus = numberFromDiagnostics(diagnostics.scan_job_last_http_status, diagnostics.active_profile_post_page_fetch_last_http_status_22C14B) || null;
  const lastStatusCodeRaw = diagnostics.scan_job_last_status_code ?? diagnostics.active_profile_post_page_fetch_last_status_code_22C14B ?? null;
  const continuationCursorSource: PersistentScanJobRecord["continuation_cursor_source"] = diagnostics.continuation_cursor_source === "fresh_start"
    || diagnostics.continuation_cursor_source === "saved_continuation_checkpoint"
    || diagnostics.continuation_cursor_source === "replay_recovery_checkpoint"
    || diagnostics.continuation_cursor_source === "unknown"
    ? diagnostics.continuation_cursor_source
    : null;
  const continuationResumeStrategy: PersistentScanJobRecord["continuation_resume_strategy"] = diagnostics.continuation_resume_strategy === "fresh_scan"
    || diagnostics.continuation_resume_strategy === "resume_from_saved_cursor"
    || diagnostics.continuation_resume_strategy === "replay_recovery_from_saved_cursor"
    || diagnostics.continuation_resume_strategy === "none"
    ? diagnostics.continuation_resume_strategy
    : null;
  const continuationResumeResult: PersistentScanJobRecord["continuation_resume_result"] = diagnostics.continuation_resume_result === "not_started"
    || diagnostics.continuation_resume_result === "resumed_from_saved_cursor"
    || diagnostics.continuation_resume_result === "replay_recovery_resumed"
    || diagnostics.continuation_resume_result === "checkpoint_unavailable"
    || diagnostics.continuation_resume_result === "not_applicable"
    ? diagnostics.continuation_resume_result
    : null;
  const continuationReplayDuplicatePagesDetected: PersistentScanJobRecord["continuation_replay_duplicate_pages_detected"] = diagnostics.continuation_replay_duplicate_pages_detected === "yes"
    || diagnostics.continuation_replay_duplicate_pages_detected === "no"
    ? diagnostics.continuation_replay_duplicate_pages_detected
    : null;
  const continuationRecoveryAttempted: PersistentScanJobRecord["continuation_recovery_attempted"] = diagnostics.continuation_recovery_attempted === "yes"
    || diagnostics.continuation_recovery_attempted === "no"
    ? diagnostics.continuation_recovery_attempted
    : null;
  const continuationRecoveryResult: PersistentScanJobRecord["continuation_recovery_result"] = diagnostics.continuation_recovery_result === "not_attempted"
    || diagnostics.continuation_recovery_result === "reused_saved_cursor"
    || diagnostics.continuation_recovery_result === "checkpoint_unavailable"
    || diagnostics.continuation_recovery_result === "recovery_exhausted"
    ? diagnostics.continuation_recovery_result
    : null;
  const scanJob: PersistentScanJobRecord = {
    ...createPersistentScanJobRecord(at),
    ...current.scan_job,
    scan_job_id: args.scanRunId,
    status: args.status,
    profile_identifier: profileIdentifier,
    cursor: args.cursor,
    has_more_state: hasMoreState,
    page_count: args.pageIndex + 1,
    request_count: (current.scan_job.request_count ?? 0) + 1,
    last_http_status: lastHttpStatus,
    last_status_code: typeof lastStatusCodeRaw === "string" || typeof lastStatusCodeRaw === "number" ? lastStatusCodeRaw : null,
    last_error: args.lastError,
    started_at: current.scan_job.started_at ?? at,
    updated_at: at,
    completed_at: args.status === "completed" || args.status === "failed" ? at : null,
    next_retry_at: args.nextRetryAt ?? null,
    retry_count: args.retryCount,
    resume_source: args.resumeSource,
    continuation_cursor_source: continuationCursorSource,
    continuation_resume_strategy: continuationResumeStrategy,
    continuation_resume_result: continuationResumeResult,
    continuation_replay_duplicate_pages_detected: continuationReplayDuplicatePagesDetected,
    continuation_replay_duplicate_count: typeof diagnostics.continuation_replay_duplicate_count === "number" ? diagnostics.continuation_replay_duplicate_count : null,
    continuation_recovery_attempted: continuationRecoveryAttempted,
    continuation_recovery_result: continuationRecoveryResult,
    continuation_checkpoint_id: typeof diagnostics.continuation_checkpoint_id === "string" ? diagnostics.continuation_checkpoint_id : null,
    continuation_run_id: typeof diagnostics.continuation_run_id === "string" ? diagnostics.continuation_run_id : null,
    continuation_persisted_total: typeof diagnostics.continuation_persisted_total === "number" ? diagnostics.continuation_persisted_total : null,
    continuation_progress_total: typeof diagnostics.continuation_progress_total === "number" ? diagnostics.continuation_progress_total : null,
    current_run_new_inserted_total: typeof diagnostics.current_run_new_inserted_total === "number" ? diagnostics.current_run_new_inserted_total : null,
    current_run_duplicate_existing_total: typeof diagnostics.current_run_duplicate_existing_total === "number" ? diagnostics.current_run_duplicate_existing_total : null,
    consecutive_no_new_pages: args.consecutiveNoNewPages,
    total_discovered: args.totalDiscovered,
    total_persisted: args.totalPersisted,
    expected_count: args.expectedCount,
    remaining_estimate: args.expectedCount == null ? null : Math.max(args.expectedCount - args.totalPersisted, 0)
  };
  const previousDiagnostics = diagnosticRecordByChannel22C14C(current.debug.last_request_summary, "runtime_debug_diagnostics");
  const sameScanRun = current.scan_job.scan_job_id === args.scanRunId || current.run_id === args.scanRunId;
  const previousDiagnosticsForRun = sameScanRun ? previousDiagnostics : {};
  const checkpointDiagnostics = {
    ...normalizePaginatedScanDiagnostics22C14B({
      diagnostics: { ...previousDiagnosticsForRun, ...diagnostics },
      status: args.status,
      retryCount: args.retryCount,
      nextRetryAt: args.nextRetryAt ?? null,
      lastError: args.lastError,
      totalDiscovered: args.totalDiscovered,
      totalPersisted: args.totalPersisted,
      expectedCount: args.expectedCount,
      pageIndex: args.pageIndex,
      requestCount: scanJob.request_count,
      responseOk: args.response.ok,
      responseReason: args.response.reason ?? args.response.error
    }),
    scan_job_request_count: scanJob.request_count
  };
  const terminalCheckpoint = args.status === "completed" || args.status === "failed";
  const checkpointRuntimeDiagnostics = splitCanonicalScanDiagnosticsChannels22C11B(
    canonicalScanDiagnostics22C11B(args.scanRunId, terminalCheckpoint ? "scan_finished" : "scan_running", checkpointDiagnostics as Record<string, unknown>)
  ).runtimeDebugDiagnostics;
  const checkpointStopReason = String((checkpointDiagnostics as Record<string, unknown>).scan_stop_authoritative ?? args.lastError ?? (args.status === "completed" ? "active_profile_post_completed" : "active_profile_post_failed"));
  const checkpointAuthorityDiagnostics = terminalCheckpoint
    ? splitCanonicalScanDiagnosticsChannels22C11B(canonicalScanDiagnostics22C11B(args.scanRunId, "scan_finished", {
      ...(checkpointDiagnostics as Record<string, unknown>),
      scan_finalization_result: args.status === "completed" ? "success" : "failed",
      scan_finalized_at: at,
      scan_stop_authoritative: checkpointStopReason,
      active_source_terminal_policy: args.status === "failed" ? "degraded_fallback_attempted_before_terminal_failure" : "not_applicable",
      active_source_degraded_fallback_policy: args.status === "failed" ? "enabled_before_terminalization" : "not_applicable",
      canonical_lock_release_ran: args.status === "failed" ? "yes" : "not_applicable",
      canonical_lock_release_reason: args.status === "failed" ? checkpointStopReason : "not_applicable"
    })).scanAuthorityDiagnostics
    : current.profile_scan.diagnostics;
  const next = appendWholeProfileTrace({
    ...current,
    status: args.status === "completed" ? "verified" : args.status === "failed" ? "failed" : "verifying",
    phase: terminalCheckpoint ? "scan_finished" : "scan_running",
    profile_url: args.profileUrl,
    workflow: terminalCheckpoint
      ? { ...current.workflow, scan: { ...current.workflow.scan, status: args.status === "completed" ? "success" : "failed", updated_at: at, completed_at: at, last_error: args.lastError }, active_task: null, action_lock: null }
      : { ...current.workflow, scan: { ...current.workflow.scan, status: "running", updated_at: at, last_error: args.lastError }, active_task: "scan_profile" },
    scan_job: scanJob,
    profile_scan: terminalCheckpoint ? { ...current.profile_scan, status: args.status === "completed" ? "success" : "failed", stop_reason: checkpointStopReason, scan_rounds: Math.max(current.profile_scan.scan_rounds, args.pageIndex + 1), diagnostics: checkpointAuthorityDiagnostics } : current.profile_scan,
    verify: terminalCheckpoint ? { ...current.verify, status: args.status === "completed" ? "success" : "failed", completed_at: at, stop_reason: checkpointStopReason, scan_rounds: Math.max(current.verify.scan_rounds, args.pageIndex + 1), diagnostics: checkpointAuthorityDiagnostics } : current.verify,
    harvest: { ...current.harvest, planned_total: args.totalPersisted, pending: args.totalPersisted },
    debug: terminalCheckpoint ? { ...current.debug, last_action_result: args.status === "completed" ? "success" : "failed", last_action_error: args.lastError, last_action_finished_at: at, active_task: null, busy_source: null, last_request_summary: checkpointRuntimeDiagnostics, last_response_summary: checkpointRuntimeDiagnostics } : { ...current.debug, last_request_summary: checkpointRuntimeDiagnostics, last_response_summary: checkpointRuntimeDiagnostics },
    updated_at: at
  }, `scan_profile.22C14B.${args.status}`, `Paginated scan job ${args.status}.`, terminalCheckpoint ? checkpointAuthorityDiagnostics : checkpointDiagnostics, at);
  const preparedNext = prepareWholeProfileHarvestStateForStorage22C11B(next);
  await safeSetScannerStorage22C11B({ [WHOLE_PROFILE_HARVEST_STATE_KEY]: preparedNext }, { stage: "scan_job_checkpoint_22C14B" });
  const runtimeDelivery = chrome.runtime.sendMessage?.({ type: "douyinScanner:stateChanged", state: preparedNext });
  if (runtimeDelivery && typeof runtimeDelivery.catch === "function") runtimeDelivery.catch(() => undefined);
}

async function verifyPaginatedScanSecondaryGap22C14P(args: { scanRunId: string; tabId: number | null; profileUrl: string; expectedCount: number | null; totalPersisted: number; responseDiagnostics: Record<string, unknown>; apiAwemeIds: Set<string>; repository: ReturnType<typeof createProfileTargetRepository>; at: string }): Promise<{ totalPersisted: number; recoveredCount: number; diagnostics: Record<string, unknown> }> {
  const gapBefore = args.expectedCount == null ? 0 : Math.max(args.expectedCount - args.totalPersisted, 0);
  const apiExhaustedHasMoreFalse = args.responseDiagnostics.scan_job_has_more_state === false || args.responseDiagnostics.active_profile_post_page_fetch_has_more_state_22C14B === false || args.responseDiagnostics.api_pagination_final_has_more === false;
  const expectedCountSource = args.responseDiagnostics.expected_profile_video_count_source ?? args.responseDiagnostics.expected_count_source ?? args.responseDiagnostics.profile_expected_count_source ?? "active_works_tab_dom_text";
  const expectedCountSelector = args.responseDiagnostics.expected_profile_video_count_selector ?? args.responseDiagnostics.expected_count_selector ?? args.responseDiagnostics.profile_expected_count_selector ?? null;
  const expectedCountRawText = args.responseDiagnostics.expected_profile_video_count_raw_text ?? args.responseDiagnostics.expected_count_raw_text ?? null;
  const expectedCountSemanticsVerified = yesNoUnknownValue22C12B(args.responseDiagnostics.expected_profile_video_count_semantics_verified ?? args.responseDiagnostics.expected_count_semantics_verified ?? (args.expectedCount != null ? "yes" : "unknown"));
  const baseDiagnostics = {
    expected_count_source: expectedCountSource,
    expected_count_selector: expectedCountSelector,
    expected_count_raw_text: expectedCountRawText,
    expected_count_semantics_verified: expectedCountSemanticsVerified,
    api_unique_aweme_ids_total: args.apiAwemeIds.size,
    api_exhausted_has_more_false: apiExhaustedHasMoreFalse ? "yes" : "no",
    final_gap_count_before_secondary_probe: gapBefore
  };
  if (gapBefore <= 0) return { totalPersisted: args.totalPersisted, recoveredCount: 0, diagnostics: { ...baseDiagnostics, secondary_gap_probe_attempted: "not_needed", secondary_gap_probe_sources: [], secondary_recovered_count: 0, final_gap_count_after_secondary_probe: gapBefore } };
  if (!apiExhaustedHasMoreFalse) return { totalPersisted: args.totalPersisted, recoveredCount: 0, diagnostics: { ...baseDiagnostics, secondary_gap_probe_attempted: "no", secondary_gap_probe_unavailable_reason: "api_not_exhausted_has_more_false", secondary_gap_probe_sources: [], secondary_recovered_count: 0, final_gap_count_after_secondary_probe: gapBefore } };
  if (args.tabId == null) return { totalPersisted: args.totalPersisted, recoveredCount: 0, diagnostics: { ...baseDiagnostics, secondary_gap_probe_attempted: "no", secondary_gap_probe_unavailable_reason: "tab_unavailable", secondary_gap_probe_sources: [], secondary_recovered_count: 0, final_gap_count_after_secondary_probe: gapBefore, final_gap_reason: "unavailable_posts_after_api_exhaustion" } };
  const probe = await chrome.tabs.sendMessage(args.tabId, { type: "DOUYIN_PROFILE_DOM_PROBE_22C11B", scan_run_id: args.scanRunId, expected_profile_url: args.profileUrl, expectedProfileVideoCount: args.expectedCount, expected_profile_video_count: args.expectedCount, traceVersion: "22C-14P" } satisfies ExtensionMessage).catch((error) => ({ ok: false, diagnostics: { error: error instanceof Error ? error.message : String(error) } })) as ExtensionMessageResponse;
  if (!probe.ok) return { totalPersisted: args.totalPersisted, recoveredCount: 0, diagnostics: { ...baseDiagnostics, secondary_gap_probe_attempted: "no", secondary_gap_probe_unavailable_reason: String(probe.reason ?? probe.error ?? "dom_probe_failed"), secondary_gap_probe_sources: [], secondary_recovered_count: 0, final_gap_count_after_secondary_probe: gapBefore, final_gap_reason: "unavailable_posts_after_api_exhaustion" } };
  const probeDiagnostics = probe.diagnostics && typeof probe.diagnostics === "object" ? probe.diagnostics as Record<string, unknown> : {};
  const probeRecord = probe.profile_dom_probe && typeof probe.profile_dom_probe === "object" ? probe.profile_dom_probe as Record<string, unknown> : {};
  const passive = tailReconcilePassiveProfilePostCandidates22C14E(args.responseDiagnostics, args.profileUrl);
  const dom = tailReconcileCandidateArray22C14E(probeDiagnostics.tail_reconcile_candidates ?? probeRecord.tail_reconcile_candidates ?? probeDiagnostics.tail_reconcile_candidate_ids ?? probeRecord.tail_reconcile_candidate_ids ?? probeDiagnostics.videoAnchors ?? probeRecord.videoAnchors, "dom_profile_probe_tail_reconcile_candidates_22C14P");
  const sources = ["passive_profile_post_network_22C14P", "dom_profile_probe_tail_reconcile_candidates_22C14P"];
  const seen = new Set(args.apiAwemeIds);
  const queue: WholeProfileHarvestQueueItem[] = [];
  const details: WholeProfileHarvestTargetDetail[] = [];
  let duplicateDrop = 0;
  let otherProfileDrop = passive.otherProfileCount;
  for (const candidate of [...passive.candidates, ...dom.candidates].slice(0, CANONICAL_SCAN_TAIL_RECONCILE_MAX_CANDIDATES_22C14E)) {
    if (queue.length >= gapBefore) break;
    if (seen.has(candidate.aweme_id)) { duplicateDrop += 1; continue; }
    if (!tailReconcileSameProfile22C14E(candidate, args.profileUrl)) { otherProfileDrop += 1; continue; }
    seen.add(candidate.aweme_id);
    const index = args.totalPersisted + queue.length + 1;
    const source = candidate.source ?? "secondary_gap_probe_22C14P";
    const evidence = { active_works_confidence: "high", source, profile_url: args.profileUrl, discovered_at: args.at };
    queue.push({ index, aweme_id: candidate.aweme_id, capture_status: "new", status: "new", attempts: 0, checkpoint_sequence: null, extraction_result: null, last_error: null, capture_inbox_item_id: null, source_url: candidate.source_url, thumbnail_url: candidate.thumbnail_url ?? null, caption: candidate.caption ?? null, profile_card_evidence: evidence });
    details.push({ index, aweme_id: candidate.aweme_id, source_url: candidate.source_url, profile_url: args.profileUrl, thumbnail_url: candidate.thumbnail_url ?? null, title: null, caption: candidate.caption ?? null, text_sample: candidate.caption ?? null, posted_text: null, posted_at: null, duration_text: null, duration_seconds: null, view_text: null, view_count: null, candidate_validation: { status: "accepted", source: "video_link", reason: source, source_url: candidate.source_url, card_context: true }, metadata_completeness: { has_profile_identity: true, has_thumbnail: candidate.thumbnail_url != null, has_title_or_caption: candidate.caption != null, has_posted_text: false, has_duration: false, has_view_count: false, has_detail_metrics: false }, capture_status: "new", backend_item: null, extraction_source: source, profile_card_evidence: evidence });
  }
  const profileIdentifier = profileIdentifierFromUrl(args.profileUrl);
  const upsert = queue.length > 0 ? await args.repository.upsertProfileTargetPage(profileIdentifier, queue, details, args.at) : null;
  const nextTotal = upsert?.total ?? args.totalPersisted;
  const recovered = Math.max(nextTotal - args.totalPersisted, 0);
  const gapAfter = args.expectedCount == null ? 0 : Math.max(args.expectedCount - nextTotal, 0);
  const reason = gapAfter <= 0 ? "none" : expectedCountSemanticsVerified === "yes" ? "expected_count_semantics_mismatch" : "unavailable_posts_after_api_exhaustion";
  return { totalPersisted: nextTotal, recoveredCount: recovered, diagnostics: { ...baseDiagnostics, secondary_gap_probe_attempted: "yes", secondary_gap_probe_sources: sources, secondary_dom_candidate_count: dom.candidates.length, secondary_dom_new_candidate_count: dom.candidates.filter((candidate) => !args.apiAwemeIds.has(candidate.aweme_id)).length, secondary_passive_network_candidate_count: passive.candidates.length, secondary_passive_network_new_candidate_count: passive.candidates.filter((candidate) => !args.apiAwemeIds.has(candidate.aweme_id)).length, secondary_recovered_count: recovered, secondary_duplicate_drop_count: duplicateDrop, secondary_invalid_drop_count: passive.invalidCount + dom.invalidCount, secondary_other_profile_drop_count: otherProfileDrop, final_gap_count_after_secondary_probe: gapAfter, final_gap_reason: reason, final_gap_evidence: `${reason}: expected=${args.expectedCount}; api_unique=${args.apiAwemeIds.size}; persisted_before_secondary=${args.totalPersisted}; persisted_after_secondary=${nextTotal}; gap_before_secondary=${gapBefore}; gap_after_secondary=${gapAfter}; secondary_dom_candidates=${dom.candidates.length}; secondary_passive_candidates=${passive.candidates.length}; secondary_recovered=${recovered}; api_has_more_false=${String(apiExhaustedHasMoreFalse)}; expected_count_source=${String(expectedCountSource)}; expected_count_raw_text=${String(expectedCountRawText)}` } };
}

function activeOverDisplayedDiagnosticsHaveExactTail22C14Q(diagnostics: Record<string, unknown>): boolean {
  const count = countSemanticsNumber22C14Q(diagnostics.over_displayed_count);
  if (count == null || count <= 0) return false;
  const ids = Array.isArray(diagnostics.over_displayed_extra_ids_exact) ? diagnostics.over_displayed_extra_ids_exact : [];
  const items = Array.isArray(diagnostics.over_displayed_extra_items_exact) ? diagnostics.over_displayed_extra_items_exact : [];
  const source = String(diagnostics.over_displayed_extra_source ?? "");
  return ids.length === count
    && items.length === count
    && (source.includes("ordered_api_tail_after_visible_count") || source.includes("ordered_accepted_api_tail_after_displayed_count"));
}

function mergeOverDisplayedDiagnosticsPreferActiveTail22C14Q(activeDiagnostics: Record<string, unknown>, repositoryDiagnostics: Record<string, unknown>): Record<string, unknown> {
  if (!activeOverDisplayedDiagnosticsHaveExactTail22C14Q(activeDiagnostics)) {
    return {
      ...activeDiagnostics,
      ...repositoryDiagnostics
    };
  }
  const merged = {
    ...repositoryDiagnostics,
    ...activeDiagnostics,
    repository_over_displayed_fallback_available: Array.isArray(repositoryDiagnostics.over_displayed_extra_ids_exact) && repositoryDiagnostics.over_displayed_extra_ids_exact.length > 0 ? "yes" : "no",
    over_displayed_diagnostics_preferred_source: "active_ordered_api_tail"
  };
  return merged;
}

function canonicalForensicVerdictForCurrentRun22C14Q(state: WholeProfileHarvestState, forensicExport: Record<string, unknown> | null | undefined): Record<string, unknown> | null {
  if (!forensicExport) return null;
  const scanRunId = typeof forensicExport.scan_run_id === "string" && forensicExport.scan_run_id.trim()
    ? forensicExport.scan_run_id.trim()
    : null;
  const currentRunId = state.scan_job.scan_job_id ?? state.run_id ?? null;
  if (!scanRunId || !currentRunId || scanRunId !== currentRunId) return null;
  const finalVerdict = typeof forensicExport.final_verdict === "string" && forensicExport.final_verdict.trim()
    ? forensicExport.final_verdict.trim()
    : null;
  if (!finalVerdict) return null;
  const sameProfileCount = typeof forensicExport.same_profile_count === "number"
    ? forensicExport.same_profile_count
    : typeof forensicExport.same_profile_validation_summary === "object" && forensicExport.same_profile_validation_summary != null && typeof (forensicExport.same_profile_validation_summary as Record<string, unknown>).same_profile_count === "number"
      ? (forensicExport.same_profile_validation_summary as Record<string, unknown>).same_profile_count as number
      : null;
  const outsideProfileCount = typeof forensicExport.outside_profile_count === "number"
    ? forensicExport.outside_profile_count
    : typeof forensicExport.same_profile_validation_summary === "object" && forensicExport.same_profile_validation_summary != null && typeof (forensicExport.same_profile_validation_summary as Record<string, unknown>).outside_profile_count === "number"
      ? (forensicExport.same_profile_validation_summary as Record<string, unknown>).outside_profile_count as number
      : null;
  const insufficientEvidenceCount = typeof forensicExport.insufficient_evidence_count === "number"
    ? forensicExport.insufficient_evidence_count
    : typeof forensicExport.same_profile_validation_summary === "object" && forensicExport.same_profile_validation_summary != null && typeof (forensicExport.same_profile_validation_summary as Record<string, unknown>).insufficient_evidence_count === "number"
      ? (forensicExport.same_profile_validation_summary as Record<string, unknown>).insufficient_evidence_count as number
      : null;
  const overDisplayedCount = typeof forensicExport.over_displayed_count === "number"
    ? forensicExport.over_displayed_count
    : sameProfileCount != null && outsideProfileCount != null && insufficientEvidenceCount != null
      ? sameProfileCount + outsideProfileCount + insufficientEvidenceCount
      : null;
  const extraIds = Array.isArray(forensicExport.extra_ids) ? forensicExport.extra_ids : [];
  const extraItems = Array.isArray(forensicExport.extra_items) ? forensicExport.extra_items : [];
  const exactProofReady = overDisplayedCount != null && overDisplayedCount > 0 && extraIds.length === overDisplayedCount && extraItems.length === overDisplayedCount;
  const basePatch = {
    forensic_export_available: finalVerdict === "ledger_missing" ? "no" : "yes",
    forensic_export_scan_run_id: scanRunId,
    forensic_export_storage_key: OVERCOLLECTION_FORENSIC_EXPORT_STORAGE_KEY_22C14Q,
    accepted_target_ledger_present: forensicExport.ledger_present === true || forensicExport.ledger_count != null ? "yes" : "no",
    accepted_target_ledger_count: forensicExport.ledger_count ?? null,
    accepted_target_ledger_matches_accepted_total: forensicExport.ledger_matches_accepted_total === true ? "yes" : forensicExport.ledger_matches_accepted_total === false ? "no" : null,
    over_displayed_boundary_start_index: forensicExport.boundary_start_index ?? null,
    over_displayed_visible_boundary_index: forensicExport.visible_boundary_index ?? null,
    over_displayed_boundary_end_index: forensicExport.boundary_end_index ?? null,
    over_displayed_count: overDisplayedCount,
    over_displayed_extra_ids_exact: extraIds,
    over_displayed_extra_items_exact: extraItems,
    over_displayed_itemized_reason_summary: typeof forensicExport.final_verdict_reason === "string" && forensicExport.final_verdict_reason.trim() ? forensicExport.final_verdict_reason.trim() : null
  } satisfies Record<string, unknown>;
  if (finalVerdict === "validated_same_profile"
    && exactProofReady
    && sameProfileCount === overDisplayedCount
    && outsideProfileCount === 0
    && insufficientEvidenceCount === 0) {
    return {
      ...basePatch,
      over_displayed_validation_status: "validated_same_profile",
      over_displayed_same_profile_validated: "yes",
      count_semantics_status: "completed_with_api_over_displayed_count",
      count_semantics_reason: "itemized_valid_same_profile_api_items_beyond_visible_count",
      scan_health_verdict: "ready_api_over_displayed_count",
      scan_health_verdict_reason: "validated_same_profile_api_over_display",
      scan_health_required_user_action: "proceed_with_non_blocking_same_profile_api_over_display_warning",
      profileScanReady: "yes"
    };
  }
  if (finalVerdict === "outside_profile_detected" && exactProofReady) {
    return {
      ...basePatch,
      over_displayed_validation_status: "outside_profile_detected",
      over_displayed_same_profile_validated: "no",
      count_semantics_status: "failed_overcollection_outside_profile",
      count_semantics_reason: typeof forensicExport.final_verdict_reason === "string" && forensicExport.final_verdict_reason.trim() ? forensicExport.final_verdict_reason.trim() : "outside_profile_detected",
      scan_health_verdict: "failed_overcollection_outside_profile",
      scan_health_verdict_reason: typeof forensicExport.final_verdict_reason === "string" && forensicExport.final_verdict_reason.trim() ? forensicExport.final_verdict_reason.trim() : "outside_profile_detected",
      scan_health_required_user_action: "review_overcollection_before_collecting",
      profileScanReady: "no"
    };
  }
  if ((finalVerdict === "needs_validation" || finalVerdict === "ledger_incomplete" || finalVerdict === "ledger_missing") && overDisplayedCount != null && overDisplayedCount > 0) {
    return {
      ...basePatch,
      over_displayed_validation_status: "needs_validation",
      over_displayed_same_profile_validated: "no",
      count_semantics_status: "overcollected_needs_validation",
      count_semantics_reason: typeof forensicExport.final_verdict_reason === "string" && forensicExport.final_verdict_reason.trim() ? forensicExport.final_verdict_reason.trim() : "over_displayed_itemized_validation_missing",
      scan_health_verdict: "failed_or_warning_overcollection_validation_needed",
      scan_health_verdict_reason: typeof forensicExport.final_verdict_reason === "string" && forensicExport.final_verdict_reason.trim() ? forensicExport.final_verdict_reason.trim() : "over_displayed_itemized_validation_missing",
      scan_health_required_user_action: "review_overcollection_before_collecting",
      profileScanReady: "no"
    };
  }
  return {
    ...basePatch,
    profileScanReady: state.layer.profile_scan_ready ? "yes" : "no"
  };
}

function applyCanonicalForensicVerdictWriteThrough22C14Q(state: WholeProfileHarvestState, forensicExport: Record<string, unknown> | null | undefined): WholeProfileHarvestState {
  const patch = canonicalForensicVerdictForCurrentRun22C14Q(state, forensicExport);
  if (!patch) return state;
  const mergeDiagnostics = (value: unknown): Record<string, unknown> => ({
    ...(value && typeof value === "object" ? value as Record<string, unknown> : {}),
    ...patch,
    forensic_export_storage_key: OVERCOLLECTION_FORENSIC_EXPORT_STORAGE_KEY_22C14Q
  });
  return {
    ...state,
    layer: {
      ...state.layer,
      profile_scan_ready: patch.profileScanReady === "yes"
    },
    profile_scan: {
      ...state.profile_scan,
      diagnostics: mergeDiagnostics(state.profile_scan.diagnostics)
    },
    verify: {
      ...state.verify,
      diagnostics: mergeDiagnostics(state.verify.diagnostics)
    },
    debug: {
      ...state.debug,
      last_request_summary: mergeDiagnostics(state.debug.last_request_summary),
      last_response_summary: mergeDiagnostics(state.debug.last_response_summary)
    }
  };
}

async function finalizePaginatedScanTerminalState22C14B(args: {
  scanRunId: string;
  profileUrl: string;
  expectedCount: number | null;
  totalPersisted: number;
  totalDiscovered: number;
  pageCount: number;
  requestCount: number;
  lastError: string | null;
  result: "success" | "incomplete" | "failed";
  responseDiagnostics: Record<string, unknown>;
}): Promise<boolean> {
  const at = new Date().toISOString();
  const operatorPersistedTotal = args.expectedCount != null && args.expectedCount > 0
    ? Math.min(args.totalPersisted, args.expectedCount)
    : args.totalPersisted;
  const stored = await chrome.storage.local.get(WHOLE_PROFILE_HARVEST_STATE_KEY).catch(() => ({} as Record<string, unknown>));
  const state = (stored[WHOLE_PROFILE_HARVEST_STATE_KEY] as WholeProfileHarvestState | undefined) ?? createWholeProfileHarvestIdleState(at);
  const profileIdentifier = profileIdentifierFromUrl(args.profileUrl);
  const repository = createProfileTargetRepository();
  const collectableStatuses: WholeProfileHarvestQueueItem["status"][] = ["new", "pending", "processing", "retry", "incomplete", "needs_metadata", "failed_recoverable"];
  const queueWindow = await repository.getProfileTargetsByStatus(profileIdentifier, collectableStatuses, LARGE_PROFILE_QUEUE_PREVIEW_WINDOW_SIZE, 0).catch(() => null);
  const queueWindowState = queueWindow
    ? buildQueueWindowFromRecords(queueWindow.records)
    : { queue: state.harvest.queue, targetDetails: state.profile_scan.target_details };
  const collectableIds = queueWindowState.queue.map((item) => item.aweme_id);
  const repositoryOverDisplayedCount = args.expectedCount == null ? 0 : Math.max(args.totalPersisted - args.expectedCount, 0);
  const repositoryOverDisplayedWindow = repositoryOverDisplayedCount > 0 && args.expectedCount != null
    ? await repository.getProfileTargetsByStatus(profileIdentifier, collectableStatuses, repositoryOverDisplayedCount, args.expectedCount).catch(() => null)
    : null;
  const repositoryOverDisplayedDiagnostics = deriveRepositoryOverDisplayedDiagnostics22C14Q(repositoryOverDisplayedWindow?.records ?? [], {
    displayedProfileCount: args.expectedCount,
    persistedCount: operatorPersistedTotal,
    requestedProfileIdentifier: profileIdentifier,
    apiResponseProfileIdentifier: typeof args.responseDiagnostics.api_response_profile_identifier === "string" ? args.responseDiagnostics.api_response_profile_identifier : null,
    existingDiagnostics: args.responseDiagnostics,
    source: repositoryOverDisplayedWindow ? "profile_target_repository_ordered_final_targets" : "profile_target_repository_ordered_final_targets_unavailable"
  });
  const responseDiagnosticsBase = mergeOverDisplayedDiagnosticsPreferActiveTail22C14Q(args.responseDiagnostics, repositoryOverDisplayedDiagnostics);
  const responseDiagnostics = (() => {
    const forensicExportCandidate = responseDiagnosticsBase.overcollection_forensic_export;
    if (!forensicExportCandidate || typeof forensicExportCandidate !== "object") return responseDiagnosticsBase;
    const forensicExport = {
      ...(forensicExportCandidate as Record<string, unknown>),
      generated_at: at,
      scan_run_id: args.scanRunId,
      requested_profile_identifier: profileIdentifier,
      profile_identifier: profileIdentifier
    };
    return {
      ...responseDiagnosticsBase,
      overcollection_forensic_export: forensicExport,
      forensic_export_scan_run_id: args.scanRunId
    };
  })();
  const nearComplete = nearCompleteExpectedGap22C14N(args.expectedCount, operatorPersistedTotal);
  const hasMoreFalse = args.responseDiagnostics.scan_job_has_more_state === false
    || args.responseDiagnostics.active_profile_post_page_fetch_has_more_state_22C14B === false;
  const paginationExhaustedComplete = hasMoreFalse && operatorPersistedTotal > 0;
  const expectedCountReached = scanPersistedMeetsExpectedCount(args.expectedCount, operatorPersistedTotal)
    || paginationExhaustedComplete;
  const countSemanticsStatus = String(responseDiagnostics.count_semantics_status ?? "");
  const countSemanticsOverDisplayedValidated = countSemanticsStatus === "completed_with_api_over_displayed_count"
    && overDisplayedItemizedProofFromDiagnostics22C14Q(responseDiagnostics).valid;
  const countSemanticsNonBlocking = countSemanticsStatus === "completed_with_displayed_count_mismatch" || countSemanticsStatus === "completed_with_partial_secondary_recovery" || countSemanticsStatus === "completed_after_secondary_recovery" || countSemanticsOverDisplayedValidated;
  const terminalReady = args.result === "success" || expectedCountReached || (args.result === "incomplete" && (nearComplete.allowed || countSemanticsNonBlocking));
  const terminalResult = expectedCountReached && args.result !== "success"
    ? "completed_with_warning"
    : args.result === "incomplete" && (nearComplete.allowed || countSemanticsNonBlocking) ? "completed_with_warning" : args.result;
  const terminalError = terminalReady
    ? null
    : args.result === "failed" || args.result === "incomplete"
      ? (args.lastError ?? (args.expectedCount != null && operatorPersistedTotal < args.expectedCount ? "expected_gap_unresolved_strict_completeness_gate" : "paginated_scan_incomplete"))
      : null;
  const postScanCounters = terminalReady
    ? await reconcileBackgroundPostScanCounters22C11B({ profileUrl: args.profileUrl, scannedTotal: operatorPersistedTotal, appliedAt: at })
    : {
      snapshot: null,
      diagnostics: {
        backend_reconciliation_skipped_for_incomplete_scan: "yes",
        post_scan_snapshot_skipped_for_incomplete_scan: "yes",
        counter_authority_blocked_for_incomplete_scan: "yes",
        post_scan_backend_reconciliation_ran: "no",
        post_scan_backend_reconciliation_status: "skipped_incomplete_scan",
        post_scan_counter_snapshot_applied: "no",
        post_scan_counter_snapshot_source: "skipped_incomplete_scan",
        post_scan_counter_overwrite_blocked: "yes"
      }
    };
  const priorRuntimeDiagnostics = {
    ...diagnosticRecordByChannel22C14C(state.debug.last_request_summary, "runtime_debug_diagnostics"),
    ...diagnosticRecordByChannel22C14C(state.debug.last_response_summary, "runtime_debug_diagnostics")
  };
  const activeFetchStatusCode = args.responseDiagnostics.active_profile_post_page_fetch_last_status_code_22C14B ?? args.responseDiagnostics.scan_job_last_status_code ?? priorRuntimeDiagnostics.active_profile_post_page_fetch_last_status_code_22C14B ?? priorRuntimeDiagnostics.scan_job_last_status_code ?? priorRuntimeDiagnostics.active_profile_post_response_status_code ?? null;
  const activeFetchStatusNonZero = activeFetchStatusCode != null && activeFetchStatusCode !== 0 && activeFetchStatusCode !== "0";
  const budgetExhaustedResumable = args.responseDiagnostics.page_budget_exhausted === "yes"
    || args.responseDiagnostics.partial_scan_resumable === "yes"
    || args.responseDiagnostics.final_gap_reason === "api_budget_exhausted_before_has_more_false";
  const scanCompletenessGateReason = terminalReady
    ? "accepted"
    : budgetExhaustedResumable
      ? "api_budget_exhausted_before_has_more_false"
      : activeFetchStatusNonZero
        ? "dom_only_fallback_under_expected_active_fetch_response_status_non_zero"
        : String(args.lastError ?? args.responseDiagnostics.scan_completeness_gate_reason ?? priorRuntimeDiagnostics.scan_completeness_gate_reason ?? "expected_gap_unresolved_strict_completeness_gate");
  const diagnostics = canonicalScanDiagnostics22C11B(args.scanRunId, "scan_finished", {
    ...withCanonicalActiveProfilePostDiagnostics22C12B({
      ...scanAuthorityDiagnostics22C14D(state),
      ...priorRuntimeDiagnostics,
      ...responseDiagnostics,
      ...postScanCounters.diagnostics,
      scan_finalization_result: terminalResult,
      scan_finalized_at: at,
      lastScannerResult: terminalResult,
      lastScannerError: terminalError ?? "none",
      scan_stop_authoritative: budgetExhaustedResumable ? "incomplete_api_budget_exhausted" : (terminalError ?? "active_profile_post_completed"),
      scan_stop_authority_source: "paginated_scan_terminal_state_22C14B",
      current_run_found_count: operatorPersistedTotal,
      scan_job_total_discovered: args.totalDiscovered,
      scan_job_total_persisted: operatorPersistedTotal,
      scan_job_duplicate_or_existing_count: Math.max(args.totalDiscovered - operatorPersistedTotal, 0),
      scan_job_page_budget: CANONICAL_SCAN_PAGE_BUDGET_22C14B,
      scan_job_stop_reason: responseDiagnostics.scan_job_stop_reason ?? responseDiagnostics.scan_stop_authoritative ?? (args.lastError ?? "active_profile_post_completed"),
      scan_job_has_more_at_stop: responseDiagnostics.scan_job_has_more_state ?? responseDiagnostics.active_profile_post_page_fetch_has_more_state_22C14B ?? state.scan_job.has_more_state ?? null,
      api_pagination_attempted: "yes",
      api_pagination_page_count: args.pageCount,
      api_pagination_request_count: args.requestCount,
      api_pagination_total_raw_targets: args.totalDiscovered,
      api_pagination_total_accepted_targets: operatorPersistedTotal,
      api_pagination_total_persisted_targets: operatorPersistedTotal,
      api_pagination_total_persisted: operatorPersistedTotal,
      api_pagination_expected: args.expectedCount,
      api_pagination_remaining: args.expectedCount == null ? null : Math.max(args.expectedCount - operatorPersistedTotal, 0),
      api_pagination_duplicate_or_existing_count: Math.max(args.totalDiscovered - operatorPersistedTotal, 0),
      api_pagination_final_has_more: args.responseDiagnostics.scan_job_has_more_state ?? args.responseDiagnostics.active_profile_post_page_fetch_has_more_state_22C14B ?? state.scan_job.has_more_state ?? null,
      api_pagination_has_more_final: args.responseDiagnostics.scan_job_has_more_state ?? args.responseDiagnostics.active_profile_post_page_fetch_has_more_state_22C14B ?? state.scan_job.has_more_state ?? null,
      api_pagination_final_cursor: args.responseDiagnostics.scan_job_cursor ?? args.responseDiagnostics.active_profile_post_page_fetch_next_cursor_22C14B ?? state.scan_job.cursor,
      api_pagination_stop_reason: args.responseDiagnostics.scan_job_stop_reason ?? args.responseDiagnostics.scan_stop_authoritative ?? (args.lastError ?? "active_profile_post_completed"),
      scan_mode: "api_profile_post_pagination",
      scan_mode_visible_scroll_required: "no",
      scan_mode_scroll_policy: "api_primary_template_warmup_may_dispatch_single_scroll_only",
      scan_job_pages_fetched: args.pageCount,
      scan_job_request_count: args.requestCount,
      scan_progress_update_seq: args.requestCount,
      scan_progress_updated_at: at,
      scan_progress_delivery_channel: "storage.local.checkpoint",
      scan_progress_discovered: operatorPersistedTotal,
      scan_progress_expected: args.expectedCount,
      scan_progress_remaining: args.expectedCount == null ? null : Math.max(args.expectedCount - operatorPersistedTotal, 0),
      scan_progress_pages: args.pageCount,
      scan_progress_requests: args.requestCount,
      scan_progress_phase_label: "Finalizing scan",
      expected_profile_video_count: args.expectedCount,
      displayed_profile_count: args.expectedCount,
      api_discovered_count_before_cap: args.totalPersisted > operatorPersistedTotal ? args.totalPersisted : null,
      profile_queue_total_count: operatorPersistedTotal,
      persisted_total_count: operatorPersistedTotal,
      large_profile_mode: operatorPersistedTotal > queueWindowState.queue.length ? "yes" : "no",
      queue_total_persisted: operatorPersistedTotal,
      queue_total_visible: queueWindowState.queue.length,
      queue_counter_authority: args.totalPersisted > queueWindowState.queue.length ? "queue_total_persisted" : "scan_queue",
      profile_scan_completion_ratio: args.expectedCount != null ? `${operatorPersistedTotal}/${args.expectedCount}` : String(operatorPersistedTotal),
      scan_completeness_gate_result: terminalReady ? "accepted" : "blocked",
      scan_completeness_gate_reason: scanCompletenessGateReason,
      scan_completeness_expected_count: args.expectedCount,
      scan_completeness_found_count: operatorPersistedTotal,
      scan_completeness_missing_count: args.expectedCount == null ? null : Math.max(args.expectedCount - operatorPersistedTotal, 0),
      scan_completeness_active_fetch_meaningful: terminalReady || budgetExhaustedResumable ? "yes" : "no",
      scan_completeness_dom_only_fallback: terminalReady || budgetExhaustedResumable ? "no" : "yes",
      scan_completeness_ready_blocked: terminalReady || budgetExhaustedResumable ? "no" : "yes",
      continuation_available: args.responseDiagnostics.continuation_available ?? (budgetExhaustedResumable ? "yes" : "no"),
      continuation_cursor: args.responseDiagnostics.continuation_cursor ?? args.responseDiagnostics.scan_job_cursor ?? args.responseDiagnostics.active_profile_post_page_fetch_next_cursor_22C14B ?? state.scan_job.cursor,
      continuation_reason: args.responseDiagnostics.continuation_reason ?? (budgetExhaustedResumable ? "page_budget_exhausted" : "none"),
      partial_scan_resumable: args.responseDiagnostics.partial_scan_resumable ?? (budgetExhaustedResumable ? "yes" : "no"),
      page_budget_limit: args.responseDiagnostics.page_budget_limit ?? CANONICAL_SCAN_PAGE_BUDGET_22C14B,
      page_budget_exhausted: args.responseDiagnostics.page_budget_exhausted ?? (budgetExhaustedResumable ? "yes" : "no"),
      source_failure: args.responseDiagnostics.source_failure ?? (budgetExhaustedResumable ? "no" : "unknown"),
      active_profile_post_source_healthy: args.responseDiagnostics.active_profile_post_source_healthy ?? (budgetExhaustedResumable ? "yes" : "unknown"),
      canonical_terminal_state: terminalResult,
      canonical_finalizer_version: "22C-14Q-count-semantics-terminal",
      paginated_near_complete_promoted_22C14N: nearComplete.allowed ? "yes" : "no",
      paginated_near_complete_gap_22C14N: nearComplete.gap,
      paginated_near_complete_threshold_22C14N: nearComplete.threshold,
      canonical_finalizer_ran: "yes",
      canonical_lock_release_ran: "yes",
      canonical_lock_release_reason: args.result,
      profileScanReady: terminalReady ? "yes" : "no"
    }),
    active_profile_post_fetch_page_count: args.pageCount,
    active_profile_post_fetch_request_count: args.requestCount,
    ...Object.fromEntries(Object.entries(responseDiagnostics).filter(([key]) => key.startsWith("api_") || key.startsWith("background_") || key.startsWith("repository_") || key === "expected_count")),
    active_profile_post_fetch_target_count: responseDiagnostics.api_pagination_accepted_targets_total ?? responseDiagnostics.api_targets_returned_to_background_total ?? args.totalPersisted,
    active_profile_post_fetch_raw_items_total: responseDiagnostics.api_pagination_raw_items_total ?? responseDiagnostics.api_raw_items_total,
    active_profile_post_fetch_raw_aweme_ids_total: responseDiagnostics.api_pagination_raw_aweme_ids_total ?? responseDiagnostics.api_raw_aweme_ids_total,
    raw_accounting_unavailable_reason: responseDiagnostics.raw_accounting_unavailable_reason,
    final_gap_count: responseDiagnostics.final_gap_count,
    final_gap_reason: responseDiagnostics.final_gap_reason,
    final_gap_classification: responseDiagnostics.final_gap_classification,
    final_gap_evidence: responseDiagnostics.final_gap_evidence
  });
  const diagnosticsChannels = splitCanonicalScanDiagnosticsChannels22C11B(diagnostics);
  const next: WholeProfileHarvestState = appendWholeProfileTrace({
    ...state,
    status: terminalReady ? "verified" : "failed",
    phase: "scan_finished",
    profile_url: args.profileUrl,
    layer: { ...state.layer, profile_scan_ready: terminalReady, harvest_ready: terminalReady },
    workflow: {
      ...state.workflow,
      scan: { ...state.workflow.scan, status: terminalReady ? "success" : "failed", updated_at: at, completed_at: at, last_error: terminalError },
      classification: { ...state.workflow.classification, status: terminalReady ? "success" : state.workflow.classification.status, started_at: state.workflow.classification.started_at ?? at, updated_at: at, completed_at: terminalReady ? at : state.workflow.classification.completed_at, last_error: terminalError },
      active_task: null,
      action_lock: null
    },
    scan_job: {
      ...state.scan_job,
      scan_job_id: args.scanRunId,
      status: terminalReady ? "completed" : "failed",
      profile_identifier: profileIdentifier,
      total_discovered: args.totalDiscovered,
      total_persisted: operatorPersistedTotal,
      expected_count: args.expectedCount,
      cursor: typeof responseDiagnostics.scan_job_cursor === "string" || typeof responseDiagnostics.scan_job_cursor === "number"
        ? responseDiagnostics.scan_job_cursor
        : state.scan_job.cursor,
      has_more_state: responseDiagnostics.scan_job_has_more_state === true || responseDiagnostics.active_profile_post_page_fetch_has_more_state_22C14B === true
        ? true
        : responseDiagnostics.scan_job_has_more_state === false || responseDiagnostics.active_profile_post_page_fetch_has_more_state_22C14B === false
          ? false
          : state.scan_job.has_more_state,
      page_count: args.pageCount,
      request_count: args.requestCount,
      last_error: terminalError,
      updated_at: at,
      completed_at: at,
      next_retry_at: null,
      remaining_estimate: args.expectedCount == null ? null : Math.max(args.expectedCount - operatorPersistedTotal, 0)
    },
    profile_scan: { ...state.profile_scan, status: terminalReady ? "success" : "failed", accepted_target_count: operatorPersistedTotal, stop_reason: terminalError, scan_rounds: Math.max(state.profile_scan.scan_rounds, args.pageCount), target_details: queueWindowState.targetDetails, diagnostics: diagnosticsChannels.scanAuthorityDiagnostics },
    verify: { ...state.verify, status: terminalReady ? "success" : "failed", completed_at: at, accepted_target_count: operatorPersistedTotal, verified_target_count: operatorPersistedTotal, stop_reason: terminalError, scan_rounds: Math.max(state.verify.scan_rounds, args.pageCount), target_details: queueWindowState.targetDetails, diagnostics: diagnosticsChannels.scanAuthorityDiagnostics },
    classification: terminalReady ? {
      ...emptyClassificationState(),
      status: "success",
      started_at: state.classification.started_at ?? at,
      completed_at: at,
      last_error: null,
      profile_url: args.profileUrl,
      schema_version: "douyin_profile_video_classification_result.v1",
      collection_mode: "paginated_profile_post_scan_22C14N",
      database_lookup_status: "not_checked_paginated_terminal",
      total_candidates: operatorPersistedTotal,
      counts: { ...emptyClassificationCounts(), new: operatorPersistedTotal, collect: operatorPersistedTotal },
      targets: [],
      collect_aweme_ids: collectableIds,
      skip_aweme_ids: [],
      diagnostics: { source: "paginated_terminal_repository_22C14N", classification_bypassed: true, total_persisted: operatorPersistedTotal, preview_count: collectableIds.length }
    } : state.classification,
    harvest: { ...state.harvest, queue: queueWindowState.queue, queue_preview: buildCollectQueuePreviewFromQueue(queueWindowState.queue, queueWindowState.targetDetails), planned_total: operatorPersistedTotal, pending: operatorPersistedTotal },
    post_scan_counter_snapshot: terminalReady ? postScanCounters.snapshot : null,
    debug: { ...state.debug, last_action_result: terminalResult, last_action_error: terminalError, last_action_finished_at: at, active_task: null, busy_source: null, last_request_summary: diagnosticsChannels.runtimeDebugDiagnostics, last_response_summary: diagnosticsChannels.runtimeDebugDiagnostics },
    last_error: terminalError ? `${terminalError}: Paginated Scan Profile finished incomplete.` : null,
    updated_at: at
  }, `scan_profile.22C14B.terminal.${terminalResult}`, `Paginated scan terminal ${terminalResult}.`, diagnosticsChannels.scanAuthorityDiagnostics, at);
  const forensicExportForStorage = responseDiagnostics.overcollection_forensic_export && typeof responseDiagnostics.overcollection_forensic_export === "object"
    ? responseDiagnostics.overcollection_forensic_export as Record<string, unknown>
    : null;
  const canonicalWithForensicWriteThrough = applyCanonicalForensicVerdictWriteThrough22C14Q(next, forensicExportForStorage);
  const preparedNext = prepareWholeProfileHarvestStateForStorage22C11B(canonicalWithForensicWriteThrough);
  await safeSetScannerStorage22C11B({
    [WHOLE_PROFILE_HARVEST_STATE_KEY]: preparedNext,
    ...(forensicExportForStorage ? { [OVERCOLLECTION_FORENSIC_EXPORT_STORAGE_KEY_22C14Q]: forensicExportForStorage } : {})
  }, { stage: "scan_job_terminal_22C14B" });
  const runtimeDelivery = chrome.runtime.sendMessage?.({ type: "douyinScanner:stateChanged", state: preparedNext });
  if (runtimeDelivery && typeof runtimeDelivery.catch === "function") runtimeDelivery.catch(() => undefined);
  return terminalReady;
}

type OverDisplayedItemReason22C14Q =
  | "valid_same_profile_api_item_beyond_visible_count_basis"
  | "valid_same_profile_api_item_not_counted_by_visible_dom"
  | "valid_same_profile_pinned_or_special_item"
  | "valid_same_profile_item_hidden_from_visible_count_basis"
  | "profile_identity_not_proven"
  | "possible_cross_profile_contamination"
  | "possible_ordering_or_count_basis_mismatch"
  | "unknown_needs_manual_review";

type PaginatedSameProfileEvidence22C14Q = {
  awemeId: string;
  profileUrl: string | null;
  profileIdentifier: string | null;
  pageIndexFound: number | null;
  requestIndexFound: number | null;
  rawIndexFound?: number | null;
  sourceEndpoint: string | null;
  sourceCursor: string | number | null;
  sourceProfileIdentifier: string | null;
  targetProfileIdentifier: string | null;
  authorId?: string | null;
  authorSecUid?: string | null;
  authorUniqueId?: string | null;
  requestedProfileSecUid?: string | null;
  sameProfileValidationStatus?: "same_profile_validated" | "missing_evidence" | "outside_profile_detected" | "same_profile" | "outside_profile" | "insufficient_evidence";
  sameProfileMissingEvidence?: string[];
  desc?: string | null;
  createTime?: number | null;
  sameProfileValidated: "yes" | "no";
  sameProfileValidationReason: string;
  isPinnedCandidate: "yes" | "no" | "unknown";
  isSpecialTabCandidate: "yes" | "no" | "unknown";
  appearsInDomGrid: "yes" | "no" | "unknown";
  appearsInVisibleProfileCountBasis: "yes" | "no" | "unknown";
  itemReason: OverDisplayedItemReason22C14Q;
};

type PaginatedAcceptedTargetEvidence22C14Q = PaginatedSameProfileEvidence22C14Q & {
  acceptedIndex: number;
  sourceTemplateId: string | null;
};

type DouyinProfileIdentityNormalization22C14S = {
  raw: string | null;
  normalizedSecUid: string | null;
  normalizedProfileUrl: string | null;
  kind: "sec_uid" | "profile_url" | "unknown";
};

function normalizeDouyinProfileIdentity22C14S(value: unknown): DouyinProfileIdentityNormalization22C14S {
  const raw = typeof value === "string" ? value.trim() : value == null ? null : String(value).trim();
  if (!raw) return { raw: null, normalizedSecUid: null, normalizedProfileUrl: null, kind: "unknown" };
  const markdownLinkMatch = raw.match(/^\s*\[([^\]]+)\]\(([^)]+)\)\s*$/);
  const candidate = (markdownLinkMatch?.[2] ?? markdownLinkMatch?.[1] ?? raw).trim();
  const withoutEscapes = candidate.replace(/\\_/g, "_");
  const decoded = (() => {
    try {
      return decodeURIComponent(withoutEscapes);
    } catch {
      return withoutEscapes;
    }
  })();
  const urlLike = /^https?:\/\//i.test(decoded) || /^www\.douyin\.com\//i.test(decoded) || /^douyin\.com\//i.test(decoded);
  const urlCandidate = /^https?:\/\//i.test(decoded) ? decoded : urlLike ? `https://${decoded}` : null;
  if (urlCandidate != null) {
    try {
      const url = new URL(urlCandidate);
      const userSegmentIndex = url.pathname.split("/").findIndex((segment) => segment === "user");
      const secUid = userSegmentIndex >= 0 ? url.pathname.split("/")[userSegmentIndex + 1] ?? null : null;
      const normalizedSecUid = secUid?.trim() || null;
      return {
        raw,
        normalizedSecUid,
        normalizedProfileUrl: normalizedSecUid == null ? null : `https://www.douyin.com/user/${normalizedSecUid}`,
        kind: normalizedSecUid == null ? "unknown" : "profile_url"
      };
    } catch {
      return { raw, normalizedSecUid: null, normalizedProfileUrl: null, kind: "unknown" };
    }
  }
  const compact = decoded.replace(/^@/, "").trim();
  return {
    raw,
    normalizedSecUid: compact || null,
    normalizedProfileUrl: compact ? `https://www.douyin.com/user/${compact}` : null,
    kind: compact ? "sec_uid" : "unknown"
  };
}

type AcceptedTargetLedgerEntry22C14Q = {
  aweme_id: string;
  accepted_index: number;
  page_index: number;
  raw_index_in_page: number;
  source: "active_profile_post_api";
  endpoint_path: string | null;
  request_url_path: string | null;
  request_cursor: string | number | null;
  response_cursor: string | number | null;
  request_profile_identifier: string | null;
  request_sec_uid: string | null;
  api_template_profile_identifier: string | null;
  api_template_sec_uid: string | null;
  author_uid: string | null;
  author_sec_uid: string | null;
  author_unique_id: string | null;
  normalized_author_sec_uid?: string | null;
  normalized_request_sec_uid?: string | null;
  normalized_api_template_sec_uid?: string | null;
  normalized_request_profile_sec_uid?: string | null;
  normalized_api_template_profile_sec_uid?: string | null;
  normalized_repository_profile_sec_uid?: string | null;
  same_profile_validation_compared_fields?: string[];
  desc_sample: string | null;
  create_time: string | number | null;
  same_profile_validation_status: "same_profile" | "outside_profile" | "insufficient_evidence";
  same_profile_validation_reason: string;
  profile_match_evidence: string[];
  raw_profile_match_evidence?: string[];
  same_profile_missing_evidence?: string[];
};

const OVERCOLLECTION_FORENSIC_EXPORT_STORAGE_KEY_22C14Q = "douyinWholeProfileHarvestOvercollectionForensicExport";

type OvercollectionForensicExportVerdict22C14Q = "validated_same_profile" | "outside_profile_detected" | "needs_validation" | "ledger_missing" | "ledger_incomplete";

type OvercollectionForensicExport22C14Q = {
  purpose: "scan_profile_overcollection_forensic_export";
  build_id: string;
  generated_at: string;
  scan_run_id: string;
  requested_profile_identifier: string | null;
  profile_identifier: string | null;
  displayed_profile_count: number | null;
  api_unique_count: number;
  persisted_count: number;
  over_displayed_count: number;
  ledger_present: boolean;
  ledger_count: number;
  ledger_matches_accepted_total: boolean;
  boundary_start_index: number | null;
  visible_boundary_index: number | null;
  boundary_end_index: number | null;
  boundary_window: AcceptedTargetLedgerEntry22C14Q[];
  extra_items: AcceptedTargetLedgerEntry22C14Q[];
  extra_ids: string[];
  same_profile_validation_summary: {
    same_profile_count: number;
    outside_profile_count: number;
    insufficient_evidence_count: number;
  };
  final_verdict: OvercollectionForensicExportVerdict22C14Q;
  final_verdict_reason: string;
  exported_item_count: number;
  extra_item_count: number;
};

type PaginatedScanAccounting22C14B = {
  rawItemsTotal: number;
  rawAwemeIdsTotal: number;
  uniqueAwemeIds: Set<string>;
  uniqueAwemeIdOrder: string[];
  orderedAcceptedTargets?: PaginatedAcceptedTargetEvidence22C14Q[];
  acceptedTargetLedger?: AcceptedTargetLedgerEntry22C14Q[];
  sameProfileEvidenceByAwemeId: Map<string, PaginatedSameProfileEvidence22C14Q>;
  requestedProfileIdentifier: string | null;
  apiResponseProfileIdentifier: string | null;
  targetsReturnedToBackgroundTotal: number;
  backgroundTargetsReceivedTotal: number;
  backgroundTargetsAfterValidationTotal: number;
  backgroundDuplicateDropTotal: number;
  backgroundInvalidDropTotal: number;
  otherProfileDropCount: number;
  favoriteEndpointDropCount: number;
  emptyOrMissingAwemeIdCount: number;
  repositoryExistingBeforeTotal: number;
  repositoryWriteInputCount: number;
  repositoryNewInsertedTotal: number;
  repositoryDuplicateExistingTotal: number;
  repositoryWriteTotalAfter: number;
  perPageRawCounts: number[];
  perPageRawAwemeIdCounts: number[];
  perPageReturnedTargetCounts: number[];
  perPageUniqueNewCounts: number[];
  perPageDuplicateCounts: number[];
  perPageCursorValues: Array<string | number | null>;
  perPageCursorPresentFlags: boolean[];
  perPageHasMoreFlags: Array<boolean | null>;
  perPageStatusCodes: Array<number | string | null>;
  perPageParserRoutes: Array<string | null>;
  perPagePersistedTotals: number[];
  firstPageRawCount: number | null;
  lastPageRawCount: number | null;
  lastPageAcceptedCount: number | null;
  lastPagePersistedDelta: number | null;
  finalHasMore: boolean | null;
  finalCursorPresent: boolean | null;
  finalStatusCode: number | string | null;
};

type CountSemanticsStatus22C14Q = "full_match" | "completed_with_displayed_count_mismatch" | "incomplete_internal_loss" | "incomplete_api_not_exhausted" | "completed_after_secondary_recovery" | "completed_with_partial_secondary_recovery" | "completed_with_api_over_displayed_count" | "overcollected_needs_validation" | "overcollected_forensic_ledger_missing" | "failed_overcollection_outside_profile";
type ScanHealthVerdict22C14R = "ready_full_match" | "ready_displayed_count_mismatch_explained" | "ready_after_secondary_recovery" | "ready_api_over_displayed_count" | "failed_or_warning_overcollection_validation_needed" | "failed_overcollection_outside_profile" | "failed_api_template_unavailable_after_recovery" | "failed_internal_accounting_loss" | "failed_unknown";

function scanHealthVerdictDiagnostics22C14R(source: Record<string, unknown>): Record<string, unknown> {
  const countStatus = typeof source.count_semantics_status === "string" ? source.count_semantics_status : "";
  const countReason = typeof source.count_semantics_reason === "string" ? source.count_semantics_reason : "unknown";
  const stopReason = String(source.active_profile_post_fetch_stop_reason ?? source.active_profile_post_page_fetch_stop_reason_22C14B ?? source.scan_job_stop_reason ?? source.scan_stop_authoritative ?? source.scan_job_last_error ?? source.lastScannerError ?? "");
  const recoveryResult = String(source.template_recovery_result ?? source.template_recovery_final_strategy ?? source.active_profile_post_template_warmup_stop_reason ?? "");
  const templateUnavailable = [stopReason, recoveryResult].some((value) => /template_unavailable|usable_template_unavailable|template_not_found_after_warmup|fallback_unavailable|required_query_keys_unavailable|direct_api_fallback_response_rejected|direct_api_fallback_request_pending_or_failed/i.test(value));
  const overDisplayedProof = overDisplayedItemizedProofFromDiagnostics22C14Q(source);
  const overDisplayedCount = Math.max(0, countSemanticsNumber22C14Q(source.over_displayed_count) ?? 0);
  const outsideProfileOffendingAwemeIds = overDisplayedOutsideProfileOffenderIds22C14Q(overDisplayedCount, source.over_displayed_extra_ids_exact, source.over_displayed_extra_items_exact);
  const outsideProfileVerdictWithoutItemizedOffenders = countStatus === "failed_overcollection_outside_profile" && outsideProfileOffendingAwemeIds.length === 0;
  const readyOverdisplayWithoutItemizedProof = (countStatus === "completed_with_api_over_displayed_count" && !overDisplayedProof.valid) || outsideProfileVerdictWithoutItemizedOffenders;
  const normalizedCountStatus = outsideProfileVerdictWithoutItemizedOffenders ? "overcollected_needs_validation" : countStatus;
  const verdict: ScanHealthVerdict22C14R = normalizedCountStatus === "full_match"
    ? "ready_full_match"
    : normalizedCountStatus === "completed_after_secondary_recovery"
      ? "ready_after_secondary_recovery"
      : normalizedCountStatus === "completed_with_api_over_displayed_count"
        ? readyOverdisplayWithoutItemizedProof ? "failed_or_warning_overcollection_validation_needed" : "ready_api_over_displayed_count"
        : normalizedCountStatus === "failed_overcollection_outside_profile"
          ? "failed_overcollection_outside_profile"
          : normalizedCountStatus === "overcollected_needs_validation" || normalizedCountStatus === "overcollected_forensic_ledger_missing"
            ? "failed_or_warning_overcollection_validation_needed"
            : normalizedCountStatus === "completed_with_displayed_count_mismatch" || normalizedCountStatus === "completed_with_partial_secondary_recovery"
            ? "ready_displayed_count_mismatch_explained"
            : countStatus === "incomplete_internal_loss"
              ? "failed_internal_accounting_loss"
              : countStatus === "incomplete_api_not_exhausted" && templateUnavailable
                ? "failed_api_template_unavailable_after_recovery"
                : normalizedCountStatus === "incomplete_api_not_exhausted"
                  ? "failed_unknown"
                  : templateUnavailable
                    ? "failed_api_template_unavailable_after_recovery"
                    : "failed_unknown";
  const reason = outsideProfileVerdictWithoutItemizedOffenders
    ? "over_displayed_itemized_validation_missing"
    : readyOverdisplayWithoutItemizedProof
      ? `ready_overdisplay_without_itemized_proof:${overDisplayedProof.missing.join(",") || countReason}`
    : verdict === "failed_overcollection_outside_profile"
      ? `failed_overcollection_outside_profile:${String(source.over_displayed_validation_failure_reason ?? countReason)}`
      : verdict === "failed_api_template_unavailable_after_recovery"
        ? `api_template_unavailable_after_recovery:${stopReason || recoveryResult || countReason}`
        : verdict === "failed_unknown"
          ? `unknown_scan_health:${countReason}`
          : countReason;
  const requiredAction = verdict === "ready_full_match" || verdict === "ready_after_secondary_recovery"
    ? "usable_no_retry_needed_continue_to_collect"
    : verdict === "ready_api_over_displayed_count"
      ? "usable_with_api_over_displayed_same_profile_warning_continue_to_collect"
      : verdict === "ready_displayed_count_mismatch_explained"
        ? "usable_with_explained_gap_review_then_continue_or_retry_if_operator_disagrees"
        : verdict === "failed_or_warning_overcollection_validation_needed"
          ? "retry_scan_profile_or_preserve_diagnostics_for_same_profile_validation_review"
          : verdict === "failed_overcollection_outside_profile"
            ? "preserve_diagnostics_block_collection_outside_profile_overcollection"
            : verdict === "failed_api_template_unavailable_after_recovery"
              ? "retry_scan_profile_after_reload_login_or_network_check"
            : verdict === "failed_internal_accounting_loss"
              ? "real_failure_preserve_diagnostics_and_report_internal_accounting_loss"
              : "retry_scan_profile_and_preserve_compact_diagnostics_if_repeated";
  return {
    scan_health_verdict: verdict,
    scan_health_verdict_reason: reason,
    scan_health_required_user_action: requiredAction,
    ready_overdisplay_without_itemized_proof: readyOverdisplayWithoutItemizedProof ? "yes" : source.ready_overdisplay_without_itemized_proof ?? "no",
    ready_overdisplay_without_itemized_proof_reasons: readyOverdisplayWithoutItemizedProof ? overDisplayedProof.missing : source.ready_overdisplay_without_itemized_proof_reasons ?? [],
    over_displayed_outside_profile_offending_aweme_ids: outsideProfileOffendingAwemeIds,
    outside_profile_verdict_without_itemized_offenders: outsideProfileVerdictWithoutItemizedOffenders ? "yes" : "no"
  };
}

type CountSemanticsDiagnosticsInput22C14Q = {
  displayedProfileCount: number | null;
  displayedProfileCountSource?: unknown;
  displayedProfileCountRawText?: unknown;
  apiRawCount: number;
  apiUniqueCount: number;
  apiHasMoreFinal: boolean | null;
  collectableCount: number;
  persistedCount: number;
  secondaryRecoveryAttempted?: unknown;
  secondaryRecoveredCount?: number;
  parserExtractionDropCount: number;
  validationOrProfileDropCount: number;
  repositoryDropCount: number;
  apiDuplicateAwemeIdsTotal: number;
  overDisplayedSameProfileValidated?: unknown;
  overDisplayedExtraIdsSample?: unknown;
  overDisplayedExtraIdsExact?: unknown;
  overDisplayedExtraItemsExact?: unknown;
  overDisplayedItemizedReasonSummary?: unknown;
  overDisplayedExtraSource?: unknown;
  overDisplayedExtraCount?: number;
  extraIdsSameProfileMatchCount?: number;
  extraIdsProfileMismatchCount?: number;
  overDisplayedValidationStatus?: unknown;
  overDisplayedValidationFailureReason?: unknown;
  overDisplayedReason?: unknown;
  overDisplayedCameFromContinuationTail?: unknown;
  requestedProfileIdentifier?: unknown;
  apiResponseProfileIdentifier?: unknown;
  repositoryProfileIdentifier?: unknown;
  repositoryExistingBeforeTotal?: number;
  repositoryExistingSameProfileTotal?: number;
  repositoryExistingOtherProfileTotal?: number;
  templateCacheProfileMatch?: unknown;
  directApiTemplateProfileMatch?: unknown;
  continuationBatchNewCount?: number;
  continuationBatchRawCount?: number;
  continuationBatchAcceptedCount?: number;
  persistedTotalBeforeContinuation?: number;
  persistedTotalAfterContinuation?: number;
  finalCumulativeCollectableCount?: number;
  finalDisplayAuthority?: unknown;
  finalHeaderCount?: number;
  finalCounterCount?: number;
  headerCounterAuthorityMatch?: unknown;
};

function countSemanticsNumber22C14Q(value: unknown): number | null {
  const numeric = typeof value === "number" ? value : typeof value === "string" && value.trim() ? Number(value) : Number.NaN;
  return Number.isFinite(numeric) ? numeric : null;
}

type OverDisplayedItemizedProof22C14Q = {
  valid: boolean;
  missing: string[];
  count: number;
};

function nonEmptyString22C14Q(value: unknown): boolean {
  return typeof value === "string" && value.trim().length > 0;
}

function arrayLength22C14Q(value: unknown): number {
  return Array.isArray(value) ? value.length : 0;
}

function overDisplayedItemObjectValue22C14Q(item: Record<string, unknown>, ...keys: string[]): unknown {
  for (const key of keys) {
    if (item[key] != null) return item[key];
  }
  return null;
}

function overDisplayedOutsideProfileOffenderIds22C14Q(overDisplayedCount: number, idsValue: unknown, itemsValue: unknown): string[] {
  if (overDisplayedCount <= 0) return [];
  const ids = Array.isArray(idsValue) ? idsValue : [];
  const items = Array.isArray(itemsValue) ? itemsValue : [];
  if (ids.length !== overDisplayedCount || items.length !== overDisplayedCount) return [];
  return items.flatMap((raw, index) => {
    if (!raw || typeof raw !== "object") return [];
    const item = raw as Record<string, unknown>;
    const status = String(item.same_profile_validation_status ?? item.over_displayed_validation_status ?? "");
    const reason = String(item.same_profile_validation_reason ?? item.item_reason ?? item.over_displayed_validation_failure_reason ?? "");
    const requested = typeof item.requested_profile_identifier === "string" && item.requested_profile_identifier.trim()
      ? item.requested_profile_identifier.trim()
      : typeof item.target_profile_identifier === "string" && item.target_profile_identifier.trim()
        ? item.target_profile_identifier.trim()
        : null;
    const source = typeof item.profile_identifier === "string" && item.profile_identifier.trim()
      ? item.profile_identifier.trim()
      : typeof item.source_profile_identifier === "string" && item.source_profile_identifier.trim()
        ? item.source_profile_identifier.trim()
        : typeof item.author_sec_uid === "string" && item.author_sec_uid.trim()
          ? item.author_sec_uid.trim()
          : null;
    const mismatch = status === "outside_profile_detected" || status === "outside_profile" || /profile_identifier_mismatch|cross_profile|outside_profile|mismatch_requested_profile/i.test(reason) || (source != null && requested != null && source !== requested);
    if (!mismatch) return [];
    const awemeId = typeof item.aweme_id === "string" && item.aweme_id.trim()
      ? item.aweme_id.trim()
      : typeof ids[index] === "string" && String(ids[index]).trim()
        ? String(ids[index]).trim()
        : null;
    return awemeId ? [awemeId] : [];
  });
}

function overDisplayedItemizedProof22C14Q(source: {
  overDisplayedCount: number;
  overDisplayedExtraIdsExact?: unknown;
  overDisplayedExtraItemsExact?: unknown;
  overDisplayedValidationStatus?: unknown;
  overDisplayedSameProfileValidated?: unknown;
  overDisplayedItemizedReasonSummary?: unknown;
}): OverDisplayedItemizedProof22C14Q {
  const count = Math.max(0, source.overDisplayedCount);
  if (count <= 0) return { valid: true, missing: [], count };
  const missing = new Set<string>();
  const ids = Array.isArray(source.overDisplayedExtraIdsExact) ? source.overDisplayedExtraIdsExact : [];
  const items = Array.isArray(source.overDisplayedExtraItemsExact) ? source.overDisplayedExtraItemsExact : [];
  if (ids.length !== count) missing.add("over_displayed_extra_ids_exact_length_mismatch");
  if (items.length !== count) missing.add("over_displayed_extra_items_exact_length_mismatch");
  if (source.overDisplayedValidationStatus !== "validated_same_profile") missing.add("over_displayed_validation_status_not_validated_same_profile");
  if (source.overDisplayedSameProfileValidated !== "yes" && source.overDisplayedSameProfileValidated !== true) missing.add("over_displayed_same_profile_validated_not_yes");
  if (!nonEmptyString22C14Q(source.overDisplayedItemizedReasonSummary)) missing.add("over_displayed_itemized_reason_summary_empty");
  items.forEach((raw, index) => {
    if (!raw || typeof raw !== "object") {
      missing.add(`over_displayed_extra_item_${index}_not_object`);
      return;
    }
    const item = raw as Record<string, unknown>;
    if (!nonEmptyString22C14Q(item.aweme_id)) missing.add(`over_displayed_extra_item_${index}_aweme_id_missing`);
    if (countSemanticsNumber22C14Q(overDisplayedItemObjectValue22C14Q(item, "page_index", "page_index_found")) == null) missing.add(`over_displayed_extra_item_${index}_page_evidence_missing`);
    if (countSemanticsNumber22C14Q(overDisplayedItemObjectValue22C14Q(item, "raw_index", "raw_index_found")) == null) missing.add(`over_displayed_extra_item_${index}_raw_index_missing`);
    if (countSemanticsNumber22C14Q(overDisplayedItemObjectValue22C14Q(item, "accepted_index", "accepted_index_in_api_order", "index_in_final_order")) == null) missing.add(`over_displayed_extra_item_${index}_accepted_index_missing`);
    if (!nonEmptyString22C14Q(overDisplayedItemObjectValue22C14Q(item, "source_endpoint", "source_url"))) missing.add(`over_displayed_extra_item_${index}_source_endpoint_missing`);
    const cursorOrTemplateEvidence = overDisplayedItemObjectValue22C14Q(item, "source_cursor", "cursor", "page_marker", "source_template_id");
    if (!nonEmptyString22C14Q(cursorOrTemplateEvidence) && countSemanticsNumber22C14Q(cursorOrTemplateEvidence) == null) missing.add(`over_displayed_extra_item_${index}_cursor_or_template_missing`);
    if (item.same_profile_validated !== "yes") missing.add(`over_displayed_extra_item_${index}_same_profile_not_validated`);
    if (!nonEmptyString22C14Q(overDisplayedItemObjectValue22C14Q(item, "author_sec_uid", "author_user_id", "author_id", "source_profile_identifier", "target_profile_identifier", "requested_profile_identifier"))) missing.add(`over_displayed_extra_item_${index}_ownership_evidence_missing`);
  });
  return { valid: missing.size === 0, missing: Array.from(missing), count };
}

function overDisplayedItemizedProofFromDiagnostics22C14Q(source: Record<string, unknown>): OverDisplayedItemizedProof22C14Q {
  const count = Math.max(0, countSemanticsNumber22C14Q(source.over_displayed_count) ?? 0);
  return overDisplayedItemizedProof22C14Q({
    overDisplayedCount: count,
    overDisplayedExtraIdsExact: source.over_displayed_extra_ids_exact,
    overDisplayedExtraItemsExact: source.over_displayed_extra_items_exact,
    overDisplayedValidationStatus: source.over_displayed_validation_status,
    overDisplayedSameProfileValidated: source.over_displayed_same_profile_validated,
    overDisplayedItemizedReasonSummary: source.over_displayed_itemized_reason_summary
  });
}

function countSemanticsDiagnostics22C14Q(input: CountSemanticsDiagnosticsInput22C14Q): Record<string, unknown> {
  const secondaryRecoveredCount = input.secondaryRecoveredCount ?? 0;
  const overDisplayedCount = input.displayedProfileCount == null ? 0 : Math.max(input.persistedCount - input.displayedProfileCount, 0);
  const overDisplayedExtraCount = input.overDisplayedExtraCount ?? overDisplayedCount;
  const overDisplayedSameProfileValidated = input.overDisplayedSameProfileValidated === "yes" || input.overDisplayedSameProfileValidated === true;
  const repositoryExistingOtherProfileTotal = input.repositoryExistingOtherProfileTotal ?? 0;
  const templateCacheMatch = input.templateCacheProfileMatch === "yes" || input.templateCacheProfileMatch === true;
  const directApiTemplateMatch = input.directApiTemplateProfileMatch === "yes" || input.directApiTemplateProfileMatch === true;
  const explicitOverDisplayedValidationStatus = typeof input.overDisplayedValidationStatus === "string" && input.overDisplayedValidationStatus.trim()
    ? input.overDisplayedValidationStatus.trim()
    : null;
  const extraIdsSameProfileMatchCount = Math.max(0, input.extraIdsSameProfileMatchCount ?? 0);
  const extraIdsProfileMismatchCount = Math.max(0, input.extraIdsProfileMismatchCount ?? 0);
  const itemizedProof = overDisplayedItemizedProof22C14Q({
    overDisplayedCount,
    overDisplayedExtraIdsExact: input.overDisplayedExtraIdsExact,
    overDisplayedExtraItemsExact: input.overDisplayedExtraItemsExact,
    overDisplayedValidationStatus: explicitOverDisplayedValidationStatus,
    overDisplayedSameProfileValidated: input.overDisplayedSameProfileValidated,
    overDisplayedItemizedReasonSummary: input.overDisplayedItemizedReasonSummary
  });
  const outsideProfileOffendingAwemeIds = overDisplayedOutsideProfileOffenderIds22C14Q(overDisplayedCount, input.overDisplayedExtraIdsExact, input.overDisplayedExtraItemsExact);
  const outsideProfileHasExactItemizedProof = outsideProfileOffendingAwemeIds.length > 0 && (explicitOverDisplayedValidationStatus === "outside_profile_detected" || explicitOverDisplayedValidationStatus === "failed_outside_profile" || explicitOverDisplayedValidationStatus === "failed_overcollection_outside_profile" || extraIdsProfileMismatchCount > 0);
  const overDisplayedValidationPassed = overDisplayedCount > 0 && itemizedProof.valid;
  const overDisplayedProofMissing = overDisplayedCount > 0 && !itemizedProof.valid;
  const unavailableOrUnlistedCount = input.displayedProfileCount == null ? null : Math.max(input.displayedProfileCount - input.persistedCount, 0);
  const internalLossReason = input.parserExtractionDropCount > 0
    ? "parser_extracted_fewer_than_raw"
    : input.validationOrProfileDropCount > 0
      ? "validation_or_profile_filter_removed_targets"
      : input.collectableCount > input.persistedCount || input.repositoryDropCount > 0
        ? "repository_write_or_dedupe_loss"
        : input.apiDuplicateAwemeIdsTotal > 0
          ? "duplicate_aweme_ids_removed"
          : null;
  const overDisplayedOutsideProfile = overDisplayedCount > 0 && outsideProfileHasExactItemizedProof;
  const overDisplayedNeedsValidationProofMissing = overDisplayedProofMissing && !overDisplayedOutsideProfile;
  const readyOverdisplayWithoutItemizedProof = overDisplayedNeedsValidationProofMissing;
  const status: CountSemanticsStatus22C14Q = input.displayedProfileCount != null && input.persistedCount > input.displayedProfileCount
    ? overDisplayedOutsideProfile
      ? "failed_overcollection_outside_profile"
      : overDisplayedValidationPassed
        ? "completed_with_api_over_displayed_count"
        : "overcollected_needs_validation"
    : input.displayedProfileCount != null && input.persistedCount === input.displayedProfileCount
      ? secondaryRecoveredCount > 0
        ? "completed_after_secondary_recovery"
        : "full_match"
      : input.apiHasMoreFinal !== false
        ? "incomplete_api_not_exhausted"
        : internalLossReason != null || input.apiRawCount > input.collectableCount || input.collectableCount > input.persistedCount
          ? "incomplete_internal_loss"
          : secondaryRecoveredCount > 0
            ? "completed_with_partial_secondary_recovery"
            : "completed_with_displayed_count_mismatch";
  const reason = overDisplayedNeedsValidationProofMissing
    ? "over_displayed_itemized_validation_missing"
    : overDisplayedValidationPassed && typeof input.overDisplayedReason === "string" && input.overDisplayedReason.trim()
      ? input.overDisplayedReason.trim()
      : status === "full_match"
      ? "displayed_count_matches_persisted_count"
      : status === "completed_with_api_over_displayed_count"
        ? "api_returned_additional_same_profile_items_beyond_displayed_count"
        : status === "failed_overcollection_outside_profile"
          ? "over_displayed_extra_item_profile_identifier_mismatch"
          : status === "overcollected_needs_validation"
            ? "api_count_exceeds_displayed_count_without_strong_same_profile_proof"
          : status === "completed_after_secondary_recovery"
            ? "secondary_recovery_reached_displayed_count"
            : status === "completed_with_displayed_count_mismatch"
              ? "displayed_count_not_fully_collectable"
              : status === "completed_with_partial_secondary_recovery"
                ? "displayed_count_partially_recovered_but_not_fully_collectable"
                : status === "incomplete_api_not_exhausted"
                  ? "api_not_exhausted_or_request_chain_failed"
                  : internalLossReason ?? "internal_count_loss";
  const overDisplayedValidationStatus = overDisplayedCount <= 0
    ? "not_applicable"
    : overDisplayedOutsideProfile
      ? "outside_profile_detected"
      : overDisplayedValidationPassed
        ? "validated_same_profile"
        : "needs_validation";
  const overDisplayedValidationFailureReason = overDisplayedCount <= 0
    ? null
    : overDisplayedOutsideProfile
      ? input.overDisplayedValidationFailureReason ?? "over_displayed_extra_item_profile_identifier_mismatch"
      : overDisplayedValidationPassed
        ? null
        : input.overDisplayedValidationFailureReason ?? (itemizedProof.missing.length > 0 ? itemizedProof.missing.join(",") : "profile_identity_not_proven");
  const persistedTotalBeforeContinuation = input.persistedTotalBeforeContinuation ?? input.repositoryExistingBeforeTotal ?? null;
  const persistedTotalAfterContinuation = input.persistedTotalAfterContinuation ?? input.persistedCount;
  const finalCumulativeCollectableCount = input.finalCumulativeCollectableCount ?? input.persistedCount;
  const finalDisplayAuthority = typeof input.finalDisplayAuthority === "string" && input.finalDisplayAuthority.trim()
    ? input.finalDisplayAuthority.trim()
    : "collectable_count";
  const finalHeaderCount = input.finalHeaderCount ?? finalCumulativeCollectableCount;
  const finalCounterCount = input.finalCounterCount ?? input.persistedCount;
  const headerCounterAuthorityMatch = input.headerCounterAuthorityMatch === "yes" || input.headerCounterAuthorityMatch === true
    ? "yes"
    : input.headerCounterAuthorityMatch === "no" || input.headerCounterAuthorityMatch === false
      ? "no"
      : finalHeaderCount === finalCounterCount
        ? "yes"
        : "no";
  return {
    displayed_profile_count: input.displayedProfileCount,
    displayed_profile_count_source: input.displayedProfileCountSource ?? null,
    displayed_profile_count_raw_text: input.displayedProfileCountRawText ?? null,
    api_raw_count: input.apiRawCount,
    api_unique_count: input.apiUniqueCount,
    api_has_more_final: input.apiHasMoreFinal,
    collectable_count: input.collectableCount,
    persisted_count: input.persistedCount,
    secondary_recovery_attempted: input.secondaryRecoveryAttempted ?? "not_yet_attempted",
    secondary_recovered_count: secondaryRecoveredCount,
    unavailable_or_unlisted_count: unavailableOrUnlistedCount,
    over_displayed_count: overDisplayedCount,
    over_displayed_reason: overDisplayedCount > 0 ? reason : null,
    over_displayed_validation_status: overDisplayedValidationStatus,
    over_displayed_same_profile_validated: overDisplayedValidationPassed ? "yes" : overDisplayedCount > 0 ? "no" : "not_applicable",
    over_displayed_validation_failure_reason: overDisplayedValidationFailureReason,
    ready_overdisplay_without_itemized_proof: readyOverdisplayWithoutItemizedProof ? "yes" : "no",
    ready_overdisplay_without_itemized_proof_reasons: readyOverdisplayWithoutItemizedProof ? itemizedProof.missing : [],
    over_displayed_extra_ids_sample: input.overDisplayedExtraIdsSample ?? null,
    over_displayed_extra_ids_exact: input.overDisplayedExtraIdsExact ?? null,
    over_displayed_extra_items_exact: input.overDisplayedExtraItemsExact ?? null,
    over_displayed_itemized_reason_summary: input.overDisplayedItemizedReasonSummary ?? null,
    over_displayed_extra_source: input.overDisplayedExtraSource ?? null,
    over_displayed_extra_count: overDisplayedCount > 0 ? overDisplayedExtraCount : 0,
    extra_ids_same_profile_match_count: overDisplayedCount > 0 ? extraIdsSameProfileMatchCount : 0,
    extra_ids_profile_mismatch_count: overDisplayedCount > 0 ? extraIdsProfileMismatchCount : 0,
    over_displayed_came_from_continuation_tail: input.overDisplayedCameFromContinuationTail ?? (overDisplayedCount > 0 ? "unknown" : "not_applicable"),
    requested_profile_identifier: input.requestedProfileIdentifier ?? null,
    api_response_profile_identifier: input.apiResponseProfileIdentifier ?? null,
    repository_profile_identifier: input.repositoryProfileIdentifier ?? null,
    repository_existing_before_total: input.repositoryExistingBeforeTotal ?? null,
    repository_existing_same_profile_total: input.repositoryExistingSameProfileTotal ?? null,
    repository_existing_other_profile_total: repositoryExistingOtherProfileTotal,
    template_cache_profile_match: input.templateCacheProfileMatch ?? "unknown",
    direct_api_template_profile_match: input.directApiTemplateProfileMatch ?? "unknown",
    continuation_batch_new_count: input.continuationBatchNewCount ?? null,
    continuation_batch_raw_count: input.continuationBatchRawCount ?? null,
    continuation_batch_accepted_count: input.continuationBatchAcceptedCount ?? null,
    persisted_total_before_continuation: persistedTotalBeforeContinuation,
    persisted_total_after_continuation: persistedTotalAfterContinuation,
    final_cumulative_collectable_count: finalCumulativeCollectableCount,
    final_display_authority: finalDisplayAuthority,
    final_header_count: finalHeaderCount,
    final_counter_count: finalCounterCount,
    header_counter_authority_match: headerCounterAuthorityMatch,
    count_semantics_status: status,
    count_semantics_reason: reason,
    over_displayed_outside_profile_offending_aweme_ids: outsideProfileOffendingAwemeIds,
    known_contradictions_to_debug: [
      ...(overDisplayedNeedsValidationProofMissing ? ["over_displayed_ready_invariant_blocked", ...itemizedProof.missing] : []),
      ...((explicitOverDisplayedValidationStatus === "outside_profile_detected" || explicitOverDisplayedValidationStatus === "failed_outside_profile" || explicitOverDisplayedValidationStatus === "failed_overcollection_outside_profile" || extraIdsProfileMismatchCount > 0) && !outsideProfileHasExactItemizedProof ? ["outside_profile_verdict_without_itemized_offenders"] : [])
    ],
    ...scanHealthVerdictDiagnostics22C14R({
      count_semantics_status: status,
      count_semantics_reason: reason,
      over_displayed_count: overDisplayedCount,
      over_displayed_validation_status: overDisplayedValidationStatus,
      over_displayed_same_profile_validated: overDisplayedValidationPassed ? "yes" : overDisplayedCount > 0 ? "no" : "not_applicable",
      over_displayed_extra_ids_exact: input.overDisplayedExtraIdsExact ?? null,
      over_displayed_extra_items_exact: input.overDisplayedExtraItemsExact ?? null,
      over_displayed_itemized_reason_summary: input.overDisplayedItemizedReasonSummary ?? null,
      over_displayed_validation_failure_reason: overDisplayedValidationFailureReason,
      over_displayed_outside_profile_offending_aweme_ids: outsideProfileOffendingAwemeIds,
      ready_overdisplay_without_itemized_proof: readyOverdisplayWithoutItemizedProof ? "yes" : "no",
      ready_overdisplay_without_itemized_proof_reasons: readyOverdisplayWithoutItemizedProof ? itemizedProof.missing : []
    })
  };
}

type RepositoryOverDisplayedDiagnosticsOptions22C14Q = {
  displayedProfileCount: number | null;
  persistedCount: number;
  requestedProfileIdentifier: string | null;
  apiResponseProfileIdentifier: string | null;
  existingDiagnostics: Record<string, unknown>;
  source: string;
};

function repositoryRecordProfileIdentifier22C14Q(record: ProfileTargetRecord): string | null {
  const detail = record.target_detail as Record<string, unknown>;
  const queueItem = record.queue_item as Record<string, unknown>;
  const direct = typeof detail.profile_identifier === "string" && detail.profile_identifier.trim()
    ? detail.profile_identifier.trim()
    : typeof queueItem.profile_identifier === "string" && queueItem.profile_identifier.trim()
      ? queueItem.profile_identifier.trim()
      : null;
  if (direct) return direct;
  const profileUrl = typeof detail.profile_url === "string" && detail.profile_url.trim()
    ? detail.profile_url.trim()
    : typeof queueItem.profile_url === "string" && queueItem.profile_url.trim()
      ? queueItem.profile_url.trim()
      : null;
  return profileUrl ? profileIdentifierFromUrl(profileUrl) : null;
}

function repositoryRecordSourceUrl22C14Q(record: ProfileTargetRecord): string | null {
  const detail = record.target_detail as Record<string, unknown>;
  const queueItem = record.queue_item as Record<string, unknown>;
  const value = record.source_url ?? detail.source_url ?? detail.profile_url ?? queueItem.source_url ?? queueItem.profile_url ?? null;
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function deriveRepositoryOverDisplayedDiagnostics22C14Q(records: ProfileTargetRecord[], options: RepositoryOverDisplayedDiagnosticsOptions22C14Q): Record<string, unknown> {
  const overDisplayedCount = options.displayedProfileCount == null ? 0 : Math.max(options.persistedCount - options.displayedProfileCount, 0);
  if (overDisplayedCount <= 0) return {};
  const exactRecords = records.slice(0, overDisplayedCount);
  const exactIds = exactRecords.map((record) => record.aweme_id);
  const requestedProfileIdentifier = options.requestedProfileIdentifier?.trim() || null;
  const apiResponseProfileIdentifier = options.apiResponseProfileIdentifier?.trim() || requestedProfileIdentifier;
  const items = exactRecords.map((record) => {
    const recordProfileIdentifier = repositoryRecordProfileIdentifier22C14Q(record);
    const sameProfileValidated = recordProfileIdentifier != null && requestedProfileIdentifier != null && recordProfileIdentifier === requestedProfileIdentifier ? "yes" : "no";
    const sameProfileValidationReason = sameProfileValidated === "yes"
      ? "repository_record_profile_identifier_matches_requested_profile"
      : "profile_identity_not_proven";
    const itemReason: OverDisplayedItemReason22C14Q = sameProfileValidated === "yes"
      ? "valid_same_profile_api_item_beyond_visible_count_basis"
      : "profile_identity_not_proven";
    return {
      aweme_id: record.aweme_id,
      index_in_final_order: record.sequence,
      page_index_found: null,
      request_index_found: null,
      source_url: repositoryRecordSourceUrl22C14Q(record),
      same_profile_validated: sameProfileValidated,
      same_profile_validation_reason: sameProfileValidationReason,
      source_profile_identifier: recordProfileIdentifier,
      target_profile_identifier: requestedProfileIdentifier,
      item_reason: itemReason
    };
  });
  const sameProfileMatchCount = items.filter((item) => item.same_profile_validated === "yes").length;
  const profileMismatchCount = items.filter((item) => item.source_profile_identifier != null && requestedProfileIdentifier != null && item.source_profile_identifier !== requestedProfileIdentifier).length;
  const allExactItemsIdentified = exactIds.length === overDisplayedCount;
  const allSameProfileValidated = allExactItemsIdentified && sameProfileMatchCount === overDisplayedCount && profileMismatchCount === 0;
  const itemizedReasonSummary = items.length > 0
    ? items.map((item) => `${item.aweme_id}:${item.item_reason}`).join(" | ")
    : null;
  const forensicContradictions = Array.isArray(options.existingDiagnostics.over_displayed_forensic_contradictions)
    ? [...options.existingDiagnostics.over_displayed_forensic_contradictions]
    : [];
  if (!allExactItemsIdentified) forensicContradictions.push("over_displayed_count_positive_but_extra_ids_missing");
  const derivedOverdisplay = {
    overDisplayedSameProfileValidated: allSameProfileValidated ? "yes" : "no",
    overDisplayedExtraIdsSample: exactIds,
    overDisplayedExtraIdsExact: exactIds,
    overDisplayedExtraItemsExact: items,
    overDisplayedItemizedReasonSummary: itemizedReasonSummary,
    overDisplayedExtraSource: options.source,
    overDisplayedExtraCount: overDisplayedCount,
    extraIdsSameProfileMatchCount: sameProfileMatchCount,
    extraIdsProfileMismatchCount: profileMismatchCount,
    overDisplayedValidationStatus: profileMismatchCount > 0 ? "failed_outside_profile" : allSameProfileValidated ? "validated_same_profile" : "needs_validation",
    overDisplayedValidationFailureReason: profileMismatchCount > 0 ? "over_displayed_extra_item_profile_identifier_mismatch" : undefined,
    overDisplayedReason: profileMismatchCount > 0 ? "over_displayed_extra_item_profile_identifier_mismatch" : allSameProfileValidated ? "itemized_valid_same_profile_api_items_beyond_visible_count" : allExactItemsIdentified ? "exact_over_displayed_items_identified_but_same_profile_proof_missing" : "over_displayed_count_positive_but_extra_ids_missing",
    requestedProfileIdentifier,
    apiResponseProfileIdentifier,
    repositoryProfileIdentifier: requestedProfileIdentifier,
    repositoryExistingOtherProfileTotal: 0,
    templateCacheProfileMatch: allSameProfileValidated ? "yes" : options.existingDiagnostics.template_cache_profile_match,
    directApiTemplateProfileMatch: allSameProfileValidated ? "yes" : options.existingDiagnostics.direct_api_template_profile_match
  } satisfies Partial<CountSemanticsDiagnosticsInput22C14Q>;
  const countSemantics = countSemanticsDiagnostics22C14Q({
    displayedProfileCount: options.displayedProfileCount,
    displayedProfileCountSource: options.existingDiagnostics.displayed_profile_count_source,
    displayedProfileCountRawText: options.existingDiagnostics.displayed_profile_count_raw_text,
    apiRawCount: countSemanticsNumber22C14Q(options.existingDiagnostics.api_raw_count ?? options.existingDiagnostics.api_pagination_raw_items_total) ?? options.persistedCount,
    apiUniqueCount: countSemanticsNumber22C14Q(options.existingDiagnostics.api_unique_count ?? options.existingDiagnostics.api_unique_aweme_ids_total) ?? options.persistedCount,
    apiHasMoreFinal: options.existingDiagnostics.api_has_more_final === false || options.existingDiagnostics.api_pagination_final_has_more === false ? false : options.existingDiagnostics.api_has_more_final === true || options.existingDiagnostics.api_pagination_final_has_more === true ? true : null,
    collectableCount: countSemanticsNumber22C14Q(options.existingDiagnostics.collectable_count) ?? options.persistedCount,
    persistedCount: options.persistedCount,
    secondaryRecoveryAttempted: options.existingDiagnostics.secondary_recovery_attempted,
    secondaryRecoveredCount: countSemanticsNumber22C14Q(options.existingDiagnostics.secondary_recovered_count) ?? 0,
    parserExtractionDropCount: countSemanticsNumber22C14Q(options.existingDiagnostics.parser_extraction_drop_count) ?? 0,
    validationOrProfileDropCount: countSemanticsNumber22C14Q(options.existingDiagnostics.validation_or_profile_drop_count) ?? 0,
    repositoryDropCount: countSemanticsNumber22C14Q(options.existingDiagnostics.repository_drop_count) ?? 0,
    apiDuplicateAwemeIdsTotal: countSemanticsNumber22C14Q(options.existingDiagnostics.api_duplicate_aweme_ids_total) ?? 0,
    ...derivedOverdisplay
  });
  return {
    ...countSemantics,
    over_displayed_extra_ids_exact: exactIds,
    over_displayed_extra_items_exact: items,
    over_displayed_itemized_reason_summary: itemizedReasonSummary,
    over_displayed_extra_source: options.source,
    over_displayed_ordered_final_targets_available: records.length > 0 ? "yes" : "no",
    over_displayed_expected_extra_count: overDisplayedCount,
    over_displayed_exact_extra_count: exactIds.length,
    over_displayed_forensic_contradictions: forensicContradictions
  };
}

function buildOvercollectionForensicExport22C14Q(args: {
  scanRunId: string;
  requestedProfileIdentifier: string | null;
  displayedProfileCount: number | null;
  apiUniqueCount: number;
  persistedCount: number;
  acceptedTargetsTotal: number;
  acceptedTargetLedger: AcceptedTargetLedgerEntry22C14Q[];
  generatedAt?: string;
}): OvercollectionForensicExport22C14Q {
  const overDisplayedCount = args.displayedProfileCount == null ? 0 : Math.max(args.persistedCount - args.displayedProfileCount, 0);
  const ledgerPresent = args.acceptedTargetLedger.length > 0;
  const ledgerMatchesAcceptedTotal = args.acceptedTargetLedger.length === args.acceptedTargetsTotal;
  const visibleBoundaryIndex = args.displayedProfileCount;
  const boundaryStartIndex = args.displayedProfileCount == null ? null : Math.max(0, args.displayedProfileCount - 5);
  const boundaryEndIndex = args.displayedProfileCount == null ? null : Math.min(args.acceptedTargetLedger.length, args.persistedCount + 5);
  const boundaryWindow = boundaryStartIndex == null || boundaryEndIndex == null ? [] : args.acceptedTargetLedger.slice(boundaryStartIndex, boundaryEndIndex);
  const extractionCountMismatch = overDisplayedCount > 0 && args.displayedProfileCount != null && args.acceptedTargetLedger.slice(args.displayedProfileCount, args.persistedCount).length !== overDisplayedCount;
  const ledgerIncomplete = overDisplayedCount > 0 && (!ledgerPresent || args.acceptedTargetLedger.length < args.persistedCount || !ledgerMatchesAcceptedTotal || extractionCountMismatch);
  const extraItems = overDisplayedCount > 0 && args.displayedProfileCount != null && !ledgerIncomplete
    ? args.acceptedTargetLedger.slice(args.displayedProfileCount, args.persistedCount)
    : [];
  const sameProfileCount = extraItems.filter((item) => item.same_profile_validation_status === "same_profile").length;
  const outsideProfileCount = extraItems.filter((item) => item.same_profile_validation_status === "outside_profile").length;
  const insufficientEvidenceCount = extraItems.filter((item) => item.same_profile_validation_status === "insufficient_evidence").length;
  const finalVerdict: OvercollectionForensicExportVerdict22C14Q = overDisplayedCount <= 0
    ? "validated_same_profile"
    : !ledgerPresent
      ? "ledger_missing"
      : ledgerIncomplete
        ? "ledger_incomplete"
        : outsideProfileCount > 0
          ? "outside_profile_detected"
          : insufficientEvidenceCount > 0
            ? "needs_validation"
            : extraItems.length === overDisplayedCount && sameProfileCount === overDisplayedCount
              ? "validated_same_profile"
              : "needs_validation";
  const finalVerdictReason = finalVerdict === "ledger_missing"
    ? "accepted_target_ledger_missing"
    : finalVerdict === "ledger_incomplete"
      ? extractionCountMismatch ? "extra_item_extraction_count_mismatch" : "accepted_target_ledger_incomplete_or_count_mismatch"
      : finalVerdict === "outside_profile_detected"
        ? `outside_profile_extra_items:${extraItems.filter((item) => item.same_profile_validation_status === "outside_profile").map((item) => item.aweme_id).join(",")}`
        : finalVerdict === "needs_validation"
          ? `insufficient_evidence_extra_items:${extraItems.filter((item) => item.same_profile_validation_status === "insufficient_evidence").map((item) => item.aweme_id).join(",") || "missing_itemized_validation"}`
          : overDisplayedCount > 0 ? "all_extra_items_validated_same_profile" : "no_over_displayed_items";
  return {
    purpose: "scan_profile_overcollection_forensic_export",
    build_id: "22C-14Q-overcollection-forensic-export",
    generated_at: args.generatedAt ?? new Date().toISOString(),
    scan_run_id: args.scanRunId,
    requested_profile_identifier: args.requestedProfileIdentifier,
    profile_identifier: args.requestedProfileIdentifier,
    displayed_profile_count: args.displayedProfileCount,
    api_unique_count: args.apiUniqueCount,
    persisted_count: args.persistedCount,
    over_displayed_count: overDisplayedCount,
    ledger_present: ledgerPresent,
    ledger_count: args.acceptedTargetLedger.length,
    ledger_matches_accepted_total: ledgerMatchesAcceptedTotal,
    boundary_start_index: boundaryStartIndex,
    visible_boundary_index: visibleBoundaryIndex,
    boundary_end_index: boundaryEndIndex,
    boundary_window: boundaryWindow,
    extra_items: extraItems,
    extra_ids: extraItems.map((item) => item.aweme_id),
    same_profile_validation_summary: {
      same_profile_count: sameProfileCount,
      outside_profile_count: outsideProfileCount,
      insufficient_evidence_count: insufficientEvidenceCount
    },
    final_verdict: finalVerdict,
    final_verdict_reason: finalVerdictReason,
    exported_item_count: boundaryWindow.length,
    extra_item_count: extraItems.length
  };
}

function paginatedScanAccountingDiagnostics22C14B(accounting: PaginatedScanAccounting22C14B, expectedCount: number | null, totalPersisted: number): Record<string, unknown> {
  const gapCount = expectedCount == null ? 0 : Math.max(expectedCount - totalPersisted, 0);
  const pageCount = accounting.perPageReturnedTargetCounts.length;
  const requestCount = pageCount;
  const apiUniqueAwemeIdsTotal = accounting.uniqueAwemeIds.size;
  const apiDuplicateAwemeIdsTotal = Math.max(accounting.rawAwemeIdsTotal - apiUniqueAwemeIdsTotal, 0);
  const parserExtractionDropCount = Math.max(accounting.rawAwemeIdsTotal - accounting.targetsReturnedToBackgroundTotal, 0) + accounting.emptyOrMissingAwemeIdCount;
  const validationOrProfileDropCount = accounting.backgroundInvalidDropTotal + accounting.otherProfileDropCount + accounting.favoriteEndpointDropCount;
  const repositoryDropCount = accounting.repositoryDuplicateExistingTotal;
  const sameProfileValidated = validationOrProfileDropCount === 0 && accounting.targetsReturnedToBackgroundTotal === accounting.backgroundTargetsAfterValidationTotal;
  const overDisplayedCount = expectedCount == null ? 0 : Math.max(totalPersisted - expectedCount, 0);
  const orderedAcceptedTargets = accounting.orderedAcceptedTargets ?? [];
  const acceptedTargetLedger = accounting.acceptedTargetLedger ?? [];
  const acceptedTargetLedgerPresent = Array.isArray(accounting.acceptedTargetLedger) && acceptedTargetLedger.length > 0;
  const acceptedTargetLedgerMatchesAcceptedTotal = acceptedTargetLedger.length === accounting.targetsReturnedToBackgroundTotal;
  const ledgerBoundaryStartIndex = expectedCount == null ? null : Math.max(expectedCount - 5, 0);
  const ledgerBoundaryEndIndex = expectedCount == null ? null : Math.min(acceptedTargetLedger.length, expectedCount + overDisplayedCount + 5);
  const acceptedTargetLedgerBoundaryWindow = ledgerBoundaryStartIndex == null || ledgerBoundaryEndIndex == null ? [] : acceptedTargetLedger.slice(ledgerBoundaryStartIndex, ledgerBoundaryEndIndex);
  const ledgerExtractionError = overDisplayedCount <= 0
    ? null
    : expectedCount == null
      ? "displayed_profile_count_missing"
      : !acceptedTargetLedgerPresent || acceptedTargetLedger.length < totalPersisted || !acceptedTargetLedgerMatchesAcceptedTotal
        ? "accepted target forensic ledger missing or incomplete"
        : null;
  const ledgerExtraTargets = overDisplayedCount <= 0 || expectedCount == null || ledgerExtractionError != null
    ? []
    : acceptedTargetLedger.slice(expectedCount, expectedCount + overDisplayedCount);
  const orderedExtraTargets = overDisplayedCount <= 0 || expectedCount == null ? [] : orderedAcceptedTargets.slice(expectedCount, expectedCount + overDisplayedCount);
  const overDisplayedExtraIds = ledgerExtraTargets.map((target) => target.aweme_id);
  const normalizedRequestedProfileIdentifier = accounting.requestedProfileIdentifier?.trim() || null;
  const normalizedApiResponseProfileIdentifier = accounting.apiResponseProfileIdentifier?.trim() || null;
  const extraIdsSameProfileMatchCount = ledgerExtraTargets.reduce((total, evidence) => evidence.same_profile_validation_status === "same_profile" ? total + 1 : total, 0);
  const extraIdsProfileMismatchCount = ledgerExtraTargets.reduce((total, evidence) => evidence.same_profile_validation_status === "outside_profile" ? total + 1 : total, 0);
  const overDisplayedExtraItemsExact = ledgerExtraTargets.map((evidence) => ({
    ...evidence,
    page_index_found: evidence.page_index,
    raw_index: evidence.raw_index_in_page,
    raw_index_found: evidence.raw_index_in_page,
    source_endpoint: evidence.endpoint_path ?? null,
    source_cursor: evidence.request_cursor ?? null,
    same_profile_validated: evidence.same_profile_validation_status === "same_profile" ? "yes" : "no",
    source_profile_identifier: evidence.api_template_profile_identifier ?? normalizedApiResponseProfileIdentifier,
    target_profile_identifier: normalizedRequestedProfileIdentifier,
    requested_profile_identifier: normalizedRequestedProfileIdentifier,
    requested_profile_sec_uid: evidence.request_sec_uid ?? normalizedRequestedProfileIdentifier,
    author_user_id: evidence.author_uid ?? null,
    author_id: evidence.author_uid ?? null,
    item_reason: evidence.same_profile_validation_status === "same_profile" ? "valid_same_profile_item_hidden_from_visible_count_basis" : evidence.same_profile_validation_status === "outside_profile" ? "possible_cross_profile_contamination" : "profile_identity_not_proven"
  }));
  const exactOrderedExtraTargetProof = overDisplayedCount > 0 && ledgerExtraTargets.length === overDisplayedCount && ledgerExtractionError == null;
  const allExtraItemsItemizedValidated = overDisplayedExtraItemsExact.length === overDisplayedCount && overDisplayedCount > 0
    && overDisplayedExtraItemsExact.every((item) => item.same_profile_validation_status === "same_profile");
  const overDisplayedItemizedReasonSummary = ledgerExtractionError != null
    ? "accepted target forensic ledger missing or incomplete"
    : exactOrderedExtraTargetProof
      ? "Derived from acceptedTargetLedger.slice(displayed_profile_count, persisted_count)"
      : null;
  const forensicExport = buildOvercollectionForensicExport22C14Q({
    scanRunId: "unknown",
    requestedProfileIdentifier: normalizedRequestedProfileIdentifier,
    displayedProfileCount: expectedCount,
    apiUniqueCount: apiUniqueAwemeIdsTotal,
    persistedCount: totalPersisted,
    acceptedTargetsTotal: accounting.targetsReturnedToBackgroundTotal,
    acceptedTargetLedger
  });
  const overDisplayedValidationStatus = overDisplayedCount <= 0
    ? "not_applicable"
    : forensicExport.final_verdict === "outside_profile_detected"
      ? "outside_profile_detected"
      : forensicExport.final_verdict === "validated_same_profile"
        ? "validated_same_profile"
        : "needs_validation";
  const countSemantics = countSemanticsDiagnostics22C14Q({ displayedProfileCount: expectedCount, apiRawCount: accounting.rawItemsTotal, apiUniqueCount: apiUniqueAwemeIdsTotal, apiHasMoreFinal: accounting.finalHasMore, collectableCount: accounting.backgroundTargetsAfterValidationTotal, persistedCount: totalPersisted, secondaryRecoveryAttempted: "not_yet_attempted", secondaryRecoveredCount: 0, parserExtractionDropCount, validationOrProfileDropCount, repositoryDropCount, apiDuplicateAwemeIdsTotal, overDisplayedSameProfileValidated: allExtraItemsItemizedValidated ? "yes" : "no", overDisplayedExtraIdsSample: overDisplayedExtraIds.length > 0 ? overDisplayedExtraIds.slice(0, 10) : null, overDisplayedExtraIdsExact: overDisplayedExtraIds.length > 0 ? overDisplayedExtraIds : null, overDisplayedExtraItemsExact: overDisplayedExtraItemsExact.length > 0 ? overDisplayedExtraItemsExact : null, overDisplayedItemizedReasonSummary, overDisplayedExtraSource: exactOrderedExtraTargetProof ? "accepted_target_ledger_boundary_tail" : null, overDisplayedExtraCount: overDisplayedCount, extraIdsSameProfileMatchCount, extraIdsProfileMismatchCount, overDisplayedValidationStatus, overDisplayedValidationFailureReason: ledgerExtractionError ?? undefined, overDisplayedReason: overDisplayedCount > 0 && allExtraItemsItemizedValidated ? "itemized_valid_same_profile_api_items_beyond_visible_count" : null, apiResponseProfileIdentifier: normalizedApiResponseProfileIdentifier, requestedProfileIdentifier: normalizedRequestedProfileIdentifier, repositoryExistingBeforeTotal: accounting.repositoryExistingBeforeTotal, repositoryExistingSameProfileTotal: accounting.repositoryExistingBeforeTotal, repositoryExistingOtherProfileTotal: 0, templateCacheProfileMatch: allExtraItemsItemizedValidated ? "yes" : sameProfileValidated ? "yes" : "no", directApiTemplateProfileMatch: normalizedApiResponseProfileIdentifier != null && normalizedRequestedProfileIdentifier != null && normalizedApiResponseProfileIdentifier === normalizedRequestedProfileIdentifier ? "yes" : allExtraItemsItemizedValidated ? "yes" : sameProfileValidated ? "yes" : "no" });
  if (overDisplayedCount > 0 && ledgerExtractionError != null) {
    countSemantics.count_semantics_status = "overcollected_forensic_ledger_missing";
    countSemantics.count_semantics_reason = "accepted_target_forensic_ledger_missing_or_incomplete";
    countSemantics.over_displayed_validation_status = "needs_validation";
    countSemantics.over_displayed_itemized_reason_summary = "accepted target forensic ledger missing or incomplete";
    countSemantics.over_displayed_extra_source = null;
    countSemantics.over_displayed_extra_ids_exact = null;
    countSemantics.over_displayed_extra_items_exact = null;
    countSemantics.scan_health_verdict = "failed_or_warning_overcollection_validation_needed";
    countSemantics.scan_health_verdict_reason = "accepted target forensic ledger missing or incomplete";
    countSemantics.known_contradictions_to_debug = Array.from(new Set([...(Array.isArray(countSemantics.known_contradictions_to_debug) ? countSemantics.known_contradictions_to_debug.map(String) : []), "overcollection_without_accepted_target_ledger"]));
  }
  const rawAccountingUnavailableReason = accounting.rawItemsTotal <= 0 && accounting.targetsReturnedToBackgroundTotal > 0
    ? "content_script_raw_item_count_unavailable_but_verified_targets_returned"
    : null;
  const gapReason = gapCount <= 0
    ? "none"
    : accounting.finalHasMore === true && pageCount >= CANONICAL_SCAN_PAGE_BUDGET_22C14B && parserExtractionDropCount === 0 && validationOrProfileDropCount === 0 && repositoryDropCount === 0 && apiDuplicateAwemeIdsTotal === 0
      ? "api_budget_exhausted_before_has_more_false"
      : accounting.finalHasMore === false && accounting.rawItemsTotal < (expectedCount ?? 0) && parserExtractionDropCount === 0 && validationOrProfileDropCount === 0 && repositoryDropCount === 0 && apiDuplicateAwemeIdsTotal === 0
        ? "api_exhausted_below_expected"
        : parserExtractionDropCount > 0
          ? "parser_extracted_fewer_than_raw"
          : validationOrProfileDropCount > 0
            ? "validation_or_profile_filter_removed_targets"
            : repositoryDropCount > 0
              ? "repository_dedupe_or_write_loss"
              : apiDuplicateAwemeIdsTotal > 0 || accounting.backgroundDuplicateDropTotal > 0
                ? "duplicate_aweme_ids_removed"
                : accounting.finalHasMore === false && accounting.rawItemsTotal >= (expectedCount ?? 0) && totalPersisted < (expectedCount ?? 0)
                  ? "expected_count_semantics_mismatch"
                  : "unexplained_after_full_accounting";
  const gapClassification = gapCount <= 0
    ? "none"
    : gapReason === "api_exhausted_below_expected"
      ? "api_exhausted_below_expected"
      : gapReason === "api_budget_exhausted_before_has_more_false"
        ? "resumable_api_budget_exhausted"
        : gapReason === "repository_dedupe_or_write_loss"
          ? "repository_drop"
          : gapReason === "parser_extracted_fewer_than_raw"
            ? "parser_drop"
            : gapReason === "validation_or_profile_filter_removed_targets"
              ? "filtered_items"
              : gapReason === "duplicate_aweme_ids_removed"
                ? "duplicate_targets_removed"
                : "unexplained_non_blocking_warning";
  const gapEvidence = gapCount <= 0
    ? expectedCount != null && totalPersisted > expectedCount
      ? `over_displayed_count: expected=${expectedCount}; persisted=${totalPersisted}; over=${totalPersisted - expectedCount}; raw=${accounting.rawItemsTotal}; unique_aweme_ids=${apiUniqueAwemeIdsTotal}; background_after_validation=${accounting.backgroundTargetsAfterValidationTotal}; repository_existing_before=${accounting.repositoryExistingBeforeTotal}; repository_total_after=${totalPersisted}; has_more=${String(accounting.finalHasMore)}`
      : "none"
    : `${gapReason}: expected=${expectedCount}; persisted=${totalPersisted}; gap=${gapCount}; page_count=${pageCount}; request_count=${requestCount}; api_pages=${pageCount}; api_requests=${requestCount}; raw=${accounting.rawItemsTotal}; raw_aweme_ids=${accounting.rawAwemeIdsTotal}; unique_aweme_ids=${apiUniqueAwemeIdsTotal}; api_duplicates=${apiDuplicateAwemeIdsTotal}; returned_to_background=${accounting.targetsReturnedToBackgroundTotal}; background_after_validation=${accounting.backgroundTargetsAfterValidationTotal}; repository_input=${accounting.repositoryWriteInputCount}; repository_existing_before=${accounting.repositoryExistingBeforeTotal}; repository_new_inserted=${accounting.repositoryNewInsertedTotal}; repository_duplicate_existing=${accounting.repositoryDuplicateExistingTotal}; repository_total_after=${totalPersisted}; has_more=${String(accounting.finalHasMore)}; page_budget=${CANONICAL_SCAN_PAGE_BUDGET_22C14B}`;
  const overDisplayedMissingEvidence = overDisplayedCount > 0
    ? overDisplayedItemizedProofFromDiagnostics22C14Q(countSemantics).missing
    : [];
  return {
    ...countSemantics,
    overcollection_forensic_export: forensicExport,
    forensic_export_available: forensicExport.final_verdict !== "ledger_missing" ? "yes" : "no",
    forensic_export_storage_key: OVERCOLLECTION_FORENSIC_EXPORT_STORAGE_KEY_22C14Q,
    forensic_export_scan_run_id: forensicExport.scan_run_id,
    over_displayed_missing_evidence: overDisplayedMissingEvidence,
    over_displayed_ordered_accepted_targets_total: orderedAcceptedTargets.length,
    over_displayed_ordered_extra_targets_count: orderedExtraTargets.length,
    accepted_target_ledger_present: acceptedTargetLedgerPresent ? "yes" : "no",
    accepted_target_ledger_count: acceptedTargetLedger.length,
    accepted_target_ledger_matches_accepted_total: acceptedTargetLedgerMatchesAcceptedTotal ? "yes" : "no",
    accepted_target_ledger_first_5: acceptedTargetLedger.slice(0, 5),
    accepted_target_ledger_last_20: acceptedTargetLedger.slice(-20),
    accepted_target_ledger_boundary_window: acceptedTargetLedgerBoundaryWindow,
    over_displayed_boundary_start_index: ledgerBoundaryStartIndex,
    over_displayed_visible_boundary_index: expectedCount,
    over_displayed_boundary_end_index: expectedCount == null ? null : expectedCount + overDisplayedCount,
    over_displayed_extraction_error: ledgerExtractionError,
    api_pagination_attempted: "yes",
    api_pages_fetched_total: pageCount,
    api_requests_total: requestCount,
    api_raw_items_total: accounting.rawItemsTotal,
    api_raw_aweme_ids_total: accounting.rawAwemeIdsTotal,
    api_unique_aweme_ids_total: apiUniqueAwemeIdsTotal,
    api_duplicate_aweme_ids_total: apiDuplicateAwemeIdsTotal,
    api_targets_returned_to_background_total: accounting.targetsReturnedToBackgroundTotal,
    background_targets_received_total: accounting.backgroundTargetsReceivedTotal,
    background_targets_after_validation_total: accounting.backgroundTargetsAfterValidationTotal,
    background_duplicate_drop_total: accounting.backgroundDuplicateDropTotal,
    background_invalid_drop_total: accounting.backgroundInvalidDropTotal,
    background_other_profile_drop_total: accounting.otherProfileDropCount,
    repository_write_input_total: accounting.repositoryWriteInputCount,
    repository_existing_before_total: accounting.repositoryExistingBeforeTotal,
    repository_new_inserted_total: accounting.repositoryNewInsertedTotal,
    repository_duplicate_existing_total: accounting.repositoryDuplicateExistingTotal,
    repository_total_after: totalPersisted,
    expected_count: expectedCount,
    api_pagination_page_count: pageCount,
    api_pagination_request_count: requestCount,
    active_profile_post_fetch_page_count: pageCount,
    active_profile_post_fetch_request_count: requestCount,
    active_profile_post_fetch_target_count: accounting.targetsReturnedToBackgroundTotal,
    active_profile_post_fetch_raw_items_total: accounting.rawItemsTotal,
    active_profile_post_fetch_raw_aweme_ids_total: accounting.rawAwemeIdsTotal,
    raw_accounting_unavailable_reason: rawAccountingUnavailableReason,
    api_pagination_raw_items_total: accounting.rawItemsTotal,
    api_pagination_raw_aweme_ids_total: accounting.rawAwemeIdsTotal,
    api_pagination_unique_aweme_ids_total: apiUniqueAwemeIdsTotal,
    api_pagination_accepted_targets_total: accounting.targetsReturnedToBackgroundTotal,
    api_pagination_persisted_targets_total: totalPersisted,
    api_pagination_duplicate_drop_count: apiDuplicateAwemeIdsTotal + accounting.backgroundDuplicateDropTotal,
    api_pagination_invalid_drop_count: accounting.backgroundInvalidDropTotal,
    api_pagination_other_profile_drop_count: accounting.otherProfileDropCount,
    api_pagination_favorite_endpoint_drop_count: accounting.favoriteEndpointDropCount,
    api_pagination_empty_or_missing_aweme_id_count: accounting.emptyOrMissingAwemeIdCount,
    api_pagination_repository_write_input_count: accounting.repositoryWriteInputCount,
    api_pagination_repository_write_total_after: accounting.repositoryWriteTotalAfter,
    api_pagination_repository_new_inserted_total: accounting.repositoryNewInsertedTotal,
    api_pagination_repository_duplicate_existing_total: accounting.repositoryDuplicateExistingTotal,
    api_pagination_first_page_raw_count: accounting.firstPageRawCount,
    api_pagination_last_page_raw_count: accounting.lastPageRawCount,
    api_pagination_last_page_accepted_count: accounting.lastPageAcceptedCount,
    api_pagination_last_page_persisted_delta: accounting.lastPagePersistedDelta,
    api_pagination_per_page_raw_counts: accounting.perPageRawCounts,
    api_pagination_per_page_raw_aweme_id_counts: accounting.perPageRawAwemeIdCounts,
    api_pagination_per_page_returned_target_counts: accounting.perPageReturnedTargetCounts,
    api_pagination_per_page_accepted_counts: accounting.perPageReturnedTargetCounts,
    api_pagination_per_page_unique_new_counts: accounting.perPageUniqueNewCounts,
    api_pagination_per_page_duplicate_counts: accounting.perPageDuplicateCounts,
    api_pagination_per_page_cursor_values: accounting.perPageCursorValues,
    api_pagination_per_page_cursor_present_flags: accounting.perPageCursorPresentFlags,
    api_pagination_per_page_has_more_flags: accounting.perPageHasMoreFlags,
    api_pagination_per_page_status_codes: accounting.perPageStatusCodes,
    api_pagination_per_page_parser_routes: accounting.perPageParserRoutes,
    api_pagination_per_page_persisted_totals: accounting.perPagePersistedTotals,
    api_pagination_final_has_more: accounting.finalHasMore,
    api_pagination_final_cursor_present: accounting.finalCursorPresent,
    api_pagination_final_status_code: accounting.finalStatusCode,
    page_budget_limit: CANONICAL_SCAN_PAGE_BUDGET_22C14B,
    page_budget_exhausted: accounting.finalHasMore === true && pageCount >= CANONICAL_SCAN_PAGE_BUDGET_22C14B ? "yes" : "no",
    continuation_available: accounting.finalHasMore === true && pageCount >= CANONICAL_SCAN_PAGE_BUDGET_22C14B ? "yes" : "no",
    continuation_cursor: accounting.finalHasMore === true && pageCount >= CANONICAL_SCAN_PAGE_BUDGET_22C14B ? accounting.perPageCursorValues[accounting.perPageCursorValues.length - 1] ?? null : null,
    continuation_reason: accounting.finalHasMore === true && pageCount >= CANONICAL_SCAN_PAGE_BUDGET_22C14B ? "page_budget_exhausted" : "none",
    partial_scan_resumable: accounting.finalHasMore === true && pageCount >= CANONICAL_SCAN_PAGE_BUDGET_22C14B ? "yes" : "no",
    source_failure: accounting.finalHasMore === true && pageCount >= CANONICAL_SCAN_PAGE_BUDGET_22C14B ? "no" : "unknown",
    active_profile_post_source_healthy: accounting.finalHasMore === true && pageCount >= CANONICAL_SCAN_PAGE_BUDGET_22C14B && (accounting.finalStatusCode == null || accounting.finalStatusCode === 0 || accounting.finalStatusCode === "0") ? "yes" : "unknown",
    expected_gap_count: gapCount,
    final_gap_count: gapCount,
    final_gap_reason: gapReason,
    final_gap_classification: gapClassification,
    final_gap_evidence: gapEvidence
  };
}

async function runPaginatedScanJob22C14B(args: { scanRunId: string; tabId: number; profileUrl: string; expectedProfileVideoCount: number | null }): Promise<boolean> {
  const repository = createProfileTargetRepository();
  const profileIdentifier = profileIdentifierFromUrl(args.profileUrl);
  const existingCounts = await repository.countProfileTargets(profileIdentifier).catch(() => null);
  const existingCheckpoint = await repository.getCheckpoint(profileIdentifier).catch(() => null);
  const continuationCheckpoint = existingCheckpoint?.scan_continuation ?? null;
  const resumableContinuation = continuationCheckpoint?.continuation_available === "yes"
    && continuationCheckpoint.continuation_profile_identifier === profileIdentifier
    && (typeof continuationCheckpoint.continuation_cursor === "string" || typeof continuationCheckpoint.continuation_cursor === "number");
  const startingCursor = resumableContinuation ? continuationCheckpoint?.continuation_cursor ?? 0 : 0;
  const continuationCheckpointId = `${profileIdentifier}:${args.scanRunId}`;
  let totalPersisted = existingCounts?.total ?? 0;
  let cursor: string | number | null = startingCursor;
  let totalDiscovered = totalPersisted;
  let retryCount = 0;
  let consecutiveNoNewPages = 0;
  let currentRunZeroNetNewPages = 0;
  let currentRunNewInsertedTotal = 0;
  let currentRunDuplicateExistingTotal = 0;
  let staleResumeRecoveryAttempted = false;
  let autoContinuationBatchesRun = 1;
  let autoContinuationLimitReached = false;
  let finalExhaustionMode: "single_action_multi_batch" | "manual_continuation" | "failed" = "single_action_multi_batch";
  const buildScanContinuationCheckpoint = (overrides: Partial<ProfileTargetScanContinuationCheckpoint> = {}): ProfileTargetScanContinuationCheckpoint => ({
    continuation_available: "yes",
    continuation_cursor: cursor,
    continuation_page_count: pageIndex,
    continuation_request_count: pageIndex,
    continuation_persisted_total: totalPersisted,
    continuation_profile_identifier: profileIdentifier,
    continuation_run_id: args.scanRunId,
    continuation_checkpoint_id: continuationCheckpointId,
    continuation_cursor_source: resumableContinuation ? "saved_continuation_checkpoint" : "fresh_start",
    continuation_resume_strategy: resumableContinuation ? "resume_from_saved_cursor" : "fresh_scan",
    continuation_resume_result: resumableContinuation ? "resumed_from_saved_cursor" : "not_applicable",
    continuation_replay_duplicate_pages_detected: "no",
    continuation_replay_duplicate_count: currentRunDuplicateExistingTotal,
    continuation_recovery_attempted: staleResumeRecoveryAttempted ? "yes" : "no",
    continuation_recovery_result: staleResumeRecoveryAttempted ? "reused_saved_cursor" : "not_attempted",
    true_source_failure: "no",
    checkpoint_saved_at: new Date().toISOString(),
    ...overrides
  });
  const persistScanContinuationCheckpoint = async (scanContinuation: ProfileTargetScanContinuationCheckpoint): Promise<void> => {
    const nextCheckpoint: ProfileTargetCursorCheckpoint = {
      collect_cursor: existingCheckpoint?.collect_cursor ?? 0,
      last_processed_aweme_id: existingCheckpoint?.last_processed_aweme_id ?? null,
      last_checkpoint_at: scanContinuation.checkpoint_saved_at,
      chunk_processed_count: existingCheckpoint?.chunk_processed_count ?? 0,
      chunk_total_count: existingCheckpoint?.chunk_total_count ?? 0,
      scan_continuation: scanContinuation
    };
    await repository.setCheckpoint(profileIdentifier, nextCheckpoint).catch(() => undefined);
  };
  let staleResumeRecoveryResult: "not_attempted" | "restarted_from_fresh_cursor" | "restart_exhausted" = "not_attempted";
  let freshCursorRestartAttempted = false;
  let freshCursorRestartResult: "not_attempted" | "restarted" | "restart_exhausted" = "not_attempted";
  let pageIndex = 0;
  let lastProgressAtMs = Date.now();
  let batchStartPageIndex = 0;
  const accounting: PaginatedScanAccounting22C14B = { rawItemsTotal: 0, rawAwemeIdsTotal: 0, uniqueAwemeIds: new Set<string>(), uniqueAwemeIdOrder: [], orderedAcceptedTargets: [], acceptedTargetLedger: [], sameProfileEvidenceByAwemeId: new Map<string, PaginatedSameProfileEvidence22C14Q>(), requestedProfileIdentifier: profileIdentifier, apiResponseProfileIdentifier: null, targetsReturnedToBackgroundTotal: 0, backgroundTargetsReceivedTotal: 0, backgroundTargetsAfterValidationTotal: 0, backgroundDuplicateDropTotal: 0, backgroundInvalidDropTotal: 0, otherProfileDropCount: 0, favoriteEndpointDropCount: 0, emptyOrMissingAwemeIdCount: 0, repositoryExistingBeforeTotal: totalPersisted, repositoryWriteInputCount: 0, repositoryNewInsertedTotal: 0, repositoryDuplicateExistingTotal: 0, repositoryWriteTotalAfter: totalPersisted, perPageRawCounts: [], perPageRawAwemeIdCounts: [], perPageReturnedTargetCounts: [], perPageUniqueNewCounts: [], perPageDuplicateCounts: [], perPageCursorValues: [], perPageCursorPresentFlags: [], perPageHasMoreFlags: [], perPageStatusCodes: [], perPageParserRoutes: [], perPagePersistedTotals: [], firstPageRawCount: null, lastPageRawCount: null, lastPageAcceptedCount: null, lastPagePersistedDelta: null, finalHasMore: null, finalCursorPresent: cursor != null, finalStatusCode: null };
  const resumeSource: "new" | "resume_existing" = totalPersisted > 0 ? "resume_existing" : "new";
  for (;;) {
    while (pageIndex < batchStartPageIndex + CANONICAL_SCAN_PAGE_BUDGET_22C14B) {
    const pageRequestCount = pageIndex + 1;
    const response = await chrome.tabs.sendMessage(args.tabId, { type: CANONICAL_SCAN_PROFILE_PAGE_MESSAGE_22C14B, scan_job_id: args.scanRunId, scanRunId: args.scanRunId, scan_run_id: args.scanRunId, run_id: args.scanRunId, profileUrl: args.profileUrl, expected_profile_url: args.profileUrl, expectedProfileVideoCount: args.expectedProfileVideoCount, expected_profile_video_count: args.expectedProfileVideoCount, cursor, page_index: pageIndex, traceVersion: "22C-14B" } satisfies ExtensionMessage).catch((error) => ({ ok: false, error: error instanceof Error ? error.message : String(error), reason: "page_fetch_message_failed", verified_targets: [], verified_target_details: [], diagnostics: { scan_job_last_error: error instanceof Error ? error.message : String(error) } })) as ExtensionMessageResponse;
    const responseDiagnostics = response.diagnostics && typeof response.diagnostics === "object" ? response.diagnostics as Record<string, unknown> : {};
    const adapted = adaptCanonicalVerifiedTargets22C11B(response, args.profileUrl, new Date().toISOString());
    const pageReturnedTargets = Array.isArray(response.verified_targets) ? response.verified_targets.map((value) => String(value)) : [];
    const pageDiscoveredCount = adapted.queue.length;
    const pageRawCount = numberFromDiagnostics(responseDiagnostics.active_profile_post_page_fetch_raw_item_count_22C14B, response.total_candidates, adapted.diagnostics.canonical_queue_adapter_input_count, pageDiscoveredCount);
    const pageRawAwemeIdCount = numberFromDiagnostics(responseDiagnostics.active_profile_post_page_fetch_raw_aweme_id_count_22C14B, pageRawCount);
    const pageMissingAwemeIdCount = numberFromDiagnostics(responseDiagnostics.active_profile_post_page_fetch_empty_or_missing_aweme_id_count_22C14B, Math.max(pageRawCount - pageRawAwemeIdCount, 0));
    const pageBackgroundDuplicateDropCount = Math.max(pageReturnedTargets.length - pageDiscoveredCount, 0);
    const pageBackgroundInvalidDropCount = numberFromDiagnostics(adapted.diagnostics.adapter_invalid_count);
    const beforeTotal = totalPersisted;
    const uniqueBeforePage = accounting.uniqueAwemeIds.size;
    adapted.targetDetails.forEach((detail, detailIndex) => {
      const awemeId = detail.aweme_id;
      if (!/^\d{8,}$/.test(awemeId)) return;
      if (!accounting.uniqueAwemeIds.has(awemeId)) {
        accounting.uniqueAwemeIds.add(awemeId);
        accounting.uniqueAwemeIdOrder.push(awemeId);
      }
      const detailEvidence = detail.profile_card_evidence && typeof detail.profile_card_evidence === "object"
        ? detail.profile_card_evidence as Record<string, unknown>
        : {};
      const evidenceProfileUrl = detail.profile_url?.trim() || canonicalDetailString(detailEvidence, "profile_url");
      const evidenceProfileIdentifier = evidenceProfileUrl != null ? profileIdentifierFromUrl(evidenceProfileUrl) : null;
      const targetProfileIdentifier = accounting.requestedProfileIdentifier?.trim() || null;
      const requestedProfileSecUid = targetProfileIdentifier;
      const authorId = canonicalDetailString(detailEvidence, "author_uid", "author_id", "uid", "user_id");
      const authorSecUid = canonicalDetailString(detailEvidence, "author_sec_uid", "sec_uid", "secUid", "sec_user_id", "secUserId");
      const authorUniqueId = canonicalDetailString(detailEvidence, "author_unique_id", "unique_id", "uniqueId", "short_id", "shortId");
      const detailPostedAtMs = detail.posted_at == null ? null : Date.parse(detail.posted_at);
      const safeDesc = detail.caption ?? detail.title ?? detail.text_sample ?? detail.posted_text ?? null;
      const normalizedAuthorSecUid = normalizeDouyinProfileIdentity22C14S(authorSecUid).normalizedSecUid;
      const normalizedRequestSecUid = normalizeDouyinProfileIdentity22C14S(requestedProfileSecUid).normalizedSecUid;
      const normalizedApiTemplateSecUid = normalizeDouyinProfileIdentity22C14S(evidenceProfileIdentifier ?? accounting.apiResponseProfileIdentifier).normalizedSecUid;
      const normalizedRequestProfileSecUid = normalizeDouyinProfileIdentity22C14S(targetProfileIdentifier).normalizedSecUid;
      const normalizedApiTemplateProfileSecUid = normalizeDouyinProfileIdentity22C14S(evidenceProfileIdentifier ?? accounting.apiResponseProfileIdentifier).normalizedSecUid;
      const normalizedRepositoryProfileSecUid = normalizeDouyinProfileIdentity22C14S(detail.profile_url).normalizedSecUid;
      const comparableProfileSecUids = [
        ["request_sec_uid", normalizedRequestSecUid],
        ["api_template_sec_uid", normalizedApiTemplateSecUid],
        ["request_profile_identifier", normalizedRequestProfileSecUid],
        ["api_template_profile_identifier", normalizedApiTemplateProfileSecUid],
        ["repository_profile_identifier", normalizedRepositoryProfileSecUid]
      ].filter((entry): entry is [string, string] => entry[1] != null);
      const sameProfileValidationComparedFields = comparableProfileSecUids.map(([field]) => `author_sec_uid:${field}`);
      const authorSecUidMatches = normalizedAuthorSecUid != null && comparableProfileSecUids.some(([, value]) => value === normalizedAuthorSecUid);
      const authorSecUidMismatches = normalizedAuthorSecUid != null && comparableProfileSecUids.length > 0 && !authorSecUidMatches;
      const profileIdentifierMatches = evidenceProfileIdentifier != null && targetProfileIdentifier != null && normalizeDouyinProfileIdentity22C14S(evidenceProfileIdentifier).normalizedSecUid === normalizeDouyinProfileIdentity22C14S(targetProfileIdentifier).normalizedSecUid;
      const profileIdentifierMismatches = evidenceProfileIdentifier != null && targetProfileIdentifier != null && normalizeDouyinProfileIdentity22C14S(evidenceProfileIdentifier).normalizedSecUid != null && normalizeDouyinProfileIdentity22C14S(targetProfileIdentifier).normalizedSecUid != null && normalizeDouyinProfileIdentity22C14S(evidenceProfileIdentifier).normalizedSecUid !== normalizeDouyinProfileIdentity22C14S(targetProfileIdentifier).normalizedSecUid;
      const sameProfileValidationStatus = authorSecUidMismatches || profileIdentifierMismatches
        ? "outside_profile_detected"
        : authorSecUidMatches || profileIdentifierMatches
          ? "same_profile_validated"
          : "missing_evidence";
      const ledgerSameProfileValidationStatus = sameProfileValidationStatus === "same_profile_validated"
        ? "same_profile"
        : sameProfileValidationStatus === "outside_profile_detected"
          ? "outside_profile"
          : "insufficient_evidence";
      const sameProfileValidated = sameProfileValidationStatus === "same_profile_validated" ? "yes" : "no";
      const sameProfileMissingEvidence = sameProfileValidationStatus === "missing_evidence"
        ? [
          evidenceProfileIdentifier == null ? "source_profile_identifier_missing" : null,
          targetProfileIdentifier == null ? "target_profile_identifier_missing" : null,
          authorSecUid == null ? "author_sec_uid_missing" : null,
          requestedProfileSecUid == null ? "requested_profile_sec_uid_missing" : null
        ].filter((value): value is string => value != null)
        : [];
      const sameProfileValidationReason = sameProfileValidationStatus === "same_profile_validated"
        ? authorSecUidMatches ? "author_sec_uid_matches_requested_profile_sec_uid_after_normalization" : "profile_identifier_exact_match_after_normalization"
        : sameProfileValidationStatus === "outside_profile_detected"
          ? authorSecUidMismatches ? "author_sec_uid_mismatch_requested_profile_sec_uid" : "profile_identifier_mismatch"
          : sameProfileMissingEvidence.join(",") || "profile_identity_not_proven";
      const itemReason: OverDisplayedItemReason22C14Q = sameProfileValidationStatus === "same_profile_validated"
        ? "valid_same_profile_item_hidden_from_visible_count_basis"
        : sameProfileValidationStatus === "outside_profile_detected"
          ? "possible_cross_profile_contamination"
          : "profile_identity_not_proven";
      const sameProfileEvidence: PaginatedSameProfileEvidence22C14Q = {
        awemeId,
        profileUrl: evidenceProfileUrl,
        profileIdentifier: evidenceProfileIdentifier,
        pageIndexFound: pageIndex,
        requestIndexFound: pageRequestCount,
        rawIndexFound: detailIndex,
        sourceEndpoint: canonicalDetailString(detailEvidence, "endpoint_path", "source_endpoint") ?? (typeof responseDiagnostics.active_profile_post_page_fetch_endpoint_path_22C14B === "string" ? responseDiagnostics.active_profile_post_page_fetch_endpoint_path_22C14B : null),
        sourceCursor: responseDiagnostics.active_profile_post_page_fetch_cursor_22C14B as string | number | null ?? cursor,
        sourceProfileIdentifier: evidenceProfileIdentifier,
        targetProfileIdentifier,
        authorId,
        authorSecUid,
        authorUniqueId,
        requestedProfileSecUid,
        sameProfileValidationStatus,
        sameProfileMissingEvidence,
        desc: safeDesc,
        createTime: detailPostedAtMs == null || Number.isNaN(detailPostedAtMs) ? null : Math.floor(detailPostedAtMs / 1000),
        sameProfileValidated,
        sameProfileValidationReason,
        isPinnedCandidate: "unknown",
        isSpecialTabCandidate: "unknown",
        appearsInDomGrid: "unknown",
        appearsInVisibleProfileCountBasis: "unknown",
        itemReason
      };
      accounting.sameProfileEvidenceByAwemeId.set(awemeId, sameProfileEvidence);
      const orderedAcceptedTargets = accounting.orderedAcceptedTargets ?? (accounting.orderedAcceptedTargets = []);
      const acceptedTargetLedger = accounting.acceptedTargetLedger ?? (accounting.acceptedTargetLedger = []);
      const acceptedIndex = acceptedTargetLedger.length;
      const endpointPath = sameProfileEvidence.sourceEndpoint ?? undefined;
      const sourceTemplateProfileIdentifier = evidenceProfileIdentifier ?? accounting.apiResponseProfileIdentifier ?? null;
      const rawProfileMatchEvidence = [
        profileIdentifierMatches ? "profile_identifier_exact_match_after_normalization" : null,
        authorSecUidMatches ? "author_sec_uid_matches_requested_profile_sec_uid_after_normalization" : null,
        authorSecUidMatches && authorSecUid != null && requestedProfileSecUid != null && authorSecUid !== requestedProfileSecUid ? "raw_identifier_format_mismatch_normalized_match" : null,
        profileIdentifierMismatches ? "profile_identifier_mismatch_after_normalization" : null,
        authorSecUidMismatches ? "author_sec_uid_mismatch_requested_profile_sec_uid" : null,
        ...sameProfileMissingEvidence
      ].filter((value): value is string => value != null);
      acceptedTargetLedger.push({
        aweme_id: awemeId,
        accepted_index: acceptedIndex,
        page_index: pageIndex,
        raw_index_in_page: detailIndex,
        source: "active_profile_post_api",
        endpoint_path: endpointPath ?? null,
        request_url_path: endpointPath ?? null,
        request_cursor: cursor,
        response_cursor: responseDiagnostics.active_profile_post_page_fetch_next_cursor_22C14B as string | number | null ?? responseDiagnostics.scan_job_cursor as string | number | null ?? null,
        request_profile_identifier: targetProfileIdentifier,
        request_sec_uid: requestedProfileSecUid,
        api_template_profile_identifier: sourceTemplateProfileIdentifier,
        api_template_sec_uid: sourceTemplateProfileIdentifier,
        author_uid: authorId,
        author_sec_uid: authorSecUid,
        author_unique_id: authorUniqueId,
        normalized_author_sec_uid: normalizedAuthorSecUid,
        normalized_request_sec_uid: normalizedRequestSecUid,
        normalized_api_template_sec_uid: normalizedApiTemplateSecUid,
        normalized_request_profile_sec_uid: normalizedRequestProfileSecUid,
        normalized_api_template_profile_sec_uid: normalizedApiTemplateProfileSecUid,
        normalized_repository_profile_sec_uid: normalizedRepositoryProfileSecUid,
        same_profile_validation_compared_fields: sameProfileValidationComparedFields,
        desc_sample: typeof safeDesc === "string" && safeDesc.trim() ? safeDesc.trim().slice(0, 160) : null,
        create_time: sameProfileEvidence.createTime ?? null,
        same_profile_validation_status: ledgerSameProfileValidationStatus,
        same_profile_validation_reason: sameProfileValidationReason,
        profile_match_evidence: rawProfileMatchEvidence,
        raw_profile_match_evidence: rawProfileMatchEvidence,
        same_profile_missing_evidence: sameProfileMissingEvidence
      });
      orderedAcceptedTargets.push({
        ...sameProfileEvidence,
        acceptedIndex,
        sameProfileValidationStatus: ledgerSameProfileValidationStatus,
        sourceTemplateId: typeof responseDiagnostics.active_profile_post_template_id === "string" ? responseDiagnostics.active_profile_post_template_id : typeof responseDiagnostics.template_id === "string" ? responseDiagnostics.template_id : null
      });
      accounting.apiResponseProfileIdentifier ??= evidenceProfileIdentifier;
    });
    pageReturnedTargets.forEach((awemeId) => {
      if (/^\d{8,}$/.test(awemeId) && !accounting.uniqueAwemeIds.has(awemeId)) {
        accounting.uniqueAwemeIds.add(awemeId);
        accounting.uniqueAwemeIdOrder.push(awemeId);
      }
    });
    const pageUniqueNewCount = Math.max(accounting.uniqueAwemeIds.size - uniqueBeforePage, 0);
    const nextCursorRaw = responseDiagnostics.scan_job_cursor ?? responseDiagnostics.active_profile_post_page_fetch_next_cursor_22C14B ?? null;
    const nextCursor = typeof nextCursorRaw === "string" || typeof nextCursorRaw === "number" ? nextCursorRaw : null;
    const hasMore = responseDiagnostics.scan_job_has_more_state ?? responseDiagnostics.active_profile_post_page_fetch_has_more_state_22C14B;
    const normalizedHasMore = hasMore === true ? true : hasMore === false ? false : null;
    const pageStatusCode = responseDiagnostics.active_profile_post_page_fetch_last_status_code_22C14B as number | string | null ?? responseDiagnostics.scan_job_last_status_code as number | string | null ?? null;
    const parserRoute = typeof responseDiagnostics.active_profile_post_page_fetch_parser_route_22C14B === "string" ? responseDiagnostics.active_profile_post_page_fetch_parser_route_22C14B : null;
    accounting.rawItemsTotal += pageRawCount;
    accounting.rawAwemeIdsTotal += pageRawAwemeIdCount;
    accounting.targetsReturnedToBackgroundTotal += pageReturnedTargets.length;
    accounting.backgroundTargetsReceivedTotal += pageReturnedTargets.length;
    accounting.backgroundTargetsAfterValidationTotal += pageDiscoveredCount;
    accounting.backgroundDuplicateDropTotal += pageBackgroundDuplicateDropCount;
    accounting.backgroundInvalidDropTotal += pageBackgroundInvalidDropCount;
    accounting.emptyOrMissingAwemeIdCount += pageMissingAwemeIdCount;
    accounting.repositoryWriteInputCount += adapted.queue.length;
    accounting.perPageRawCounts.push(pageRawCount);
    accounting.perPageRawAwemeIdCounts.push(pageRawAwemeIdCount);
    accounting.perPageReturnedTargetCounts.push(pageReturnedTargets.length);
    accounting.perPageUniqueNewCounts.push(pageUniqueNewCount);
    accounting.perPageDuplicateCounts.push(Math.max(pageRawAwemeIdCount - pageUniqueNewCount, 0) + pageBackgroundDuplicateDropCount);
    accounting.perPageCursorValues.push(nextCursor);
    accounting.perPageCursorPresentFlags.push(nextCursor != null);
    accounting.perPageHasMoreFlags.push(normalizedHasMore);
    accounting.perPageStatusCodes.push(pageStatusCode);
    accounting.perPageParserRoutes.push(parserRoute);
    accounting.firstPageRawCount ??= pageRawCount;
    accounting.lastPageRawCount = pageRawCount;
    accounting.lastPageAcceptedCount = pageReturnedTargets.length;
    totalDiscovered += pageDiscoveredCount;
    if (adapted.queue.length > 0) {
      const persisted = await repository.upsertProfileTargetPage(profileIdentifier, adapted.queue, adapted.targetDetails, new Date().toISOString());
      totalPersisted = persisted.total;
      totalDiscovered = Math.max(totalDiscovered, totalPersisted);
    }
    accounting.lastPagePersistedDelta = Math.max(totalPersisted - beforeTotal, 0);
    accounting.repositoryNewInsertedTotal += accounting.lastPagePersistedDelta;
    accounting.repositoryDuplicateExistingTotal += Math.max(adapted.queue.length - accounting.lastPagePersistedDelta, 0);
    accounting.repositoryWriteTotalAfter = totalPersisted;
    accounting.perPagePersistedTotals.push(totalPersisted);
    consecutiveNoNewPages = totalPersisted > beforeTotal ? 0 : consecutiveNoNewPages + 1;
    cursor = nextCursor;
    accounting.finalHasMore = normalizedHasMore;
    accounting.finalCursorPresent = cursor != null;
    accounting.finalStatusCode = pageStatusCode;
    currentRunNewInsertedTotal += accounting.lastPagePersistedDelta ?? 0;
    currentRunDuplicateExistingTotal += Math.max(adapted.queue.length - (accounting.lastPagePersistedDelta ?? 0), 0);
    currentRunZeroNetNewPages = (accounting.lastPagePersistedDelta ?? 0) > 0 ? 0 : currentRunZeroNetNewPages + 1;
    const staleResumeDetected = resumeSource === "resume_existing"
      && accounting.repositoryExistingBeforeTotal > 0
      && pageRequestCount > 0
      && currentRunNewInsertedTotal === 0
      && currentRunDuplicateExistingTotal > 0
      && currentRunZeroNetNewPages >= CANONICAL_SCAN_NO_NEW_PAGE_LIMIT_22C14B
      && (normalizedHasMore === true || nextCursor != null);
    const staleResumeReason = staleResumeDetected
      ? "resume_existing_duplicate_only_pages_with_has_more"
      : "not_applicable";
    const currentRunEffectiveProgressTotal = currentRunNewInsertedTotal;
    const continuationCursorSource = staleResumeRecoveryAttempted
      ? "replay_recovery_checkpoint"
      : resumableContinuation
        ? "saved_continuation_checkpoint"
        : "fresh_start";
    const continuationResumeStrategy = staleResumeRecoveryAttempted
      ? "replay_recovery_from_saved_cursor"
      : resumableContinuation
        ? "resume_from_saved_cursor"
        : "fresh_scan";
    const continuationResumeResult = staleResumeRecoveryAttempted
      ? "replay_recovery_resumed"
      : resumableContinuation
        ? "resumed_from_saved_cursor"
        : "not_applicable";
    const remainingEstimateFromExpected = args.expectedProfileVideoCount == null ? null : Math.max(args.expectedProfileVideoCount - totalPersisted, 0);
    const diagnostics: Record<string, unknown> = {
      ...responseDiagnostics,
      ...adapted.diagnostics,
      ...paginatedScanAccountingDiagnostics22C14B(accounting, args.expectedProfileVideoCount, totalPersisted),
      stale_resume_detected: staleResumeDetected ? "yes" : "no",
      stale_resume_reason: staleResumeReason,
      stale_resume_recovery_attempted: staleResumeRecoveryAttempted ? "yes" : "no",
      stale_resume_recovery_result: staleResumeRecoveryResult,
      repository_existing_before_total: accounting.repositoryExistingBeforeTotal,
      persisted_total_existing_before_run: accounting.repositoryExistingBeforeTotal,
      current_run_new_inserted_total: currentRunNewInsertedTotal,
      current_run_duplicate_existing_total: currentRunDuplicateExistingTotal,
      continuation_progress_total: currentRunEffectiveProgressTotal,
      current_run_effective_progress_total: currentRunEffectiveProgressTotal,
      current_run_pages_with_zero_net_new: currentRunZeroNetNewPages,
      fresh_cursor_restart_attempted: freshCursorRestartAttempted ? "yes" : "no",
      fresh_cursor_restart_result: freshCursorRestartResult,
      current_run_progress_authority: "current_run_new_inserted_total",
      displayed_progress_excludes_existing_repository: "yes",
      current_run_found_count: currentRunEffectiveProgressTotal,
      persisted_total_count: totalPersisted,
      remaining_estimate_from_expected: remainingEstimateFromExpected,
      continuation_cursor_source: continuationCursorSource,
      continuation_resume_strategy: continuationResumeStrategy,
      continuation_resume_result: continuationResumeResult,
      continuation_replay_duplicate_pages_detected: staleResumeDetected ? "yes" : "no",
      continuation_replay_duplicate_count: currentRunDuplicateExistingTotal,
      continuation_recovery_attempted: staleResumeRecoveryAttempted ? "yes" : "no",
      continuation_recovery_result: staleResumeRecoveryAttempted ? "reused_saved_cursor" : "not_attempted",
      continuation_checkpoint_id: continuationCheckpointId,
      continuation_run_id: args.scanRunId,
      continuation_persisted_total: totalPersisted,
      auto_continuation_enabled: "yes",
      auto_continuation_batches_run: autoContinuationBatchesRun,
      auto_continuation_reason: resumableContinuation ? "resume_saved_continuation_then_continue" : "healthy_page_budget_boundary_continues_in_same_run",
      auto_continuation_limit_reached: autoContinuationLimitReached ? "yes" : "no",
      final_exhaustion_mode: finalExhaustionMode,
      user_action_count_required_for_full_scan: 1,
      true_source_failure: "no",
      scan_progress_discovered: currentRunEffectiveProgressTotal,
      scan_progress_phase_label: staleResumeRecoveryAttempted && staleResumeRecoveryResult === "restarted_from_fresh_cursor"
        ? "Refreshing scan cursor"
        : response.ok ? "Scanning profile" : "Retry wait"
    };
    response.diagnostics = diagnostics;
    if (
      response.ok
      && args.expectedProfileVideoCount != null
      && args.expectedProfileVideoCount > 0
      && totalPersisted >= args.expectedProfileVideoCount
    ) {
      const operatorPersisted = args.expectedProfileVideoCount;
      const apiDiscoveredBeforeCap = totalPersisted;
      const displayedStopDiagnostics: Record<string, unknown> = {
        ...diagnostics,
        scan_job_stop_reason: "displayed_profile_count_reached",
        scan_job_has_more_at_stop: normalizedHasMore ?? null,
        scan_progress_phase_label: "Finalizing scan",
        displayed_profile_count: args.expectedProfileVideoCount,
        api_discovered_count_before_cap: apiDiscoveredBeforeCap,
        over_displayed_count: Math.max(apiDiscoveredBeforeCap - operatorPersisted, 0),
        collect_scope: DISPLAYED_PROFILE_COLLECT_SCOPE,
        queue_cap_applied: apiDiscoveredBeforeCap > operatorPersisted ? "yes" : "no",
        count_semantics_status: "completed_with_api_over_displayed_count",
        scan_health_verdict: "ready_api_over_displayed_count",
        scan_health_required_user_action: "proceed_with_non_blocking_same_profile_api_over_display_warning"
      };
      return finalizePaginatedScanTerminalState22C14B({
        scanRunId: args.scanRunId,
        profileUrl: args.profileUrl,
        expectedCount: args.expectedProfileVideoCount,
        totalPersisted: operatorPersisted,
        totalDiscovered,
        pageCount: pageIndex + 1,
        requestCount: pageRequestCount,
        lastError: null,
        result: "success",
        responseDiagnostics: displayedStopDiagnostics
      });
    }
    if (!response.ok) {
      retryCount += 1;
      const reason = String(response.reason ?? response.error ?? "page_fetch_failed");
      await checkpointPaginatedScanJob22C14B({
        scanRunId: args.scanRunId,
        profileUrl: args.profileUrl,
        expectedCount: args.expectedProfileVideoCount,
        response,
        pageIndex,
        cursor,
        totalDiscovered,
        totalPersisted,
        status: "retry_wait",
        retryCount,
        consecutiveNoNewPages,
        resumeSource,
        lastError: reason,
        nextRetryAt: new Date(Date.now() + (2 ** retryCount) * 1000).toISOString()
      });
      const statusCode = diagnostics.active_profile_post_page_fetch_last_status_code_22C14B ?? diagnostics.scan_job_last_status_code ?? null;
      const isNonZero = statusCode != null && statusCode !== 0 && statusCode !== "0";
      const setupUnavailable = reason === "required_query_keys_unavailable" || reason === "active_profile_post_response_status_non_zero" || isNonZero;
      const terminal = retryCount >= CANONICAL_SCAN_MAX_RETRIES_22C14B;
      const terminalReason = isNonZero
        ? "active_profile_post_response_status_non_zero_terminal"
        : setupUnavailable
          ? "active_profile_post_required_query_keys_unavailable_terminal"
          : `${reason}_terminal`;
      const retryReason = isNonZero ? "active_profile_post_response_status_non_zero_retryable" : `${reason}_retryable`;
      const nextRetryAt = terminal ? null : new Date(Date.now() + (2 ** retryCount) * 1000).toISOString();
      const storedForRetryDiagnostics = await chrome.storage.local.get(WHOLE_PROFILE_HARVEST_STATE_KEY).catch(() => ({} as Record<string, unknown>));
      const stateForRetryDiagnostics = storedForRetryDiagnostics?.[WHOLE_PROFILE_HARVEST_STATE_KEY] as WholeProfileHarvestState | undefined;
      const previousRetryDiagnostics = stateForRetryDiagnostics?.debug?.last_request_summary && typeof stateForRetryDiagnostics.debug.last_request_summary === "object" ? stateForRetryDiagnostics.debug.last_request_summary as Record<string, unknown> : {};
      const retryDiagnostics = { ...previousRetryDiagnostics, ...diagnostics, active_profile_post_fetch_status_non_zero_retryable: isNonZero ? "yes" : "no", active_profile_post_fetch_status_non_zero_retry_count: retryCount, active_profile_post_response_status_code: statusCode ?? "unknown", active_profile_post_fetch_stop_reason: isNonZero ? "active_profile_post_response_status_non_zero" : reason, active_profile_post_template_found: diagnostics.active_profile_post_template_found ?? (isNonZero ? "no" : "unknown"), active_profile_post_template_required_query_keys_available: diagnostics.active_profile_post_template_required_query_keys_available ?? (setupUnavailable ? "no" : "unknown"), active_profile_post_recovery_attempted: "yes", active_profile_post_recovery_result: terminal ? "failed" : "retry_wait", active_profile_post_recovery_reason: terminal ? terminalReason : retryReason, active_profile_post_template_retry_count: setupUnavailable ? retryCount : 0, active_profile_post_non_zero_status_retryable: isNonZero ? "yes" : "no", scan_stop_authoritative: isNonZero ? "active_profile_post_response_status_non_zero" : reason, scan_stop_authority_source: "paginated_active_profile_post_retry_22C14B", expected_count_gate_meaningful_active_fetch: "no", expected_count_gate_dom_only_convergence_allowed: "no", scan_job_retry_count: retryCount, scan_job_next_retry_at: nextRetryAt, scan_job_last_error: terminal ? terminalReason : retryReason };
      if (terminal && collectCanonicalFallbackCandidates22C14F(retryDiagnostics, args.profileUrl).candidates.length > 0) {
        await finalizeCanonicalScanSuccess22C11B(args.scanRunId, args.profileUrl, { ...response, ok: true, verified_targets: [], verified_target_details: [], scan_rounds: pageIndex + 1, diagnostics: { ...retryDiagnostics, scan_fallback_original_active_fetch_error: terminalReason } }, { tabId: args.tabId });
        return true;
      }
      await checkpointPaginatedScanJob22C14B({ scanRunId: args.scanRunId, profileUrl: args.profileUrl, expectedCount: args.expectedProfileVideoCount, response: { ...response, diagnostics: retryDiagnostics }, pageIndex, cursor, totalDiscovered, totalPersisted, status: terminal ? "failed" : "retry_wait", retryCount, consecutiveNoNewPages, resumeSource, lastError: terminal ? terminalReason : retryReason, nextRetryAt });
      if (terminal) return false;
      const retryDelayMs = scanRetryWaitDelayMs22C14B(nextRetryAt);
      if (retryDelayMs == null) {
        await checkpointPaginatedScanJob22C14B({ scanRunId: args.scanRunId, profileUrl: args.profileUrl, expectedCount: args.expectedProfileVideoCount, response: { ...response, diagnostics: { ...retryDiagnostics, scan_job_retry_wait_stall_guard_triggered: "yes", scan_job_last_error: "retry_wait_invalid_checkpoint" } }, pageIndex, cursor, totalDiscovered, totalPersisted, status: "failed", retryCount, consecutiveNoNewPages, resumeSource, lastError: "retry_wait_invalid_checkpoint" });
        return false;
      }
      const forcedStaleRetryWait = diagnostics.scan_job_retry_wait_stall_guard_triggered === "force";
      const staleRetryWait = forcedStaleRetryWait || retryDelayMs > CANONICAL_SCAN_RETRY_WAIT_STALL_MS_22C14B;
      if (staleRetryWait) {
        await checkpointPaginatedScanJob22C14B({ scanRunId: args.scanRunId, profileUrl: args.profileUrl, expectedCount: args.expectedProfileVideoCount, response: { ...response, diagnostics: { ...retryDiagnostics, scan_job_retry_wait_stall_guard_triggered: "yes", scan_job_last_error: "retry_wait_stall_guard_terminal" } }, pageIndex, cursor, totalDiscovered, totalPersisted, status: "failed", retryCount, consecutiveNoNewPages, resumeSource, lastError: "retry_wait_stall_guard_terminal" });
        return false;
      }
      await sleepScanRetryWait22C14B(retryDelayMs);
      const wakeAt = new Date().toISOString();
      await checkpointPaginatedScanJob22C14B({ scanRunId: args.scanRunId, profileUrl: args.profileUrl, expectedCount: args.expectedProfileVideoCount, response: { ...response, ok: true, diagnostics: { ...retryDiagnostics, scan_job_retry_wake_triggered: "yes", scan_job_retry_wake_source: "background_retry_wait_timer", scan_job_retry_wake_at: wakeAt, scan_job_status: "running", scan_job_last_error: null } }, pageIndex, cursor, totalDiscovered, totalPersisted, status: "running", retryCount, consecutiveNoNewPages, resumeSource, lastError: null, nextRetryAt: null });
      continue;
    }
    if (staleResumeDetected && !freshCursorRestartAttempted) {
      staleResumeRecoveryAttempted = true;
      staleResumeRecoveryResult = "restarted_from_fresh_cursor";
      freshCursorRestartAttempted = true;
      freshCursorRestartResult = "restarted";
      consecutiveNoNewPages = 0;
      currentRunZeroNetNewPages = 0;
      currentRunNewInsertedTotal = 0;
      currentRunDuplicateExistingTotal = 0;
      cursor = resumableContinuation ? continuationCheckpoint?.continuation_cursor ?? cursor : cursor;
      const recoveredCheckpoint = buildScanContinuationCheckpoint({
        continuation_cursor: cursor,
        continuation_cursor_source: "replay_recovery_checkpoint",
        continuation_resume_strategy: "replay_recovery_from_saved_cursor",
        continuation_resume_result: "replay_recovery_resumed",
        continuation_replay_duplicate_pages_detected: "yes",
        continuation_replay_duplicate_count: accounting.repositoryDuplicateExistingTotal,
        continuation_recovery_attempted: "yes",
        continuation_recovery_result: resumableContinuation ? "reused_saved_cursor" : "checkpoint_unavailable"
      });
      await persistScanContinuationCheckpoint(recoveredCheckpoint);
      response.diagnostics = {
        ...diagnostics,
        stale_resume_detected: "yes",
        stale_resume_reason: staleResumeReason,
        stale_resume_recovery_attempted: "yes",
        stale_resume_recovery_result: "restarted_from_fresh_cursor",
        fresh_cursor_restart_attempted: "yes",
        fresh_cursor_restart_result: "restarted",
        continuation_cursor_source: "replay_recovery_checkpoint",
        continuation_resume_strategy: "replay_recovery_from_saved_cursor",
        continuation_resume_result: "replay_recovery_resumed",
        continuation_replay_duplicate_pages_detected: "yes",
        continuation_replay_duplicate_count: accounting.repositoryDuplicateExistingTotal,
        continuation_recovery_attempted: "yes",
        continuation_recovery_result: resumableContinuation ? "reused_saved_cursor" : "checkpoint_unavailable",
        current_run_new_inserted_total: 0,
        current_run_duplicate_existing_total: 0,
        current_run_effective_progress_total: 0,
        continuation_progress_total: 0,
        current_run_pages_with_zero_net_new: 0,
        current_run_found_count: 0,
        scan_progress_discovered: 0,
        scan_progress_phase_label: "Refreshing scan cursor"
      };
      await checkpointPaginatedScanJob22C14B({ scanRunId: args.scanRunId, profileUrl: args.profileUrl, expectedCount: args.expectedProfileVideoCount, response, pageIndex, cursor, totalDiscovered, totalPersisted, status: "running", retryCount, consecutiveNoNewPages, resumeSource, lastError: null });
      continue;
    }
    if (consecutiveNoNewPages >= CANONICAL_SCAN_NO_NEW_PAGE_LIMIT_22C14B && hasMore === true) {
      const finalFailureReason = staleResumeRecoveryAttempted
        ? "stale_resume_duplicate_replay_after_fresh_restart"
        : "repeated_zero_new_pages_with_has_more";
      staleResumeRecoveryResult = staleResumeRecoveryAttempted ? "restart_exhausted" : staleResumeRecoveryResult;
      freshCursorRestartResult = staleResumeRecoveryAttempted ? "restart_exhausted" : freshCursorRestartResult;
      response.diagnostics = {
        ...diagnostics,
        stale_resume_detected: staleResumeDetected ? "yes" : "no",
        stale_resume_reason: staleResumeDetected ? staleResumeReason : "not_applicable",
        stale_resume_recovery_attempted: staleResumeRecoveryAttempted ? "yes" : "no",
        stale_resume_recovery_result: staleResumeRecoveryResult,
        fresh_cursor_restart_attempted: freshCursorRestartAttempted ? "yes" : "no",
        fresh_cursor_restart_result: freshCursorRestartResult,
        final_failure_reason_refined: finalFailureReason
      };
      await checkpointPaginatedScanJob22C14B({ scanRunId: args.scanRunId, profileUrl: args.profileUrl, expectedCount: args.expectedProfileVideoCount, response, pageIndex, cursor, totalDiscovered, totalPersisted, status: "failed", retryCount, consecutiveNoNewPages, resumeSource, lastError: finalFailureReason });
      return false;
    }
    if (hasMore === false) {
      const accountingBeforeSecondary = paginatedScanAccountingDiagnostics22C14B(accounting, args.expectedProfileVideoCount, totalPersisted);
      const secondary = await verifyPaginatedScanSecondaryGap22C14P({ scanRunId: args.scanRunId, tabId: args.tabId, profileUrl: args.profileUrl, expectedCount: args.expectedProfileVideoCount, totalPersisted, responseDiagnostics: { ...diagnostics, ...accountingBeforeSecondary }, apiAwemeIds: accounting.uniqueAwemeIds, repository, at: new Date().toISOString() });
      if (secondary.recoveredCount > 0) {
        totalPersisted = secondary.totalPersisted;
        totalDiscovered = Math.max(totalDiscovered + secondary.recoveredCount, totalPersisted);
        accounting.repositoryWriteInputCount += secondary.recoveredCount;
        accounting.repositoryNewInsertedTotal += secondary.recoveredCount;
        accounting.repositoryWriteTotalAfter = totalPersisted;
      }
      const accountingAfterSecondary = paginatedScanAccountingDiagnostics22C14B(accounting, args.expectedProfileVideoCount, totalPersisted);
      const secondaryGapAfter = args.expectedProfileVideoCount == null ? 0 : Math.max(args.expectedProfileVideoCount - totalPersisted, 0);
      const continuationBatchNewCount = accounting.repositoryNewInsertedTotal;
      const continuationBatchRawCount = accounting.rawItemsTotal;
      const continuationBatchAcceptedCount = accounting.backgroundTargetsAfterValidationTotal;
      const persistedTotalBeforeContinuation = accounting.repositoryExistingBeforeTotal;
      const persistedTotalAfterContinuation = totalPersisted;
      const finalCumulativeCollectableCount = totalPersisted;
      const overDisplayedExtraIds = Array.isArray(accountingAfterSecondary.over_displayed_extra_ids_exact)
        ? accountingAfterSecondary.over_displayed_extra_ids_exact.filter((value): value is string => typeof value === "string")
        : [];
      const overDisplayedValidationPassed = accountingAfterSecondary.over_displayed_validation_status === "validated_same_profile" && accountingAfterSecondary.over_displayed_same_profile_validated === "yes";
      const secondaryRecoveredCountForSemantics = countSemanticsNumber22C14Q(secondary.diagnostics.secondary_recovered_count) ?? secondary.recoveredCount;
      const countSemanticsAfterSecondary = countSemanticsDiagnostics22C14Q({
        displayedProfileCount: args.expectedProfileVideoCount,
        displayedProfileCountSource: secondary.diagnostics.expected_count_source ?? diagnostics.expected_profile_video_count_source,
        displayedProfileCountRawText: secondary.diagnostics.expected_count_raw_text ?? diagnostics.expected_profile_video_count_raw_text,
        apiRawCount: countSemanticsNumber22C14Q(accountingAfterSecondary.api_raw_count) ?? accounting.rawItemsTotal,
        apiUniqueCount: countSemanticsNumber22C14Q(accountingAfterSecondary.api_unique_count) ?? accounting.uniqueAwemeIds.size,
        apiHasMoreFinal: false,
        collectableCount: finalCumulativeCollectableCount,
        persistedCount: totalPersisted,
        secondaryRecoveryAttempted: secondary.diagnostics.secondary_gap_probe_attempted ?? "yes",
        secondaryRecoveredCount: secondaryRecoveredCountForSemantics,
        parserExtractionDropCount: Math.max(accounting.rawAwemeIdsTotal - accounting.targetsReturnedToBackgroundTotal, 0) + accounting.emptyOrMissingAwemeIdCount,
        validationOrProfileDropCount: accounting.backgroundInvalidDropTotal + accounting.otherProfileDropCount + accounting.favoriteEndpointDropCount,
        repositoryDropCount: accounting.repositoryDuplicateExistingTotal,
        apiDuplicateAwemeIdsTotal: Math.max(accounting.rawAwemeIdsTotal - accounting.uniqueAwemeIds.size, 0),
        overDisplayedSameProfileValidated: accountingAfterSecondary.over_displayed_same_profile_validated,
        overDisplayedExtraIdsSample: overDisplayedExtraIds.length > 0 ? overDisplayedExtraIds.slice(0, 10) : null,
        overDisplayedExtraIdsExact: accountingAfterSecondary.over_displayed_extra_ids_exact,
        overDisplayedExtraItemsExact: accountingAfterSecondary.over_displayed_extra_items_exact,
        overDisplayedItemizedReasonSummary: accountingAfterSecondary.over_displayed_itemized_reason_summary,
        overDisplayedExtraSource: accountingAfterSecondary.over_displayed_extra_source ?? (overDisplayedExtraIds.length > 0 ? "active_profile_post_api_pagination_after_secondary_gap_probe" : null),
        overDisplayedExtraCount: countSemanticsNumber22C14Q(accountingAfterSecondary.over_displayed_count) ?? overDisplayedExtraIds.length,
        extraIdsSameProfileMatchCount: countSemanticsNumber22C14Q(accountingAfterSecondary.extra_ids_same_profile_match_count ?? accountingAfterSecondary.over_displayed_extra_ids_same_profile_match_count) ?? 0,
        extraIdsProfileMismatchCount: countSemanticsNumber22C14Q(accountingAfterSecondary.extra_ids_profile_mismatch_count ?? accountingAfterSecondary.over_displayed_extra_ids_profile_mismatch_count) ?? 0,
        overDisplayedValidationStatus: accountingAfterSecondary.over_displayed_validation_status,
        overDisplayedValidationFailureReason: accountingAfterSecondary.over_displayed_validation_failure_reason,
        overDisplayedReason: overDisplayedExtraIds.length > 0 ? accountingAfterSecondary.count_semantics_reason ?? accountingAfterSecondary.over_displayed_reason : null,
        overDisplayedCameFromContinuationTail: overDisplayedExtraIds.length > 0 && autoContinuationBatchesRun > 1 ? "yes" : overDisplayedExtraIds.length > 0 ? "no" : "not_applicable",
        requestedProfileIdentifier: profileIdentifier,
        repositoryProfileIdentifier: profileIdentifier,
        repositoryExistingBeforeTotal: accounting.repositoryExistingBeforeTotal,
        repositoryExistingSameProfileTotal: accounting.repositoryExistingBeforeTotal,
        repositoryExistingOtherProfileTotal: 0,
        apiResponseProfileIdentifier: accountingAfterSecondary.api_response_profile_identifier,
        templateCacheProfileMatch: accountingAfterSecondary.template_cache_profile_match ?? (overDisplayedValidationPassed ? "yes" : "no"),
        directApiTemplateProfileMatch: accountingAfterSecondary.direct_api_template_profile_match ?? (overDisplayedValidationPassed ? "yes" : "no"),
        continuationBatchNewCount,
        continuationBatchRawCount,
        continuationBatchAcceptedCount,
        persistedTotalBeforeContinuation,
        persistedTotalAfterContinuation,
        finalCumulativeCollectableCount,
        finalDisplayAuthority: "cumulative_persisted_count",
        finalHeaderCount: finalCumulativeCollectableCount,
        finalCounterCount: totalPersisted,
        headerCounterAuthorityMatch: finalCumulativeCollectableCount === totalPersisted ? "yes" : "no"
      });
      const countSemanticsStatus = String(countSemanticsAfterSecondary.count_semantics_status ?? "");
      const finalGapReason = secondaryGapAfter <= 0 ? "none" : countSemanticsStatus === "completed_with_displayed_count_mismatch" || countSemanticsStatus === "completed_with_partial_secondary_recovery" ? "displayed_count_not_fully_collectable" : String(secondary.diagnostics.final_gap_reason ?? "unavailable_posts_after_api_exhaustion");
      const finalDiagnostics = {
        ...diagnostics,
        ...secondary.diagnostics,
        ...countSemanticsAfterSecondary,
        ...accountingAfterSecondary,
        count_semantics_status: countSemanticsAfterSecondary.count_semantics_status,
        count_semantics_reason: countSemanticsAfterSecondary.count_semantics_reason,
        scan_health_verdict: countSemanticsAfterSecondary.scan_health_verdict,
        scan_health_verdict_reason: countSemanticsAfterSecondary.scan_health_verdict_reason,
        scan_health_required_user_action: countSemanticsAfterSecondary.scan_health_required_user_action,
        secondary_recovery_attempted: countSemanticsAfterSecondary.secondary_recovery_attempted,
        secondary_recovered_count: countSemanticsAfterSecondary.secondary_recovered_count,
        final_gap_count: secondaryGapAfter,
        expected_gap_count: secondaryGapAfter,
        final_gap_reason: finalGapReason,
        final_gap_classification: secondaryGapAfter <= 0 ? "none" : finalGapReason,
        final_gap_evidence: secondary.diagnostics.final_gap_evidence ?? accountingAfterSecondary.final_gap_evidence,
        scan_job_resume_source: resumeSource,
        scan_job_total_persisted: totalPersisted,
        scan_job_total_discovered: totalDiscovered,
        scan_job_duplicate_or_existing_count: Math.max(totalDiscovered - totalPersisted, 0),
        scan_job_pages_fetched: pageIndex + 1,
        scan_job_request_count: pageRequestCount,
        scan_job_page_budget: CANONICAL_SCAN_PAGE_BUDGET_22C14B,
        scan_job_stop_reason: "has_more_false",
        scan_job_has_more_at_stop: false,
        auto_continuation_enabled: "yes",
        auto_continuation_batches_run: autoContinuationBatchesRun,
        auto_continuation_reason: autoContinuationBatchesRun > 1 ? "continued_across_healthy_page_budget_boundaries" : "not_needed_single_batch_exhaustion",
        auto_continuation_limit_reached: autoContinuationLimitReached ? "yes" : "no",
        final_exhaustion_mode: finalExhaustionMode,
        user_action_count_required_for_full_scan: 1,
        continuation_available: "no",
        continuation_reason: "none",
        partial_scan_resumable: "no",
        page_budget_exhausted: "no",
        scan_mode: "api_profile_post_pagination",
        scan_mode_visible_scroll_required: "no",
        expected_profile_video_count: args.expectedProfileVideoCount,
        scan_progress_phase_label: "Finalizing scan"
      };
      const nearComplete = nearCompleteExpectedGap22C14N(args.expectedProfileVideoCount, totalPersisted);
      const terminalResult = args.expectedProfileVideoCount != null && totalPersisted < args.expectedProfileVideoCount ? "incomplete" as const : "success" as const;
      return finalizePaginatedScanTerminalState22C14B({
        scanRunId: args.scanRunId,
        profileUrl: args.profileUrl,
        expectedCount: args.expectedProfileVideoCount,
        totalPersisted,
        totalDiscovered,
        pageCount: pageIndex + 1,
        requestCount: pageRequestCount,
        lastError: terminalResult === "incomplete" && !nearComplete.allowed ? "expected_gap_unresolved_strict_completeness_gate" : null,
        result: terminalResult,
        responseDiagnostics: finalDiagnostics
      });
    }
    await checkpointPaginatedScanJob22C14B({ scanRunId: args.scanRunId, profileUrl: args.profileUrl, expectedCount: args.expectedProfileVideoCount, response, pageIndex, cursor, totalDiscovered, totalPersisted, status: "running", retryCount, consecutiveNoNewPages, resumeSource, lastError: null });
    if (Date.now() - lastProgressAtMs > CANONICAL_SCAN_RUNNING_STALL_MS_22C14B && consecutiveNoNewPages > 0 && hasMore !== true) {
      await checkpointPaginatedScanJob22C14B({ scanRunId: args.scanRunId, profileUrl: args.profileUrl, expectedCount: args.expectedProfileVideoCount, response: { ...response, diagnostics: { ...diagnostics, scan_job_last_error: "running_no_progress_watchdog_terminal" } }, pageIndex, cursor, totalDiscovered, totalPersisted, status: "failed", retryCount, consecutiveNoNewPages, resumeSource, lastError: "running_no_progress_watchdog_terminal" });
      return false;
    }
    if (totalPersisted > beforeTotal) lastProgressAtMs = Date.now();
    if (cursor == null) {
      const terminalResult = args.expectedProfileVideoCount != null && totalPersisted < args.expectedProfileVideoCount ? "incomplete" as const : "success" as const;
      return finalizePaginatedScanTerminalState22C14B({
        scanRunId: args.scanRunId,
        profileUrl: args.profileUrl,
        expectedCount: args.expectedProfileVideoCount,
        totalPersisted,
        totalDiscovered,
        pageCount: pageIndex + 1,
        requestCount: pageRequestCount,
        lastError: terminalResult === "incomplete" ? "active_profile_post_cursor_absent_before_expected" : null,
        result: terminalResult,
        responseDiagnostics: {
          ...diagnostics,
          ...paginatedScanAccountingDiagnostics22C14B(accounting, args.expectedProfileVideoCount, totalPersisted),
          scan_job_resume_source: resumeSource,
          scan_job_total_persisted: totalPersisted,
          scan_job_total_discovered: totalDiscovered,
          scan_job_duplicate_or_existing_count: Math.max(totalDiscovered - totalPersisted, 0),
          scan_job_pages_fetched: pageIndex + 1,
          scan_job_request_count: pageRequestCount,
          scan_job_page_budget: CANONICAL_SCAN_PAGE_BUDGET_22C14B,
          scan_job_stop_reason: "cursor_absent",
          scan_job_has_more_at_stop: hasMore ?? null,
          scan_mode: "api_profile_post_pagination",
          scan_mode_visible_scroll_required: "no",
          expected_profile_video_count: args.expectedProfileVideoCount,
          scan_progress_phase_label: "Finalizing scan"
        }
      });
    }
    pageIndex += 1;
    }
    if (accounting.finalHasMore === true
    && cursor != null
    && autoContinuationBatchesRun < CANONICAL_SCAN_AUTO_CONTINUATION_MAX_BATCHES_22C14B
    && (accounting.finalStatusCode == null || accounting.finalStatusCode === 0 || accounting.finalStatusCode === "0")) {
      autoContinuationBatchesRun += 1;
      batchStartPageIndex = pageIndex;
      continue;
    }
    autoContinuationLimitReached = accounting.finalHasMore === true && cursor != null;
    finalExhaustionMode = autoContinuationLimitReached ? "manual_continuation" : finalExhaustionMode;
    const terminalResult = args.expectedProfileVideoCount != null && totalPersisted < args.expectedProfileVideoCount ? "incomplete" as const : "success" as const;
    const budgetCheckpoint = buildScanContinuationCheckpoint({
    continuation_available: "yes",
    continuation_cursor: cursor,
    continuation_page_count: pageIndex,
    continuation_request_count: pageIndex,
    continuation_persisted_total: totalPersisted,
    continuation_cursor_source: staleResumeRecoveryAttempted ? "replay_recovery_checkpoint" : resumableContinuation ? "saved_continuation_checkpoint" : "fresh_start",
    continuation_resume_strategy: staleResumeRecoveryAttempted ? "replay_recovery_from_saved_cursor" : resumableContinuation ? "resume_from_saved_cursor" : "fresh_scan",
    continuation_resume_result: staleResumeRecoveryAttempted ? "replay_recovery_resumed" : resumableContinuation ? "resumed_from_saved_cursor" : "not_applicable",
    continuation_replay_duplicate_pages_detected: accounting.repositoryDuplicateExistingTotal > 0 && currentRunNewInsertedTotal === 0 ? "yes" : "no",
    continuation_replay_duplicate_count: currentRunDuplicateExistingTotal,
    continuation_recovery_attempted: staleResumeRecoveryAttempted ? "yes" : "no",
    continuation_recovery_result: staleResumeRecoveryAttempted ? "reused_saved_cursor" : "not_attempted"
  });
  await persistScanContinuationCheckpoint(budgetCheckpoint);
  return finalizePaginatedScanTerminalState22C14B({
    scanRunId: args.scanRunId,
    profileUrl: args.profileUrl,
    expectedCount: args.expectedProfileVideoCount,
    totalPersisted,
    totalDiscovered,
    pageCount: pageIndex,
    requestCount: pageIndex,
    lastError: terminalResult === "incomplete" ? "incomplete_api_budget_exhausted" : null,
    result: terminalResult,
    responseDiagnostics: {
      ...paginatedScanAccountingDiagnostics22C14B(accounting, args.expectedProfileVideoCount, totalPersisted),
      scan_job_resume_source: resumeSource,
      scan_job_total_persisted: totalPersisted,
      scan_job_total_discovered: totalDiscovered,
      scan_job_duplicate_or_existing_count: Math.max(totalDiscovered - totalPersisted, 0),
      scan_job_pages_fetched: pageIndex,
      scan_job_request_count: pageIndex,
      scan_job_page_budget: CANONICAL_SCAN_PAGE_BUDGET_22C14B,
      scan_job_stop_reason: autoContinuationLimitReached ? "auto_continuation_limit_reached" : "page_budget_exhausted",
      scan_job_has_more_at_stop: true,
      scan_job_has_more_state: true,
      scan_job_cursor: cursor,
      page_budget_limit: CANONICAL_SCAN_PAGE_BUDGET_22C14B,
      page_budget_exhausted: "yes",
      continuation_available: "yes",
      continuation_cursor: cursor,
      continuation_reason: autoContinuationLimitReached ? "auto_continuation_limit_reached" : "page_budget_exhausted",
      continuation_cursor_source: budgetCheckpoint.continuation_cursor_source,
      continuation_resume_strategy: budgetCheckpoint.continuation_resume_strategy,
      continuation_resume_result: budgetCheckpoint.continuation_resume_result,
      continuation_replay_duplicate_pages_detected: budgetCheckpoint.continuation_replay_duplicate_pages_detected,
      continuation_replay_duplicate_count: budgetCheckpoint.continuation_replay_duplicate_count,
      continuation_recovery_attempted: budgetCheckpoint.continuation_recovery_attempted,
      continuation_recovery_result: budgetCheckpoint.continuation_recovery_result,
      continuation_checkpoint_id: budgetCheckpoint.continuation_checkpoint_id,
      continuation_run_id: budgetCheckpoint.continuation_run_id,
      continuation_persisted_total: budgetCheckpoint.continuation_persisted_total,
      continuation_page_count: budgetCheckpoint.continuation_page_count,
      continuation_request_count: budgetCheckpoint.continuation_request_count,
      persisted_total_existing_before_run: accounting.repositoryExistingBeforeTotal,
      current_run_new_inserted_total: currentRunNewInsertedTotal,
      current_run_duplicate_existing_total: currentRunDuplicateExistingTotal,
      continuation_progress_total: currentRunNewInsertedTotal,
      remaining_estimate_from_expected: args.expectedProfileVideoCount == null ? null : Math.max(args.expectedProfileVideoCount - totalPersisted, 0),
      auto_continuation_enabled: "yes",
      auto_continuation_batches_run: autoContinuationBatchesRun,
      auto_continuation_reason: autoContinuationLimitReached ? "healthy_boundary_limit_reached" : "healthy_page_budget_boundary_continues_in_same_run",
      auto_continuation_limit_reached: autoContinuationLimitReached ? "yes" : "no",
      final_exhaustion_mode: finalExhaustionMode,
      user_action_count_required_for_full_scan: autoContinuationLimitReached ? 2 : 1,
      partial_scan_resumable: "yes",
      source_failure: "no",
      true_source_failure: "no",
      active_profile_post_source_healthy: "yes",
      final_gap_reason: "api_budget_exhausted_before_has_more_false",
      final_gap_classification: "resumable_api_budget_exhausted",
      scan_mode: "api_profile_post_pagination",
      scan_mode_visible_scroll_required: "no",
      expected_profile_video_count: args.expectedProfileVideoCount,
      scan_progress_phase_label: "Finalizing scan"
    }
    });
  }
}

async function runScanProfile22C11B(context: CanonicalScanProfile22C11BContext): Promise<void> {
  const { scanRunId, tabContext } = context;
  let terminalPersisted = false;
  let paginatedMainlineOwned = false;
  try {
    const cleanupDiagnostics = await cleanupObsoleteScanStorage22C11B(scanRunId);
    await persistCanonicalScanDiagnostics22C11B(scanRunId, "resolving_tab", { ...cleanupDiagnostics, tab_resolve_started_at: new Date().toISOString() });
    const tab = await resolveBackgroundScanProfileTab22C11B(tabContext, (stage, patch = {}) => canonicalScanDiagnostics22C11B(scanRunId, stage, patch));
    const tabId = tab.id;
    const profileUrl = tab.url ?? tabContext?.url ?? "";
    if (typeof tabId !== "number") throw new Error("scan_tab_not_found");

    await persistCanonicalScanDiagnostics22C11B(scanRunId, "ensuring_content_script", { content_script_ensure_status: "started" });
    const initialPing = await chrome.tabs.sendMessage(tabId, { type: "DOUYIN_SCANNER_PING", traceVersion: "22C-11B", scan_run_id: scanRunId } satisfies ExtensionMessage).catch((error) => ({ ok: false, error: error instanceof Error ? error.message : String(error) })) as ExtensionMessageResponse;
    if (!initialPing.ok && chrome.scripting?.executeScript) await chrome.scripting.executeScript({ target: { tabId }, files: ["contentScript.js"] }).catch(() => undefined);
    const ping = initialPing.ok ? initialPing : await chrome.tabs.sendMessage(tabId, { type: "DOUYIN_SCANNER_PING", traceVersion: "22C-11B", scan_run_id: scanRunId } satisfies ExtensionMessage).catch((error) => ({ ok: false, error: error instanceof Error ? error.message : String(error) })) as ExtensionMessageResponse;
    const handlers = Array.isArray(ping.content_script_supported_handlers) ? ping.content_script_supported_handlers : Array.isArray(ping.handlers) ? ping.handlers : [];
    await persistCanonicalScanDiagnostics22C11B(scanRunId, "ensuring_content_script", {
      content_script_ensure_status: ping.ok ? "ready" : "failed",
      content_script_ping: ping.ok ? "ok" : "failed",
      content_script_ping_result: ping.ok ? "ok" : "failed",
      content_script_ping_error: ping.error ?? null,
      content_script_supported_handlers: handlers,
      canonical_content_handler_registered: handlers.includes(CANONICAL_SCAN_PROFILE_MESSAGE_22C11B) ? "yes" : "no"
    });
    if (!ping.ok) {
      await failCanonicalScanProfile22C11B(scanRunId, "scan_content_script_unavailable", "ensuring_content_script", { content_script_ping_error: ping.error ?? null });
      terminalPersisted = true;
      return;
    }

    const liveProbeStatus = await chrome.tabs.sendMessage(tabId, { type: "DOUYIN_RUNTIME_AUTHORITY_SNAPSHOT_22C11B", traceVersion: "22C-11B", scan_run_id: scanRunId } satisfies ExtensionMessage).catch((error) => ({ ok: false, error: error instanceof Error ? error.message : String(error) })) as ExtensionMessageResponse;
    const liveProbeDiagnostics = liveProbeStatus.diagnostics && typeof liveProbeStatus.diagnostics === "object"
      ? liveProbeStatus.diagnostics as Record<string, unknown>
      : {};
    const networkProbeIdle = !liveProbeStatus.ok
      || liveProbeDiagnostics.network_stream_last_emit_at === "none"
      || liveProbeDiagnostics.network_stream_total_batches === 0
      || liveProbeDiagnostics.network_stream_total_targets === 0;
    await persistCanonicalScanDiagnostics22C11B(scanRunId, "network_probe_status", {
      network_probe_live_status_query: liveProbeStatus.ok ? "authority_snapshot_success" : "failed",
      network_probe_live_status_error: liveProbeStatus.ok ? null : liveProbeStatus.error ?? "network_probe_status_failed",
      network_probe_idle_fallback_required: networkProbeIdle ? "yes" : "no",
      ...sanitizeScannerDiagnostics22C11B(liveProbeDiagnostics)
    });

    const selfTest = await chrome.tabs.sendMessage(tabId, { type: CANONICAL_SCAN_PROFILE_PING_22C11B, traceVersion: "22C-11B", scan_run_id: scanRunId } satisfies ExtensionMessage).catch((error) => ({ ok: false, error: error instanceof Error ? error.message : String(error) })) as ExtensionMessageResponse;
    await persistCanonicalScanDiagnostics22C11B(scanRunId, "canonical_handler_self_test", {
      canonical_handler_self_test: selfTest.ok ? "success" : "failed",
      canonical_handler_self_test_response: selfTest.ok ? "ok" : selfTest.error ?? "failed",
      canonical_content_handler_registered: selfTest.ok ? "yes" : "no"
    });
    if (!selfTest.ok) {
      await failCanonicalScanProfile22C11B(scanRunId, "canonical_scan_handler_missing", "canonical_handler_self_test", { canonical_handler_self_test_response: selfTest.error ?? "failed" });
      terminalPersisted = true;
      return;
    }

    const probe = await sendBackgroundDomProbe22C11B(tabId, scanRunId, (stage, patch = {}) => canonicalScanDiagnostics22C11B(scanRunId, stage, patch)).catch((error) => ({ ok: false, error: error instanceof Error ? error.message : String(error), diagnostics: { profile_dom_probe_status: "failed" } })) as ExtensionMessageResponse;
    const probeDiagnostics = normalizeBackgroundDomProbeDiagnostics22C11B(probe, canonicalScanDiagnostics22C11B(scanRunId, "probing_dom", { dom_probe_role: networkProbeIdle ? "network_idle_fallback" : "diagnostic_only", network_probe_idle_fallback_triggered: networkProbeIdle ? "yes" : "no" }));
    await persistCanonicalScanDiagnostics22C11B(scanRunId, "probing_dom", probeDiagnostics);
    const expectedCountRaw = probeDiagnostics.expected_profile_video_count ?? probeDiagnostics.expectedProfileVideoCount;
    const expectedProfileVideoCount = typeof expectedCountRaw === "number" ? expectedCountRaw : typeof expectedCountRaw === "string" ? Number(expectedCountRaw) : null;

    const paginatedHandlerAvailable = handlers.includes(CANONICAL_SCAN_PROFILE_PAGE_MESSAGE_22C14B);
    if (paginatedHandlerAvailable) {
      paginatedMainlineOwned = true;
      const completed = await runPaginatedScanJob22C14B({ scanRunId, tabId, profileUrl, expectedProfileVideoCount: Number.isFinite(expectedProfileVideoCount) && expectedProfileVideoCount != null && expectedProfileVideoCount > 0 ? Math.round(expectedProfileVideoCount) : null });
      if (completed) {
        terminalPersisted = true;
        return;
      }
      const storedAfterPaginated = await chrome.storage.local.get(WHOLE_PROFILE_HARVEST_STATE_KEY).catch(() => ({} as Record<string, unknown>));
      const stateAfterPaginated = storedAfterPaginated?.[WHOLE_PROFILE_HARVEST_STATE_KEY] as WholeProfileHarvestState | undefined;
      const authorityAfterPaginated = stateAfterPaginated ? scanAuthorityDiagnostics22C14D(stateAfterPaginated) : {};
      const paginatedTerminal = stateAfterPaginated != null && scanStateIsTerminal22C14D(stateAfterPaginated, authorityAfterPaginated);
      if (paginatedTerminal) {
        terminalPersisted = true;
        return;
      }
      if (stateAfterPaginated?.scan_job?.status === "retry_wait" || stateAfterPaginated?.scan_job?.status === "failed") {
        terminalPersisted = true;
        return;
      }
      terminalPersisted = true;
      return;
    }

    const sentAt = new Date().toISOString();
    await persistCanonicalScanDiagnostics22C11B(scanRunId, "canonical_scanner_dispatch", {
      canonical_scan_message_sent: "yes",
      canonical_scan_message_sent_at: sentAt,
      canonical_scan_message_type: CANONICAL_SCAN_PROFILE_MESSAGE_22C11B,
      canonical_scanner_function: "collectActiveWorksGridTargets22C11B",
      expected_profile_video_count: Number.isFinite(expectedProfileVideoCount) && expectedProfileVideoCount != null && expectedProfileVideoCount > 0 ? Math.round(expectedProfileVideoCount) : null,
      queue_source_dispatch_mode: "minimal_active_works_grid_22C11B"
    });
    const response = await chrome.tabs.sendMessage(tabId, { type: CANONICAL_SCAN_PROFILE_MESSAGE_22C11B, scanRunId, scan_run_id: scanRunId, run_id: scanRunId, profileUrl, expected_profile_url: profileUrl, expectedProfileVideoCount: Number.isFinite(expectedProfileVideoCount) && expectedProfileVideoCount != null && expectedProfileVideoCount > 0 ? Math.round(expectedProfileVideoCount) : null, expected_profile_video_count: Number.isFinite(expectedProfileVideoCount) && expectedProfileVideoCount != null && expectedProfileVideoCount > 0 ? Math.round(expectedProfileVideoCount) : null, traceVersion: "22C-11B" } satisfies ExtensionMessage).catch((error) => ({ ok: false, error: error instanceof Error ? error.message : String(error), reason: "minimal_active_works_scanner_threw", verified_targets: [], verified_target_details: [], diagnostics: { canonical_scanner_error: error instanceof Error ? error.message : String(error) } })) as ExtensionMessageResponse | null | undefined;
    const responseDiagnostics = canonicalScannerResponseDiagnostics22C11B(response);
    if (!response || typeof response !== "object" || typeof response.ok !== "boolean") {
      await failCanonicalScanProfile22C11B(scanRunId, "canonical_scanner_completed_without_result", "canonical_result_parse", {
        ...responseDiagnostics,
        canonical_result_parse_status: "malformed",
        canonical_queue_adapter_invoked: "no",
        canonical_queue_adapter_skipped_reason: response ? "canonical_scanner_response_malformed" : "canonical_scanner_response_missing"
      });
      terminalPersisted = true;
      return;
    }
    const verifiedCount = Array.isArray(response.verified_targets) ? response.verified_targets.length : Array.isArray(response.verified_target_details) ? response.verified_target_details.length : 0;
    await persistCanonicalScanDiagnostics22C11B(scanRunId, "canonical_scanner_completed", {
      ...responseDiagnostics,
      ...sanitizeScannerDiagnostics22C11B(response.diagnostics),
      canonical_scanner_result: response.ok ? "success" : "failed",
      canonical_scanner_rounds: response.scan_rounds ?? 0,
      canonical_scanner_verified_target_count: verifiedCount,
      canonical_scanner_error: response.error ?? response.reason ?? null,
      canonical_result_parse_status: "parsed",
      canonical_queue_adapter_invoked: "no",
      canonical_queue_adapter_skipped_reason: response.ok ? null : "canonical_scanner_failed",
      canonical_scanner_completed_at: new Date().toISOString()
    });
    if (!response.ok) {
      await failCanonicalScanProfile22C11B(scanRunId, String(response.reason ?? response.error ?? "canonical_scanner_threw"), "canonical_scanner_completed", { ...sanitizeScannerDiagnostics22C11B(response.diagnostics), ...responseDiagnostics, canonical_result_parse_status: "parsed", canonical_queue_adapter_invoked: "no", canonical_queue_adapter_skipped_reason: "canonical_scanner_failed" });
      terminalPersisted = true;
      return;
    }
    const scannerFallbackDiagnostics = verifiedCount <= 0 ? { ...await readBackgroundScanDiagnostics22C11B(), ...sanitizeScannerDiagnostics22C11B(response.diagnostics) } : {};
    if (verifiedCount <= 0 && collectCanonicalFallbackCandidates22C14F(scannerFallbackDiagnostics, profileUrl).candidates.length <= 0) {
      await failCanonicalScanProfile22C11B(scanRunId, "canonical_scanner_zero_verified_targets", "canonical_scanner_completed", { ...sanitizeScannerDiagnostics22C11B(response.diagnostics), ...responseDiagnostics, canonical_result_parse_status: "parsed", canonical_queue_adapter_invoked: "no", canonical_queue_adapter_skipped_reason: "canonical_scanner_zero_verified_targets" });
      terminalPersisted = true;
      return;
    }
    await finalizeCanonicalScanSuccess22C11B(scanRunId, profileUrl, response, { tabId });
    terminalPersisted = true;
  } catch (error) {
    if (paginatedMainlineOwned) {
      terminalPersisted = true;
    } else {
      await failCanonicalScanProfile22C11B(scanRunId, error instanceof Error ? error.message : String(error), "canonical_exception");
      terminalPersisted = true;
    }
  } finally {
    if (!terminalPersisted && !paginatedMainlineOwned) {
      await failCanonicalScanProfile22C11B(scanRunId, "canonical_scanner_completed_without_result", "canonical_result_parse", {
        canonical_result_parse_status: "missing_terminal_result",
        canonical_queue_adapter_invoked: "no",
        canonical_queue_adapter_skipped_reason: "canonical_scanner_response_missing"
      }).catch(() => undefined);
    }
    if (activeBackgroundScanProfileRunId === scanRunId) activeBackgroundScanProfileRunId = null;
  }
}

async function resolveBackgroundScanProfileTab22C11B(tabContext: BackgroundScanProfileTabContext22C11B, runtimeDiagnostics: (stage: string, patch?: Record<string, unknown>) => Record<string, unknown>): Promise<{ id?: number; url?: string }> {
  const startedAt = new Date().toISOString();
  const candidates: Array<{ strategy: string; tab: { id?: number; url?: string; title?: string; status?: string } | null; error?: string | null }> = [];
  if (typeof tabContext?.tabId === "number") {
    const tab = await (chrome.tabs as unknown as { get(tabId: number): Promise<unknown> }).get(tabContext.tabId).catch((error: unknown) => { candidates.push({ strategy: "explicit_tab_id", tab: null, error: error instanceof Error ? error.message : String(error) }); return null; });
    if (tab) candidates.push({ strategy: "explicit_tab_id", tab: tab as { id?: number; url?: string; title?: string; status?: string }, error: null });
  }
  for (const query of [{ strategy: "active_current_window", args: { active: true, currentWindow: true } }, { strategy: "active_last_focused_window", args: { active: true, lastFocusedWindow: true } }, { strategy: "all_douyin_tabs", args: { url: ["*://*.douyin.com/*"] } }]) {
    const [tab] = await (chrome.tabs.query as unknown as (args: unknown) => Promise<Array<{ id?: number; url?: string; title?: string; status?: string }>>)(query.args).catch(() => [] as Array<{ id?: number; url?: string; title?: string; status?: string }>);
    candidates.push({ strategy: query.strategy, tab: tab as { id?: number; url?: string; title?: string; status?: string } | undefined ?? null, error: null });
  }
  const found = candidates.find((entry) => entry.tab?.id && isSupportedDouyinUrl(entry.tab.url ?? ""));
  if (!found?.tab?.id) {
    const anyTab = candidates.find((entry) => entry.tab?.id)?.tab ?? null;
    const reason = anyTab ? "scan_tab_not_douyin" : "scan_tab_not_found";
    await persistBackgroundScanDiagnostics("resolving_tab", runtimeDiagnostics("resolving_tab", { tab_resolve_started_at: startedAt, tab_resolve_result: reason, tab_resolve_strategy: candidates.map((c) => c.strategy).join("->"), tab_url: anyTab?.url ?? null, tab_is_douyin: false, tab_resolve_error: candidates.find((c) => c.error)?.error ?? reason }));
    throw new Error(reason);
  }
  await persistBackgroundScanDiagnostics("resolving_tab", runtimeDiagnostics("resolving_tab", { tab_resolve_started_at: startedAt, tab_resolve_result: "success", tab_resolve_strategy: found.strategy, tab_id: found.tab.id, tab_url: found.tab.url ?? null, tab_title: found.tab.title ?? null, tab_status: found.tab.status ?? null, tab_is_douyin: true, tab_resolved_at: new Date().toISOString() }));
  return found.tab;
}

async function readBackgroundScanDiagnostics22C11B(): Promise<Record<string, unknown>> {
  const stored = await chrome.storage.local.get(WHOLE_PROFILE_HARVEST_STATE_KEY);
  const state = stored[WHOLE_PROFILE_HARVEST_STATE_KEY] as { debug?: { last_request_summary?: unknown } } | undefined;
  return state?.debug?.last_request_summary && typeof state.debug.last_request_summary === "object" ? state.debug.last_request_summary as Record<string, unknown> : {};
}

function scanStageEvent22C11B(stage: string, diagnostics: Record<string, unknown>): string {
  if (stage === "resolving_tab") return diagnostics.tab_resolve_result === "success" ? "resolving_tab_success" : "resolving_tab_started";
  if (stage === "ensuring_content_script") return diagnostics.content_script_ping_result === "ok" ? "content_script_ping_ok" : diagnostics.content_script_ensure_status === "ready" ? "content_script_ready" : "content_script_ensure_started";
  if (stage === "probing_dom") return diagnostics.profile_dom_probe_status === "completed" ? "dom_probe_completed" : "dom_probe_started";
  if (stage === "verified") return "scan_success_finalized";
  return stage;
}

async function persistBackgroundScanDiagnostics(stage: string, diagnostics: Record<string, unknown>): Promise<void> {
  const at = new Date().toISOString();
  const stored = await chrome.storage.local.get(WHOLE_PROFILE_HARVEST_STATE_KEY);
  const state = stored[WHOLE_PROFILE_HARVEST_STATE_KEY] as { debug?: { last_request_summary?: unknown; last_response_summary?: unknown }; phase?: unknown; [key: string]: unknown } | undefined;
  if (!state) return;
  const current = state.debug?.last_request_summary && typeof state.debug.last_request_summary === "object" ? state.debug.last_request_summary as Record<string, unknown> : {};
  const previousStage = typeof current.scan_stage_current === "string" ? current.scan_stage_current : typeof state.phase === "string" ? state.phase : null;
  const history = Array.isArray(current.scan_stage_history) ? current.scan_stage_history : [];
  const event = scanStageEvent22C11B(stage, diagnostics);
  const merged = { ...current, ...diagnostics, scan_watchdog_stage: stage, scan_stage_previous: previousStage, scan_stage_current: stage, scan_stage_updated_at: at, scan_stage_history: [...history, { stage, event, at }].slice(-40), updated_at: at };
  await chrome.storage.local.set({ [WHOLE_PROFILE_HARVEST_STATE_KEY]: { ...state, phase: stage, debug: { ...(state.debug ?? {}), last_request_summary: merged, last_response_summary: merged }, updated_at: at } });
}

export function __testDerivePostProbeProductiveGate22C11B(probeResult: unknown, diagnostics: Record<string, unknown> = {}): PostProbeProductiveGateDerivation22C11B {
  return derivePostProbeProductiveGate22C11B(probeResult, diagnostics);
}

export function __testPaginatedScanAccountingDiagnostics22C14B(accounting: PaginatedScanAccounting22C14B, expectedCount: number | null, totalPersisted: number): Record<string, unknown> {
  return paginatedScanAccountingDiagnostics22C14B(accounting, expectedCount, totalPersisted);
}

export function __testScanHealthVerdictDiagnostics22C14R(source: Record<string, unknown>): Record<string, unknown> {
  return scanHealthVerdictDiagnostics22C14R(source);
}

export function __testCountSemanticsDiagnostics22C14Q(input: CountSemanticsDiagnosticsInput22C14Q): Record<string, unknown> {
  return countSemanticsDiagnostics22C14Q(input);
}

export function __testDeriveRepositoryOverDisplayedDiagnostics22C14Q(records: ProfileTargetRecord[], options: RepositoryOverDisplayedDiagnosticsOptions22C14Q): Record<string, unknown> {
  return deriveRepositoryOverDisplayedDiagnostics22C14Q(records, options);
}

export function __testMergeOverDisplayedDiagnosticsPreferActiveTail22C14Q(activeDiagnostics: Record<string, unknown>, repositoryDiagnostics: Record<string, unknown>): Record<string, unknown> {
  return mergeOverDisplayedDiagnosticsPreferActiveTail22C14Q(activeDiagnostics, repositoryDiagnostics);
}

export function __testNormalizeDouyinProfileIdentity22C14S(value: unknown): DouyinProfileIdentityNormalization22C14S {
  return normalizeDouyinProfileIdentity22C14S(value);
}

async function sendBackgroundDomProbe22C11B(tabId: number, scanRunId: string, runtimeDiagnostics: (stage: string, patch?: Record<string, unknown>) => Record<string, unknown>): Promise<ExtensionMessageResponse> {
  const message = { type: "DOUYIN_PROFILE_DOM_PROBE_22C11B", traceVersion: SCAN_PROFILE_BACKGROUND_TRACE_VERSION, scan_run_id: scanRunId } satisfies ExtensionMessage;
  const timeout = new Promise<ExtensionMessageResponse>((resolve) => setTimeout(() => resolve({ ok: false, error: "scan_dom_probe_timeout", diagnostics: { dom_probe_message_result: "timeout", profile_dom_probe_message: "timeout", profile_dom_probe_fallback_attempted: false } }), 10_000));
  const response = await Promise.race([
    chrome.tabs.sendMessage(tabId, message).catch((error) => ({ ok: false, error: error instanceof Error ? error.message : String(error), diagnostics: { dom_probe_message_result: "failed", profile_dom_probe_message: "failed" } })),
    timeout
  ]) as ExtensionMessageResponse;
  const rawError = String(response.error ?? "");
  const missingHandler = !response.ok && /unknown|unsupported/i.test(rawError);
  const connectionFailure = !response.ok && /receiving end|message port closed/i.test(rawError);
  if (!missingHandler || connectionFailure) return response;
  if (!chrome.scripting?.executeScript) {
    return { ok: false, error: "scan_dom_probe_handler_missing", diagnostics: runtimeDiagnostics("probing_dom", { dom_probe_message_result: "handler_missing", profile_dom_probe_message: "handler_missing", profile_dom_probe_fallback_attempted: true, profile_dom_probe_fallback_result: "unavailable", dom_probe_fallback_execute_script_attempted: true, dom_probe_fallback_execute_script_result: "unavailable", raw_scan_error: response.error ?? null }) };
  }
  try {
    const fallback = await chrome.scripting.executeScript({ target: { tabId }, func: inlineProfileDomProbe22C11B });
    return { ok: true, profile_dom_probe: fallback?.[0]?.result as Record<string, unknown>, diagnostics: runtimeDiagnostics("probing_dom", { dom_probe_message_result: "handler_missing", profile_dom_probe_message: "fallback_execute_script", profile_dom_probe_fallback_attempted: true, profile_dom_probe_fallback_result: "success", dom_probe_fallback_execute_script_attempted: true, dom_probe_fallback_execute_script_result: "success" }) };
  } catch (error) {
    return { ok: false, error: "scan_dom_probe_execute_script_failed", diagnostics: runtimeDiagnostics("probing_dom", { dom_probe_message_result: "handler_missing", profile_dom_probe_message: "fallback_execute_script_failed", profile_dom_probe_fallback_attempted: true, profile_dom_probe_fallback_result: "failed", profile_dom_probe_fallback_error: error instanceof Error ? error.message : String(error), dom_probe_fallback_execute_script_attempted: true, dom_probe_fallback_execute_script_result: "failed", dom_probe_fallback_error: error instanceof Error ? error.message : String(error) }) };
  }
}

function normalizeBackgroundDomProbeDiagnostics22C11B(response: ExtensionMessageResponse, base: Record<string, unknown>): Record<string, unknown> {
  const probe = response.profile_dom_probe && typeof response.profile_dom_probe === "object" ? response.profile_dom_probe as Record<string, unknown> : null;
  const rawError = String(response.error ?? "");
  const missingHandler = !response.ok && /unknown|unsupported/i.test(rawError);
  const specific = response.ok && probe ? null : response.error === "scan_dom_probe_timeout" ? "scan_dom_probe_timeout" : response.error === "scan_dom_probe_execute_script_failed" ? "scan_dom_probe_execute_script_failed" : missingHandler ? "scan_dom_probe_handler_missing" : response.error ? "scan_dom_probe_message_failed" : "scan_dom_probe_malformed_response";
  const videoAnchorCount = Number(probe?.videoAnchorCount ?? 0);
  const modalIdLinkCount = Number(probe?.modalIdLinkCount ?? 0);
  const awemeIdCount = Number(probe?.awemeIdCount ?? 0);
  const gridCardCandidateCount = Number(probe?.gridCardCandidateCount ?? 0);
  const expectedRaw = probe?.expectedProfileVideoCount;
  const expectedProfileVideoCount = typeof expectedRaw === "number" ? expectedRaw : typeof expectedRaw === "string" ? Number(expectedRaw) : null;
  return { ...base, ...(response.diagnostics ?? {}), ...(probe ?? {}), profile_dom_probe: probe, profile_dom_probe_status: specific ? (specific === "scan_dom_probe_timeout" ? "timeout" : "failed") : "completed", profile_dom_probe_message: response.ok ? "ok" : specific, profile_dom_probe_completed_at: new Date().toISOString(), profile_dom_probe_message_type: "DOUYIN_PROFILE_DOM_PROBE_22C11B", profile_dom_probe_response_received: response.error === "scan_dom_probe_timeout" ? "no" : "yes", profile_dom_probe_fallback_attempted: Boolean(response.diagnostics?.profile_dom_probe_fallback_attempted ?? response.diagnostics?.dom_probe_fallback_execute_script_attempted ?? false), profile_dom_probe_fallback_result: response.diagnostics?.profile_dom_probe_fallback_result ?? response.diagnostics?.dom_probe_fallback_execute_script_result ?? "not_attempted", dom_probe_message_result: response.ok ? "ok" : (response.diagnostics?.dom_probe_message_result ?? "failed"), profile_grid_ready: Boolean(probe && (probe.profileGridFound || videoAnchorCount > 0 || modalIdLinkCount > 0 || awemeIdCount > 0 || gridCardCandidateCount > 0 || probe.emptyProfileDetected)), video_anchor_count: videoAnchorCount, modal_id_link_count: modalIdLinkCount, aweme_id_count: awemeIdCount, grid_card_candidate_count: gridCardCandidateCount, scroll_container_found: probe?.scrollContainerFound ?? null, expected_profile_video_count: Number.isFinite(expectedProfileVideoCount) && expectedProfileVideoCount != null && expectedProfileVideoCount > 0 ? Math.round(expectedProfileVideoCount) : null, expected_profile_video_count_raw_text: probe?.expectedProfileVideoCountRawText ?? null, expected_profile_video_count_selector: probe?.expectedProfileVideoCountSelector ?? null, expected_profile_video_count_parse_ok: probe?.expectedProfileVideoCountParseOk === true ? "yes" : "no", expected_profile_video_count_parse_error: probe?.expectedProfileVideoCountParseError ?? null, specific_scan_error: specific, scan_failure_stage: specific ? "probing_dom" : null, raw_scan_error_safe: response.error ?? null, raw_scan_error: response.error ?? null, raw_scan_error_stack_safe: null, final_visible_error: specific, scan_no_round_reason: probe && !(videoAnchorCount > 0 || modalIdLinkCount > 0 || awemeIdCount > 0 || gridCardCandidateCount > 0 || probe.profileGridFound || probe.emptyProfileDetected) ? "profile_grid_not_ready_timeout" : null };
}

function inlineProfileDomProbe22C11B() {
  const hrefs = Array.from(document.querySelectorAll("a[href]")).map((link) => (link as HTMLAnchorElement).href).filter(Boolean);
  const awemeIds = Array.from(new Set(hrefs.join("\n").match(/\d{10,}/g) ?? []));
  const videoAnchors = hrefs.filter((href) => /\/video\//.test(href));
  const modalLinks = hrefs.filter((href) => /modal_id=/.test(href));
  const gridCardSelectorHits = ["[data-e2e*=user-post]", "[data-e2e*=user-video]", "a[href*=\"/video/\"]"].map((selector) => ({ selector, count: document.querySelectorAll(selector).length }));
  const bodyText = document.body?.innerText ?? "";
  return { traceVersion: "22C-11B", url: location.href, pathname: location.pathname, documentReadyState: document.readyState, pageTypeDetected: /\/user\//.test(location.pathname) ? "profile" : "unknown", profileContainerFound: Boolean(document.querySelector("main, [data-e2e*=user]")), profileGridFound: gridCardSelectorHits.some((hit) => hit.count > 0), profileGridSelector: gridCardSelectorHits.find((hit) => hit.count > 0)?.selector ?? null, videoAnchorCount: videoAnchors.length, videoAnchors: videoAnchors.slice(0, 500), videoAnchorsSample: videoAnchors.slice(0, 5), modalIdLinkCount: modalLinks.length, modalIdLinks: modalLinks.slice(0, 500), modalIdLinksSample: modalLinks.slice(0, 5), awemeIdCount: awemeIds.length, awemeIds: awemeIds.slice(0, 500), awemeIdsSample: awemeIds.slice(0, 10), gridCardCandidateCount: gridCardSelectorHits.reduce((sum, hit) => sum + hit.count, 0), gridCards: hrefs.slice(0, 500), gridCardSelectorHits, scrollContainerFound: Boolean(document.scrollingElement), scrollContainerSelector: document.scrollingElement ? "document.scrollingElement" : null, emptyProfileDetected: /empty/i.test(bodyText), loginWallDetected: /login/i.test(bodyText), captchaDetected: /captcha/i.test(bodyText), checkpointDetected: /checkpoint/i.test(bodyText), error: null };
}

function senderTabId(sender: unknown): number | null {
  const tab = sender && typeof sender === "object" ? (sender as { tab?: { id?: number } }).tab : null;
  return typeof tab?.id === "number" ? tab.id : null;
}

function isSupportedDouyinUrl(value: string): boolean {
  try {
    const url = new URL(value);
    return /(^|\.)douyin\.com$/.test(url.hostname) || /(^|\.)iesdouyin\.com$/.test(url.hostname);
  } catch {
    return false;
  }
}

function isLikelyAwemeResponse(url: string): boolean {
  return /aweme|post|feed|detail|modal|video/i.test(url);
}

export async function sendToActiveTab(message: ExtensionMessage): Promise<ExtensionMessageResponse> {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab?.id) return { ok: false, error: "No active tab found." };
  try {
    return await chrome.tabs.sendMessage(tab.id, message);
  } catch (error) {
    return { ok: false, error: error instanceof Error ? error.message : "Unable to reach content script. Open a Douyin tab and try again." };
  }
}

async function readWebDashboardAuthTokenFromOpenTabs22C13A(): Promise<{ webTabOpen: boolean; tab_id: number | null; token: string | null }> {
  const tabs = await chrome.tabs.query({ url: ["http://localhost/*", "http://127.0.0.1/*"] }).catch(() => [] as Array<{ id?: number; url?: string }>);
  for (const tab of tabs) {
    if (typeof tab.id !== "number") continue;
    const results = await chrome.scripting?.executeScript?.({
      target: { tabId: tab.id },
      func: (storageKey: string) => window.localStorage.getItem(storageKey),
      args: [WEB_API_AUTH_TOKEN_STORAGE_KEY]
    }).catch(() => null);
    const raw = Array.isArray(results) ? results[0]?.result : null;
    const token = typeof raw === "string" && raw.trim() ? raw.trim() : null;
    return { webTabOpen: true, tab_id: tab.id, token };
  }
  return { webTabOpen: false, tab_id: null, token: null };
}

async function syncApiAuthTokenFromWebTabs22C13A(): Promise<{ token: string | null; source: string; tab_id: number | null }> {
  const existing = await readStoredApiAuthToken();
  const webTab = await readWebDashboardAuthTokenFromOpenTabs22C13A();
  const reconciled = reconcileExtensionAuthWithWebTabToken(existing, webTab.webTabOpen, webTab.token);
  const at = new Date().toISOString();
  if (reconciled.clearedStaleExtensionToken || (webTab.webTabOpen && !reconciled.token)) {
    await chrome.storage.local.set({
      [EXTENSION_AUTH_TOKEN_STORAGE_KEY]: "",
      apiAuthRequired: true,
      apiAuthTokenSyncedAt: at,
      apiAuthTokenSource: reconciled.source,
      apiAuthLastPrincipalStatus: "web_tab_logged_out",
      apiAuthLastPrincipalCheckedAt: at
    });
    return { token: null, source: reconciled.source, tab_id: webTab.tab_id };
  }
  if (reconciled.token && reconciled.source === "background_web_local_storage_22C13A") {
    await chrome.storage.local.set({
      [EXTENSION_AUTH_TOKEN_STORAGE_KEY]: reconciled.token,
      apiAuthTokenSyncedAt: at,
      apiAuthTokenSource: reconciled.source,
      apiAuthRequired: false
    });
    return { token: reconciled.token, source: reconciled.source, tab_id: webTab.tab_id };
  }
  if (reconciled.token) return { token: reconciled.token, source: reconciled.source, tab_id: webTab.tab_id };
  return { token: null, source: reconciled.source, tab_id: webTab.tab_id };
}

function firstString22C13A(value: unknown, ...keys: string[]): string | null {
  const record = value && typeof value === "object" ? value as Record<string, unknown> : null;
  if (!record) return null;
  for (const key of keys) {
    const candidate = record[key];
    if (typeof candidate === "string" && candidate.trim()) return candidate.trim();
  }
  return null;
}

async function syncAuthSession22C13A(baseUrlInput: string | null): Promise<ExtensionMessageResponse> {
  const baseUrl = (baseUrlInput || "http://127.0.0.1:8000").replace(/\/+$/, "");
  const synced = await syncApiAuthTokenFromWebTabs22C13A();
  if (!synced.token) {
    await chrome.storage.local.set({ apiAuthRequired: true, apiAuthLastPrincipalStatus: "missing_token", apiAuthLastPrincipalCheckedAt: new Date().toISOString() });
    return { ok: false, error: "api_auth_token_missing", diagnostics: { auth_session_sync_version: AUTH_SESSION_SYNC_VERSION_22C13A, auth_token_source: synced.source, get_current_principal_verified: "no" } };
  }
  const principalProbe = await postToBackend(await withStoredAuthHeader({ base_url: baseUrl, path: "/capture-inbox/sessions?limit=200", method: "GET", keepalive: false }));
  const at = new Date().toISOString();
  const principalVerified = principalProbe.ok;
  const body = principalProbe.body && typeof principalProbe.body === "object" ? principalProbe.body as Record<string, unknown> : {};
  const sessions = Array.isArray(body.sessions) ? body.sessions : [];
  const session = sessions.find((entry) => firstString22C13A(entry, "id", "session_id", "capture_session_id", "capture_id")) ?? null;
  const sessionId = firstString22C13A(session, "id", "session_id", "capture_session_id", "capture_id");
  const stored = await chrome.storage.local.get(WHOLE_PROFILE_HARVEST_STATE_KEY).catch(() => ({} as Record<string, unknown>));
  const state = (stored as Record<string, unknown>)[WHOLE_PROFILE_HARVEST_STATE_KEY] as WholeProfileHarvestState | undefined;
  if (state && principalVerified && sessionId) {
    const next: WholeProfileHarvestState = appendWholeProfileTrace({
      ...state,
      capture_session_id: state.capture_session_id ?? sessionId,
      harvest: {
        ...state.harvest,
        capture_session_status: "ready",
        backend: {
          ...state.harvest.backend,
          capture_session: {
            ...state.harvest.backend.capture_session,
            status: "ready",
            session_id: state.harvest.backend.capture_session.session_id ?? sessionId,
            created: state.harvest.backend.capture_session.created ?? false,
            request_summary: { stage: "auth_session_sync_22C13A", method: "GET", url: "/capture-inbox/sessions?limit=200" },
            response_summary: { status: principalProbe.status_code, principal_verified: true, session_id: sessionId, session_count: sessions.length },
            error_code: null,
            error_message: null,
            updated_at: at
          }
        }
      },
      last_error: null,
      updated_at: at
    }, "auth_session_sync.22C13A", "Verified backend principal and synced Capture Inbox session.", { auth_session_sync_version: AUTH_SESSION_SYNC_VERSION_22C13A, capture_session_id: sessionId, get_current_principal_verified: "yes" }, at);
    await safeSetScannerStorage22C11B({ [WHOLE_PROFILE_HARVEST_STATE_KEY]: next }, { stage: "auth_session_sync_22C13A" });
  }
  await chrome.storage.local.set({ apiAuthRequired: !principalVerified, apiAuthLastPrincipalStatus: principalVerified ? "verified" : "failed", apiAuthLastPrincipalCheckedAt: at });
  const response: ExtensionMessageResponse = {
    ok: principalVerified,
    backend_post: principalProbe,
    diagnostics: {
      auth_session_sync_version: AUTH_SESSION_SYNC_VERSION_22C13A,
      auth_token_source: synced.source,
      auth_token_synced_from_tab_id: synced.tab_id,
      get_current_principal_verified: principalVerified ? "yes" : "no",
      protected_route_used_for_principal: "/capture-inbox/sessions?limit=200",
      capture_session_id_synced: sessionId,
      capture_session_count: sessions.length
    }
  };
  if (!principalVerified) response.error = principalProbe.error_message || "get_current_principal verification failed";
  return response;
}

async function readStoredApiAuthToken(): Promise<string | null> {
  const stored = await chrome.storage.local.get(EXTENSION_AUTH_TOKEN_STORAGE_KEY).catch(() => ({} as Record<string, unknown>));
  const token = (stored as Record<string, unknown>)[EXTENSION_AUTH_TOKEN_STORAGE_KEY];
  return typeof token === "string" && token.trim() ? token.trim() : null;
}

async function withStoredAuthHeader(request: ExtensionBackendPostRequest): Promise<ExtensionBackendPostRequest> {
  const existingHeaders = request.headers ?? {};
  if (existingHeaders.Authorization || existingHeaders.authorization) return request;
  const token = await readStoredApiAuthToken();
  if (!token) return request;
  return {
    ...request,
    headers: {
      ...existingHeaders,
      Authorization: `Bearer ${token}`
    }
  };
}

export async function postToBackend(request: ExtensionBackendPostRequest): Promise<ExtensionBackendPostResponse> {
  return postBackendJson(request);
}

// ---------------------------------------------------------------------------
// Hybrid Network Cache Runner — background message handler
// ---------------------------------------------------------------------------
//
// The popup dispatches DOUYIN_HYBRID_NETWORK_CACHE_RUNNER to the background
// when the hybrid_network_cache_mode feature flag is enabled. Without this
// listener the message is silently dropped, the collect job never starts,
// the lock expires, and the popup shows a stale "Collecting videos..." state.
//
// This handler:
//   1. Builds a background-appropriate WholeProfileHarvestRuntime.
//   2. Calls runBatchCollectHybridNetworkCacheMode (already implemented in
//      controller.ts as Phase 4.4c).
//   3. Returns { ok: true } so the popup's ack-poll loop can proceed.

async function fetchDetailEvidenceChunkFromTab(
  tabId: number,
  discoveries: Array<{ aweme_id: string; source_url: string }>
): Promise<NetworkVideoMetadata[]> {
  if (!Array.isArray(discoveries) || discoveries.length === 0) return [];
  const fetchTargets = discoveries.map((discovery) => ({
    aweme_id: discovery.aweme_id,
    urls: buildHybridDetailFetchUrls(discovery.aweme_id, discovery.source_url)
  }));
  const results = await chrome.scripting.executeScript({
    target: { tabId },
    func: async (items: Array<{ aweme_id: string; urls: string[] }>) => {
      const CONCURRENCY = 5;
      const TIMEOUT_MS = 8000;
      const out: Array<{ aweme_id: string; ok: boolean; body: string; content_type: string }> = [];
      let cursor = 0;
      async function worker(): Promise<void> {
        while (cursor < items.length) {
          const current = items[cursor];
          cursor += 1;
          if (!current) return;
          let ok = false;
          let body = "";
          let content_type = "";
          for (const url of current.urls) {
            const controller = new AbortController();
            const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);
            try {
              const resp = await fetch(url, {
                credentials: "include",
                redirect: "follow",
                signal: controller.signal
              });
              const text = resp.ok ? await resp.text() : "";
              if (resp.ok && text.trim()) {
                ok = true;
                body = text;
                content_type = resp.headers.get("content-type") || "";
                break;
              }
            } catch {
              // try next URL
            } finally {
              clearTimeout(timer);
            }
          }
          out.push({
            aweme_id: current.aweme_id,
            ok,
            body,
            content_type
          });
        }
      }
      await Promise.all(
        Array.from({ length: Math.min(CONCURRENCY, items.length) }, () => worker())
      );
      return out;
    },
    args: [fetchTargets]
  });
  const fetched = (Array.isArray(results) && results[0]?.result ? results[0].result : []) as Array<{
    aweme_id: string;
    ok: boolean;
    body: string;
    content_type: string;
  }>;
  const items: NetworkVideoMetadata[] = [];
  for (const entry of fetched) {
    if (!entry?.ok || !entry.body) continue;
    const selected = selectBestDetailCandidate(
      extractExactDetailCandidates(entry.body, entry.content_type, entry.aweme_id),
      entry.aweme_id
    );
    if (selected) items.push(selected);
  }
  return items;
}

async function ensureDouyinTabForProfileHybridCollect(profileUrl: string): Promise<{
  id: number;
  url: string | null;
  navigated: boolean;
  created: boolean;
}> {
  return ensureDouyinTabForHybridTailGapCollect(profileUrl, async (url) => {
    const tab = await resolveDouyinTabRecordForBackground(null, url);
    return { id: tab.id ?? null, url: tab.url ?? null };
  });
}

function buildBackgroundHybridRuntime(): WholeProfileHarvestRuntime {
  const storage = {
    get: async (key: string): Promise<Record<string, unknown>> => {
      return chrome.storage.local.get(key);
    },
    set: async (items: Record<string, unknown>): Promise<void> => {
      await chrome.storage.local.set(items);
    }
  };
  return {
    storage,
    now: () => new Date().toISOString(),
    getActiveTab: async () => {
      const tab = await resolveDouyinTabRecordForBackground();
      return tab ?? { id: null, url: null };
    },
    resolveDouyinTabForProfile: async (profileUrl: string) => {
      const tab = await resolveDouyinTabRecordForBackground(null, profileUrl);
      return { id: tab.id ?? null, url: tab.url ?? null };
    },
    ensureDouyinTabForProfile: async (profileUrl: string) => ensureDouyinTabForProfileHybridCollect(profileUrl),
    readDomTailReconcileProbeFromTab: async (tabId: number, profileUrl: string, options?: { forceDomScroll?: boolean; allowCappedDomScroll?: boolean }) =>
      readDomTailReconcileProbeFromHybridTab(tabId, profileUrl, options ?? {}),
    readNetworkCacheFromTab: async (tabId: number): Promise<unknown[]> => {
      try {
        const results = await chrome.scripting.executeScript({
          target: { tabId },
          func: () => {
            const cache = (window as unknown as { __REUP_DOUYIN_NETWORK_CACHE__?: unknown }).__REUP_DOUYIN_NETWORK_CACHE__;
            if (!cache) return [];
            if (Array.isArray(cache)) return cache;
            if (typeof cache === "object" && cache !== null) {
              const arr = Object.values(cache);
              return arr.filter((v): v is Record<string, unknown> => v != null && typeof v === "object");
            }
            return [];
          }
        });
        const result = Array.isArray(results) && results[0]?.result ? results[0].result : [];
        return Array.isArray(result) ? result : [];
      } catch {
        return [];
      }
    },
    readPassiveProbeDiagnosticsFromTab: async (tabId: number): Promise<Record<string, unknown>> => {
      try {
        const response = await chrome.tabs.sendMessage(tabId, { type: "DOUYIN_RUNTIME_AUTHORITY_SNAPSHOT_22C11B" } satisfies ExtensionMessage) as ExtensionMessageResponse;
        if (!response?.ok) return {};
        if (response.runtime_authority_snapshot && typeof response.runtime_authority_snapshot === "object") {
          return response.runtime_authority_snapshot as Record<string, unknown>;
        }
        return response?.diagnostics && typeof response.diagnostics === "object"
          ? response.diagnostics as Record<string, unknown>
          : {};
      } catch {
        return {};
      }
    },
    hydrateDetailEvidenceFromTab: async (
      tabId: number,
      discoveries: Array<{ aweme_id: string; source_url: string }>
    ): Promise<NetworkVideoMetadata[]> => {
      if (!Array.isArray(discoveries) || discoveries.length === 0) return [];
      try {
        const chunks = chunkDetailHydrationDiscoveries(discoveries);
        const items: NetworkVideoMetadata[] = [];
        const parallel = Math.max(1, HYBRID_DETAIL_HYDRATION_PARALLEL_CHUNKS);
        for (let index = 0; index < chunks.length; index += parallel) {
          const batch = chunks.slice(index, index + parallel);
          const fetchedBatch = await Promise.all(
            batch.map((chunk) => fetchDetailEvidenceChunkFromTab(tabId, chunk).catch(() => [] as NetworkVideoMetadata[]))
          );
          for (const fetched of fetchedBatch) items.push(...fetched);
        }
        return items;
      } catch {
        return [];
      }
    },
    fetchProfilePostPageFromTab: async (
      tabId: number,
      profileUrl: string,
      cursor: string | number | null,
      pageIndex: number
    ) => fetchProfilePostPageFromHybridTab(tabId, profileUrl, cursor, pageIndex),
    flushCanonicalHarvestPayload: async (payload: unknown, headers: Record<string, string>): Promise<WholeProfileBackendFlushResult> => {
      try {
        const baseUrl = await readBackgroundApiBaseUrl22C11B();
        const backendPost = await postToBackend(await withStoredAuthHeader({
          base_url: baseUrl,
          path: "/douyin-extension/full-modal-harvest",
          method: "POST",
          payload,
          headers,
          keepalive: false
        } as ExtensionBackendPostRequest));
        if (!backendPost.ok) {
          return {
            ok: false,
            status: backendPost.status_code ?? undefined,
            error_code: backendPost.error_code ?? "backend_flush_failed",
            error_message: backendPost.error_message ?? "Backend flush failed.",
            raw: backendPost
          } as WholeProfileBackendFlushResult;
        }
        const body = backendPost.body ?? {};
        return { ok: true, ...(body as Record<string, unknown>), raw: body, status: backendPost.status_code ?? undefined } as WholeProfileBackendFlushResult;
      } catch (err) {
        return {
          ok: false,
          error_code: "background_flush_threw",
          error_message: err instanceof Error ? err.message : String(err)
        } as WholeProfileBackendFlushResult;
      }
    },
    verifyCaptureInboxItem: async (_captureSessionId: string, _awemeId: string): Promise<{ ok: boolean; matched_by?: string }> => {
      return { ok: false };
    },
    listCaptureSessionItems: async (captureSessionId: string): Promise<WholeProfileCaptureSessionItemsResult> => {
      try {
        const baseUrl = await readBackgroundApiBaseUrl22C11B();
        const response = await postToBackend(await withStoredAuthHeader({
          base_url: baseUrl,
          path: `/douyin-extension/capture-sessions/${encodeURIComponent(captureSessionId)}/items`,
          method: "GET",
          keepalive: false
        } as ExtensionBackendPostRequest));
        const body = response.body as Record<string, unknown> | null;
        return {
          ok: response.ok,
          status: response.status_code ?? null,
          error_code: response.error_code ?? null,
          error_message: response.error_message ?? null,
          session_id: captureSessionId,
          items_count: Array.isArray(body?.items) ? body!.items!.length : 0,
          items: Array.isArray(body?.items) ? body!.items! as Array<Record<string, unknown>> : [],
          raw: body
        } as WholeProfileCaptureSessionItemsResult;
      } catch (err) {
        return {
          ok: false,
          error_code: "list_capture_session_items_threw",
          error_message: err instanceof Error ? err.message : String(err)
        } as WholeProfileCaptureSessionItemsResult;
      }
    },
    listCaptureSessions: async (): Promise<{ ok: boolean; status?: number | null; error_code?: string | null; error_message?: string | null; total_count?: number; sessions?: Array<Record<string, unknown>>; raw?: unknown }> => {
      try {
        const baseUrl = await readBackgroundApiBaseUrl22C11B();
        const response = await postToBackend(await withStoredAuthHeader({
          base_url: baseUrl,
          path: "/capture-inbox/sessions",
          method: "GET",
          keepalive: false
        } as ExtensionBackendPostRequest));
        const body = response.body as Record<string, unknown> | null;
        return {
          ok: response.ok,
          status: response.status_code ?? null,
          error_code: response.error_code ?? null,
          error_message: response.error_message ?? null,
          total_count: typeof body?.total_count === "number" ? body.total_count : Array.isArray(body?.sessions) ? body!.sessions!.length : 0,
          sessions: Array.isArray(body?.sessions) ? body!.sessions! as Array<Record<string, unknown>> : [],
          raw: body
        };
      } catch (err) {
        return {
          ok: false,
          error_code: "list_capture_sessions_threw",
          error_message: err instanceof Error ? err.message : String(err),
          total_count: 0,
          sessions: []
        };
      }
    },
    createCanonicalHarvestSession: async (request: Record<string, unknown>): Promise<{ ok: boolean; session_id?: string; created?: boolean; status?: number | null; url?: string | null; body?: unknown | null; error_code?: string | null; error_message?: string | null; network_error?: boolean }> => {
      try {
        const baseUrl = await readBackgroundApiBaseUrl22C11B();
        const response = await postToBackend(await withStoredAuthHeader({
          base_url: baseUrl,
          path: "/douyin-extension/capture-session",
          method: "POST",
          payload: request,
          keepalive: false
        } as ExtensionBackendPostRequest));
        const body = (response.body ?? {}) as Record<string, unknown>;
        if (!response.ok) {
          return { ok: false, status: response.status_code ?? null, url: response.url, body, error_code: response.error_code ?? "network_failed", error_message: response.error_message ?? null, network_error: response.status_code === null };
        }
        const sessionId = typeof body.session_id === "string" ? body.session_id.trim() : null;
        return { ok: true, session_id: sessionId ?? "", created: Boolean(body.created), status: response.status_code, url: response.url, body };
      } catch (err) {
        return { ok: false, error_code: "create_canonical_session_threw", error_message: err instanceof Error ? err.message : String(err), network_error: true };
      }
    },
    listCaptureInboxProfileItems: async (profileUrl: string): Promise<WholeProfileCaptureInboxProfileItemsResult> => {
      try {
        const baseUrl = await readBackgroundApiBaseUrl22C11B();
        const path = `/douyin-extension/capture-inbox/profile-items?profile_url=${encodeURIComponent(profileUrl)}&limit=1000`;
        const response = await postToBackend(await withStoredAuthHeader({
          base_url: baseUrl,
          path,
          method: "GET",
          keepalive: false
        } as ExtensionBackendPostRequest));
        const body = (response.body ?? {}) as Record<string, unknown>;
        if (!response.ok) {
          return {
            ok: false,
            status: response.status_code ?? null,
            error_code: response.error_code ?? "profile_items_failed",
            error_message: response.error_message ?? null,
            items: [],
            items_count: 0,
            counts: null,
            profile_identifier: null,
            raw: body
          } as WholeProfileCaptureInboxProfileItemsResult;
        }
        const items = Array.isArray(body.items) ? body.items as Array<Record<string, unknown>> : [];
        const counts = body.counts && typeof body.counts === "object" && !Array.isArray(body.counts)
          ? body.counts as Record<string, unknown>
          : null;
        return {
          ok: true,
          status: response.status_code ?? 200,
          items,
          items_count: typeof body.items_count === "number" ? body.items_count : items.length,
          counts,
          profile_identifier: typeof body.profile_identifier === "string" ? body.profile_identifier : null,
          raw: body
        } as WholeProfileCaptureInboxProfileItemsResult;
      } catch (err) {
        return {
          ok: false,
          error_code: "list_capture_inbox_profile_items_threw",
          error_message: err instanceof Error ? err.message : String(err),
          items: [],
          items_count: 0,
          counts: null,
          profile_identifier: null
        } as WholeProfileCaptureInboxProfileItemsResult;
      }
    },
    listCaptureInboxProfileSummary: async (profileUrl: string): Promise<WholeProfileCaptureInboxProfileSummaryResult> => {
      try {
        const baseUrl = await readBackgroundApiBaseUrl22C11B();
        const path = `/douyin-extension/capture-inbox/profile-summary?profile_url=${encodeURIComponent(profileUrl)}`;
        const response = await postToBackend(await withStoredAuthHeader({
          base_url: baseUrl,
          path,
          method: "GET",
          keepalive: false
        } as ExtensionBackendPostRequest));
        const body = (response.body ?? {}) as Record<string, unknown>;
        if (!response.ok) {
          return {
            ok: false,
            status: response.status_code ?? null,
            error_code: response.error_code ?? "profile_summary_failed",
            error_message: response.error_message ?? null,
            total_count: 0,
            counts: null,
            profile_identifier: null,
            raw: body
          } as WholeProfileCaptureInboxProfileSummaryResult;
        }
        const counts = body.counts && typeof body.counts === "object" && !Array.isArray(body.counts)
          ? body.counts as Record<string, unknown>
          : null;
        return {
          ok: true,
          status: response.status_code ?? 200,
          total_count: typeof body.total_count === "number"
            ? body.total_count
            : typeof counts?.captured === "number"
              ? counts.captured
              : 0,
          counts,
          profile_identifier: typeof body.profile_identifier === "string" ? body.profile_identifier : null,
          normalized_profile_url: typeof body.normalized_profile_url === "string" ? body.normalized_profile_url : null,
          profile_scope: typeof body.profile_scope === "string" ? body.profile_scope : null,
          source: typeof body.source === "string" ? body.source : null,
          raw: body
        } as WholeProfileCaptureInboxProfileSummaryResult;
      } catch (err) {
        return {
          ok: false,
          error_code: "list_capture_inbox_profile_summary_threw",
          error_message: err instanceof Error ? err.message : String(err),
          total_count: 0,
          counts: null,
          profile_identifier: null
        } as WholeProfileCaptureInboxProfileSummaryResult;
      }
    },
    getBackendBaseUrl: (): string | null => backgroundApiBaseUrlCache22C11B,
    sleep: (ms: number) => sleepScanRetryWait22C14B(ms),
    getCalibration: async (): Promise<unknown> => {
      const stored = await chrome.storage.local.get(DOUYIN_SCANNER_CALIBRATION_KEY).catch(() => ({} as Record<string, unknown>));
      return (stored as Record<string, unknown>)[DOUYIN_SCANNER_CALIBRATION_KEY] ?? null;
    },
    ensureContentScriptReady: async (tabId: number): Promise<{ ok: boolean; status: string; error?: string | null }> => {
      try {
        const response = await chrome.tabs.sendMessage(tabId, { type: "DOUYIN_RUNTIME_AUTHORITY_SNAPSHOT_22C11B" } satisfies ExtensionMessage) as ExtensionMessageResponse;
        return { ok: response?.ok === true, status: response?.ok === true ? "healthy" : "content_script_missing", error: response?.error ?? null };
      } catch {
        return { ok: false, status: "content_script_missing", error: "content_script_not_ready" };
      }
    },
    openDirectModal: undefined,
    extractModalMetrics: undefined,
    classifyProfileVideos: undefined
  } as unknown as WholeProfileHarvestRuntime;
}

// NOTE: The hybrid network cache runner (DOUYIN_HYBRID_NETWORK_CACHE_RUNNER) is
// dispatched by the SINGLE canonical message router registered above
// (chrome.runtime.onMessage.addListener -> handleMessage), which handles this
// message type in its DOUYIN_HYBRID_NETWORK_CACHE_RUNNER branch.
//
// A second, standalone onMessage listener used to live here and ALSO dispatched
// runBatchCollectHybridNetworkCacheMode for the same message. Because Chrome MV3
// invokes EVERY registered onMessage listener for every message, that duplicate
// registration ran the runner TWICE concurrently for a single popup dispatch.
// The later invocation re-ACKed the collect job back to "running" AFTER the
// first invocation had already completed it, reverting collect_job.state and
// dropping the hybrid_collector_completed escape hatch — which froze the
// "Collecting videos" button and (on the non-pre-skip path) risked duplicate
// concurrent backend flushes for the same items. The duplicate listener has been
// removed so the runner is dispatched exactly once per message. The runner also
// carries an entry-level idempotency guard as defense-in-depth.

if (typeof chrome !== "undefined" && chrome.storage?.onChanged) {
  chrome.storage.onChanged.addListener((changes, areaName) => {
    if (areaName !== "local") return;
    if (!changes[EXTENSION_AUTH_TOKEN_STORAGE_KEY] && !changes.apiAuthRequired) return;
    const tokenChange = changes[EXTENSION_AUTH_TOKEN_STORAGE_KEY];
    const authRequiredChange = changes.apiAuthRequired;
    const tokenLost = tokenChange != null && (typeof tokenChange.newValue !== "string" || tokenChange.newValue.trim().length === 0);
    const authRequired = authRequiredChange?.newValue === true;
    if (!tokenLost && !authRequired) return;
    void pauseWholeProfileHarvestOnAuthLoss(buildBackgroundHybridRuntime()).catch(() => undefined);
  });
}






