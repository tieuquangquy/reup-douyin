import { isHybridTailGapClosed, isHybridUnreachableTailGapOffer } from "./hybridUnreachableTailGap.js";
import type { ActiveProfilePresentation, ActiveProfileRepositorySnapshot } from "./activeProfilePresentation.js";
import { profileIdentifierFromUrl } from "./profileTargetRepository.js";
import { detectCurrentDouyinProfileIdentity, isDifferentProfile } from "./profileResolver.js";
import type { WholeProfileHarvestState } from "./state.js";

export type ScanProfileResetMode = "new_profile" | "current_profile_rescan" | "none";

function normalizeProfileUrlForComparison(url: string | null | undefined): string | null {
  if (typeof url !== "string" || !url.trim()) return null;
  const identity = detectCurrentDouyinProfileIdentity(url.trim(), null);
  return identity.canonical_profile_url?.replace(/\/+$/, "") ?? url.trim().replace(/\/+$/, "");
}

export type ActiveProfileInboxSummary = {
  total_count: number;
  /** Videos saved and ready in Capture Inbox for this profile. */
  already_collected: number;
  /** Videos discovered by scan but not yet captured in inbox. */
  new_count: number;
  queue_count: number;
  /** Captured in inbox but not READY (needs review / enrichment). Not a collect queue. */
  incomplete_count: number;
  inbox_needs_review_count: number;
  need_retry_count: number;
  /** Raw captured rows from API (ready + pending statuses). */
  captured_total: number;
  trusted: boolean;
};

export type ActiveProfileInboxSummarySource = {
  counts?: Record<string, unknown> | null;
  total_count?: number | null;
  normalized_profile_url?: string | null;
  profile_identifier?: string | null;
  scanned_total?: number | null;
};

export type ProfileContextViewModel = {
  mismatch: true;
  active_tab_on_profile: boolean;
  stored_profile_url: string | null;
  stored_progress_label: string | null;
  active_profile_url: string | null;
  active_profile_label: string;
  active_inbox_summary: ActiveProfileInboxSummary | null;
  banner_message: string;
  show_previous_inbox_link: boolean;
  collection_running_on_stored_profile: boolean;
};

export type ScannerControlPanelRenderContext = {
  active_tab_url?: string | null;
  active_profile_inbox_summary?: ActiveProfileInboxSummary | null;
  /** When false, collect/save to Capture Inbox must be blocked in the UI. */
  app_backend_logged_in?: boolean;
  active_profile_repository_snapshot?: ActiveProfileRepositorySnapshot | null;
  active_profile_presentation?: ActiveProfilePresentation | null;
};

function numberValue(value: unknown, fallback = 0): number {
  if (typeof value === "number" && Number.isFinite(value)) return Math.max(0, Math.round(value));
  if (typeof value === "string" && value.trim()) {
    const parsed = Number(value);
    if (Number.isFinite(parsed)) return Math.max(0, Math.round(parsed));
  }
  return fallback;
}

function storedProgressLabel(state: WholeProfileHarvestState): string | null {
  const snapshot = state.post_scan_counter_snapshot;
  if (snapshot?.status === "applied" && snapshot.already_collected > 0) {
    return `${snapshot.already_collected} collected`;
  }
  if (state.scan_job.total_persisted > 0 && state.profile_scan.status === "success") {
    const collected = snapshot?.already_collected ?? 0;
    if (collected > 0) return `${collected} collected`;
    return `${state.scan_job.total_persisted} scanned`;
  }
  return null;
}

function humanStoredSessionLabel(storedProgress: string | null): string {
  return storedProgress ? `your previous profile (${storedProgress})` : "your previous profile";
}

function isHybridCollectModeEnabled(state: WholeProfileHarvestState): boolean {
  const summary = state.debug.last_response_summary;
  if (!summary || typeof summary !== "object" || Array.isArray(summary)) return false;
  const flag = (summary as Record<string, unknown>).hybrid_network_cache_mode_flag;
  return flag === "enabled" || flag === true;
}

function numericSummaryField(summary: Record<string, unknown>, key: string): number | null {
  const value = summary[key];
  if (typeof value === "number" && Number.isFinite(value)) return Math.max(0, Math.round(value));
  if (typeof value === "string" && value.trim()) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? Math.max(0, Math.round(parsed)) : null;
  }
  return null;
}

/**
 * True when a hybrid profile collect has no remaining work — even if stale
 * post_scan_counter_snapshot or inbox cache still show a partial batch (500/503).
 */
export function hybridProfileCollectFullyComplete(
  state: WholeProfileHarvestState,
  renderContext: ScannerControlPanelRenderContext = {}
): boolean {
  if (isHybridTailGapClosed(state)) return true;
  if (!isHybridCollectModeEnabled(state)) return false;
  const summary = state.debug.last_response_summary && typeof state.debug.last_response_summary === "object"
    ? state.debug.last_response_summary as Record<string, unknown>
    : {};
  const hybridMarkedDone = summary.hybrid_collector_completed === "yes"
    || summary.hybrid_collection_done_override_applied === "yes";
  const collectTerminal = state.collect_job.state === "completed"
    || state.collect_job.state === "stuck"
    || state.collect_job.state === "failed";
  if (!hybridMarkedDone && !collectTerminal) return false;

  const inbox = renderContext.active_profile_inbox_summary;
  if (inbox?.trusted && profileContextCollectableRemaining(inbox) <= 0 && inbox.already_collected > 0) {
    return true;
  }

  const postRunNew = numericSummaryField(summary, "hybrid_runner_post_run_tile_new");
  const postRunAlready = numericSummaryField(summary, "hybrid_runner_post_run_tile_already");
  if (postRunNew === 0 && (postRunAlready ?? 0) > 0) return true;

  const snap = state.post_scan_counter_snapshot;
  if (snap?.status === "applied" && snap.new <= 0 && snap.queue <= 0 && (snap.already_collected ?? 0) > 0) {
    return true;
  }

  const scannedTotal = Math.max(
    snap?.scanned_total ?? 0,
    state.scan_job.total_persisted ?? 0,
    state.classification.total_candidates ?? 0
  );
  if (postRunAlready != null && scannedTotal > 0 && postRunAlready >= scannedTotal) return true;
  if (snap?.status === "applied" && scannedTotal > 0 && (snap.already_collected ?? 0) >= scannedTotal) return true;

  return false;
}

/** Videos the extension can still collect (local queue / not yet captured). Excludes inbox review backlog. */
export function profileContextCollectableRemaining(summary: ActiveProfileInboxSummary | null | undefined): number {
  if (!summary) return 0;
  return Math.max(0, summary.new_count) + Math.max(0, summary.need_retry_count);
}

/**
 * Remaining videos to collect when the in-memory harvest.queue is empty after a large-profile batch.
 * Repository / inbox / persisted totals still show work left (e.g. 500 saved, 502 remaining).
 */
export function expectedCollectContinuationRemaining(
  state: WholeProfileHarvestState,
  renderContext?: ScannerControlPanelRenderContext
): number {
  if (state.scan_job.status === "failed" || state.profile_scan.status === "failed" || state.workflow.scan.status === "failed") {
    return 0;
  }
  const tabUrl = renderContext?.active_tab_url
    ?? state.page_context.current_url
    ?? state.safety.tab_health.current_url
    ?? null;
  if (tabUrl && detectProfileContextMismatch(state, tabUrl)) return 0;
  if (shouldGateScannerPanelForProfileContext(state, tabUrl)) return 0;
  if (isHybridTailGapClosed(state)) return 0;
  if (isHybridUnreachableTailGapOffer(state)) return 0;
  if (state.profile_scan.status !== "success" && state.scan_job.status !== "completed") return 0;
  if (hybridProfileCollectFullyComplete(state, renderContext ?? {})) return 0;
  const summary = renderContext?.active_profile_inbox_summary;
  if (summary?.trusted) {
    const inboxRemaining = profileContextCollectableRemaining(summary);
    if (inboxRemaining > 0) return inboxRemaining;
    // Trusted inbox with nothing left to collect is authoritative over stale scan snapshots.
    if (summary.already_collected > 0 || activeProfileInboxSummaryIsComplete(summary)) return 0;
  }
  const snap = state.post_scan_counter_snapshot;
  if (!persistedScanJobTotalsTrustedForStoredProfile(state)) return 0;
  const diag = state.profile_scan.diagnostics && typeof state.profile_scan.diagnostics === "object"
    ? state.profile_scan.diagnostics as Record<string, unknown>
    : {};
  const persisted = numberValue(
    diag.queue_total_persisted ?? diag.scan_job_total_persisted ?? diag.profile_queue_total_count,
    state.scan_job.total_persisted
  );
  const alreadyCollected = Math.max(
    numberValue(diag.profile_already_collected_count, state.target_status.complete),
    state.harvest.updated,
    snap?.already_collected ?? 0
  );
  if (
    alreadyCollected === 0
    && persisted > 0
    && storedScanSessionAppliesToActiveTab(state, tabUrl)
    && state.calibration?.ready === true
    && (state.layer.profile_scan_ready
      || (state.scan_job.status === "completed" && state.scan_job.has_more_state === false)
      || (state.profile_scan.status === "success" && state.verify.status === "success"))
  ) {
    return persisted;
  }
  const partialBatchWork = persisted > alreadyCollected && alreadyCollected > 0;
  const batchPhase = state.phase === "batch_safe_mode_completed";
  if (!partialBatchWork && !batchPhase) return 0;
  if (snap?.status === "applied") {
    const snapRemaining = Math.max(0, snap.new) + Math.max(0, snap.need_retry ?? 0);
    if (snapRemaining > 0) return snapRemaining;
    const scannedGap = Math.max(0, (snap.scanned_total ?? 0) - (snap.already_collected ?? 0));
    if (scannedGap > 0) return scannedGap;
  }
  if (persisted > alreadyCollected) return persisted - alreadyCollected;
  const planned = state.harvest.planned_total ?? 0;
  const done = Math.max(state.harvest.updated, alreadyCollected);
  if (planned > done) return planned - done;
  return 0;
}

/** Split remaining collect work across New vs Queue tiles after partial collection. */
export function partialCollectTileCounts(
  remaining: number,
  alreadyCollected: number,
  nextBatchCap = 500
): { newCount: number; queueCount: number } {
  const left = Math.max(0, Math.round(remaining));
  if (left <= 0) return { newCount: 0, queueCount: 0 };
  if (alreadyCollected > 0) {
    return { newCount: left, queueCount: Math.min(left, nextBatchCap) };
  }
  return { newCount: left, queueCount: left };
}

export function profileContextInboxReviewCount(summary: ActiveProfileInboxSummary | null | undefined): number {
  if (!summary) return 0;
  return Math.max(0, summary.inbox_needs_review_count, summary.incomplete_count);
}

/** @deprecated Use profileContextCollectableRemaining for collect routing. */
export function profileContextActionableRemaining(summary: ActiveProfileInboxSummary | null | undefined): number {
  return profileContextCollectableRemaining(summary);
}

export function profileContextHeaderStatus(summary: ActiveProfileInboxSummary | null | undefined): string {
  if (!summary || summary.already_collected <= 0) return "Not scanned";
  const collectLeft = profileContextCollectableRemaining(summary);
  const review = profileContextInboxReviewCount(summary);
  if (review > 0 && collectLeft === 0) {
    return review === 1
      ? `${summary.already_collected} collected · 1 needs review`
      : `${summary.already_collected} collected · ${review} need review`;
  }
  if (collectLeft > 0) return `${summary.already_collected} collected · ${collectLeft} left`;
  return `${summary.already_collected} collected`;
}

export function inboxSummaryHasReviewOnlyBacklog(summary: ActiveProfileInboxSummary | null | undefined): boolean {
  if (!summary) return false;
  return profileContextInboxReviewCount(summary) > 0 && profileContextCollectableRemaining(summary) === 0;
}

export function profileContextShouldShowActiveTiles(
  activeTabOnProfile: boolean,
  summary: ActiveProfileInboxSummary | null | undefined,
  allowMismatchInboxTiles: boolean
): boolean {
  if (!activeTabOnProfile || !summary || !activeProfileInboxSummaryIsResumeEligible(summary)) return false;
  if (!allowMismatchInboxTiles) return false;
  return summary.already_collected > 0 || activeProfileInboxHasActionableWork(summary);
}

export function profileUrlsMatchForInboxTrust(storedUrl: string | null | undefined, responseUrl: string | null | undefined): boolean {
  if (!storedUrl || !responseUrl) return false;
  const a = detectCurrentDouyinProfileIdentity(storedUrl);
  const b = detectCurrentDouyinProfileIdentity(responseUrl);
  if (!a.canonical_profile_url || !b.canonical_profile_url) return false;
  return !isDifferentProfile(a, b);
}

export function parseActiveProfileInboxSummary(
  source: ActiveProfileInboxSummarySource | Record<string, unknown> | null | undefined,
  activeProfileUrl?: string | null,
  scannedTotal?: number | null
): ActiveProfileInboxSummary | null {
  const payload = source && typeof source === "object" ? source : null;
  if (!payload) return null;
  const counts = (payload as ActiveProfileInboxSummarySource).counts
    ?? ((payload as Record<string, unknown>).counts as Record<string, unknown> | null | undefined);
  if (!counts || typeof counts !== "object") return null;

  const ready = numberValue(counts.ready);
  const capturedTotal = numberValue(counts.captured);
  const needsAction = numberValue(counts.needs_action);
  const failed = numberValue(counts.fail ?? counts.failed ?? counts.need_retry);
  const explicitIncomplete = numberValue(counts.incomplete);
  const totalFromApi = typeof (payload as ActiveProfileInboxSummarySource).total_count === "number"
    ? (payload as ActiveProfileInboxSummarySource).total_count
    : typeof (payload as Record<string, unknown>).total_count === "number"
      ? (payload as Record<string, unknown>).total_count as number
      : null;
  const total = typeof totalFromApi === "number" && Number.isFinite(totalFromApi)
    ? Math.max(0, Math.round(totalFromApi))
    : capturedTotal;
  const normalizedUrl = typeof (payload as ActiveProfileInboxSummarySource).normalized_profile_url === "string"
    ? (payload as ActiveProfileInboxSummarySource).normalized_profile_url
    : null;
  const trusted = activeProfileUrl
    ? profileUrlsMatchForInboxTrust(activeProfileUrl, normalizedUrl ?? activeProfileUrl)
    : false;
  const scannedFromPayload = typeof (payload as ActiveProfileInboxSummarySource).scanned_total === "number"
    ? (payload as ActiveProfileInboxSummarySource).scanned_total
    : null;
  const scanned = typeof scannedTotal === "number" && Number.isFinite(scannedTotal)
    ? Math.max(0, Math.round(scannedTotal))
    : typeof scannedFromPayload === "number" && Number.isFinite(scannedFromPayload)
      ? Math.max(0, Math.round(scannedFromPayload))
      : null;
  // API needs_action = already captured in inbox but not ready/dup/fail — not extension collect queue.
  const inboxNeedsReview = Math.max(0, needsAction, explicitIncomplete);
  const collectableRemaining = scanned != null ? Math.max(0, scanned - capturedTotal) : 0;
  const tileCounts = partialCollectTileCounts(collectableRemaining, ready);
  return {
    total_count: total,
    already_collected: ready,
    new_count: tileCounts.newCount,
    queue_count: tileCounts.queueCount,
    incomplete_count: inboxNeedsReview,
    inbox_needs_review_count: inboxNeedsReview,
    need_retry_count: failed,
    captured_total: capturedTotal,
    trusted
  };
}

/** Inbox counts are only actionable after extension session matches this profile (post-switch or same tab). */
export function activeProfileInboxSummaryIsResumeEligible(
  summary: ActiveProfileInboxSummary | null | undefined
): boolean {
  if (!summary || !summary.trusted) return false;
  if (summary.already_collected <= 0 && summary.queue_count <= 0 && summary.inbox_needs_review_count <= 0) return false;
  if (summary.captured_total > 0 && summary.already_collected === 0 && summary.inbox_needs_review_count === summary.captured_total) {
    return false;
  }
  return activeProfileInboxHasActionableWork(summary) || summary.already_collected > 0;
}

export function activeProfileInboxHasActionableWork(summary: ActiveProfileInboxSummary | null | undefined): boolean {
  if (!summary) return false;
  return profileContextCollectableRemaining(summary) > 0;
}

/** Nothing left to collect via extension; inbox review backlog is allowed. */
export function activeProfileInboxSummaryIsComplete(summary: ActiveProfileInboxSummary | null | undefined): boolean {
  if (!summary || !summary.trusted) return false;
  return summary.already_collected > 0 && !activeProfileInboxHasActionableWork(summary);
}

export function inboxSummaryScannerCounts(summary: ActiveProfileInboxSummary): {
  newCount: number;
  incompleteCount: number;
  alreadyCollectedCount: number;
  queueCount: number;
  collectedCount: number;
  savedCount: number;
  failedCount: number;
} {
  return {
    newCount: summary.new_count,
    incompleteCount: summary.inbox_needs_review_count,
    alreadyCollectedCount: summary.already_collected,
    queueCount: summary.queue_count,
    collectedCount: summary.already_collected,
    savedCount: summary.already_collected,
    failedCount: summary.need_retry_count
  };
}

export function inboxSummaryProvesBackendEmpty(summary: ActiveProfileInboxSummary | null | undefined): boolean {
  return summary?.trusted === true
    && summary.already_collected === 0
    && summary.captured_total === 0
    && summary.inbox_needs_review_count === 0;
}

const HYBRID_POST_COLLECT_AUTHORITY_WINDOW_MS = 5 * 60_000;

export function hybridPostCollectWriteOkCount(state: WholeProfileHarvestState): number {
  const summary = state.debug.last_response_summary && typeof state.debug.last_response_summary === "object"
    ? state.debug.last_response_summary as Record<string, unknown>
    : {};
  if (typeof summary.hybrid_runner_write_ok_count === "number" && Number.isFinite(summary.hybrid_runner_write_ok_count)) {
    return Math.max(0, Math.round(summary.hybrid_runner_write_ok_count));
  }
  if (summary.hybrid_runner_backend_write_ok === "yes") return 1;
  return 0;
}

/**
 * True during the post-collect authority window: Hybrid reported write_ok and the
 * job finished recently. Prevents empty inbox API/cache from reverting UI to
 * "139 ready" right after a successful re-collect (backend wipe → Start Collecting).
 *
 * Intentionally false for stale completed jobs after an operator backend wipe
 * (backend_empty_disproves_snapshot) unless completion just happened.
 */
export function hybridPostCollectAuthorityActive(
  state: WholeProfileHarvestState,
  nowMs: number = Date.now()
): boolean {
  const writeOk = hybridPostCollectWriteOkCount(state);
  if (writeOk <= 0) return false;

  const summary = state.debug.last_response_summary && typeof state.debug.last_response_summary === "object"
    ? state.debug.last_response_summary as Record<string, unknown>
    : {};
  const hybridMarkedDone = summary.hybrid_collector_completed === "yes"
    || summary.hybrid_collection_done_override_applied === "yes";
  const collectTerminal = state.collect_job.state === "completed"
    || state.collect_job.state === "stuck"
    || state.collect_job.state === "failed";
  if (!hybridMarkedDone && !collectTerminal) return false;

  const snap = state.post_scan_counter_snapshot;
  const wipeSnapshot = snap?.status === "applied"
    && snap.source === "backend_empty_disproves_snapshot"
    && (snap.already_collected ?? 0) === 0
    && (snap.backend_captured ?? 0) === 0;

  const completedAtCandidates = [
    state.collect_job.completed_at,
    typeof summary.hybrid_collection_done_completed_at === "string" ? summary.hybrid_collection_done_completed_at : null
  ];
  let completedMs: number | null = null;
  for (const candidate of completedAtCandidates) {
    if (!candidate) continue;
    const parsed = Date.parse(candidate);
    if (Number.isFinite(parsed)) {
      completedMs = completedMs == null ? parsed : Math.max(completedMs, parsed);
    }
  }

  const recentCompletion = completedMs != null && nowMs - completedMs <= HYBRID_POST_COLLECT_AUTHORITY_WINDOW_MS;
  const snapCaptured = (snap?.already_collected ?? 0) > 0 || (snap?.backend_captured ?? 0) > 0;

  if (snap?.source === "backend_capture_inbox_profile_summary" && snapCaptured && collectTerminal) {
    return recentCompletion;
  }
  if (wipeSnapshot) {
    return recentCompletion && hybridMarkedDone;
  }
  if (recentCompletion && hybridMarkedDone) return true;
  return false;
}

export function emptyTrustedInboxSummary(profileUrl: string): ActiveProfileInboxSummary {
  return {
    total_count: 0,
    already_collected: 0,
    new_count: 0,
    queue_count: 0,
    incomplete_count: 0,
    inbox_needs_review_count: 0,
    need_retry_count: 0,
    captured_total: 0,
    trusted: profileUrl.trim().length > 0
  };
}

/** Snapshot or inbox proves backend has no captures while local state may still show collected. */
export function staleLocalCollectedDisprovenByBackendEmpty(
  state: WholeProfileHarvestState,
  renderContext: ScannerControlPanelRenderContext = {}
): boolean {
  if (hybridPostCollectAuthorityActive(state)) return false;
  const snap = state.post_scan_counter_snapshot;
  if (snap?.status === "applied") {
    if (snap.source === "backend_empty_disproves_snapshot") return true;
    if (snap.already_collected === 0 && snap.backend_captured === 0 && (snap.new > 0 || snap.queue > 0)) {
      const hasStaleQueueMarkers = state.harvest.queue.some((item) => {
        const status = String(item.status);
        return status === "already_collected" || status === "backend_verified" || status === "complete" || status === "extracted" || item.capture_status === "complete" || Boolean(item.capture_inbox_item_id || item.backend_item_id);
      });
      const hasStaleMetadata = state.profile_scan.target_details.some((detail) => {
        const metadataStatus = String(detail.backend_item?.metadata_status ?? "").toLowerCase();
        return Boolean(detail.backend_item?.item_id && ["ready", "complete"].includes(metadataStatus));
      });
      const classificationComplete = state.classification.status === "success" ? state.classification.counts.complete : 0;
      if (hasStaleQueueMarkers || hasStaleMetadata || classificationComplete > 0) return true;
    }
  }
  if (inboxSummaryProvesBackendEmpty(renderContext.active_profile_inbox_summary)) {
    if ((snap?.already_collected ?? 0) > 0 || (snap?.backend_captured ?? 0) > 0) return true;
    if (state.harvest.queue.some((item) => {
      const status = String(item.status);
      return status === "already_collected" || status === "backend_verified" || status === "complete" || status === "extracted" || item.capture_status === "complete";
    })) return true;
    if (state.classification.status === "success" && state.classification.counts.complete > 0) return true;
  }
  return false;
}

export function shouldTrustSnapshotAlreadyCollected(
  state: WholeProfileHarvestState,
  renderContext: ScannerControlPanelRenderContext
): boolean {
  if (hybridPostCollectAuthorityActive(state)) return true;
  if (renderContext.app_backend_logged_in === false) return false;
  if (staleLocalCollectedDisprovenByBackendEmpty(state, renderContext)) return false;
  const summary = renderContext.active_profile_inbox_summary;
  if (inboxSummaryProvesBackendEmpty(summary)) return false;
  const snap = state.post_scan_counter_snapshot;
  if (!snap || snap.status !== "applied") return false;
  if (!summary?.trusted) {
    return !(snap.already_collected > 0 && snap.new <= 0 && snap.queue <= 0);
  }
  return snap.already_collected > 0 || summary.already_collected > 0 || summary.captured_total > 0;
}

export function deviceScanQueueCountFromSnapshot(
  state: WholeProfileHarvestState,
  snapshot: NonNullable<WholeProfileHarvestState["post_scan_counter_snapshot"]>
): number {
  const pendingQueue = state.harvest.queue.filter((item) => {
    const status = String(item.status);
    return status === "pending" || status === "new" || status === "retry" || item.capture_status === "new";
  }).length;
  return Math.max(snapshot.new, snapshot.queue, snapshot.scanned_total, state.scan_job.total_persisted, state.harvest.pending, pendingQueue);
}

/** True while scan/classify is running — collect tiles, block reasons, and preflight errors must not paint. */
export function collectPresentationSuppressed(state: WholeProfileHarvestState): boolean {
  const expected = resolveScanJobExpectedCount(state);
  const persisted = Math.max(
    state.scan_job.total_persisted ?? 0,
    state.profile_scan.accepted_target_count ?? 0,
    state.verify.verified_target_count ?? 0
  );
  const scanTerminalComplete = state.scan_job.status === "completed"
    && state.profile_scan.status === "success"
    && persisted > 0
    && scanPersistedMeetsExpectedCount(expected, persisted)
    && persistedScanJobTotalsTrustedForStoredProfile(state);
  if (scanTerminalComplete) return false;
  return state.workflow.scan.status === "running"
    || state.workflow.classification.status === "running"
    || state.scan_job.status === "running"
    || state.scan_job.status === "retry_wait"
    || (state.status === "verifying" && state.workflow.active_task === "scan_profile");
}

/** Strip stale Start Collecting block copy that must not survive profile switch or rescan. */
export function clearStaleCollectBlockDiagnostics(summary: Record<string, unknown>): Record<string, unknown> {
  return {
    ...summary,
    start_collecting_blocked_reason: null,
    start_collecting_preflight_result: null,
    start_collecting_error: null,
    start_collecting_stage: null,
    last_scanner_error: null,
    last_scanner_result: null
  };
}

const STALE_OVERCOLLECTION_DIAGNOSTIC_KEYS = [
  "over_displayed_count",
  "over_displayed_extra_ids_exact",
  "over_displayed_extra_items_exact",
  "over_displayed_validation_status",
  "over_displayed_same_profile_validated",
  "over_displayed_itemized_reason_summary",
  "over_displayed_extra_source",
  "over_displayed_outside_profile_offending_aweme_ids",
  "over_displayed_boundary_start_index",
  "over_displayed_visible_boundary_index",
  "over_displayed_boundary_end_index",
  "count_semantics_status",
  "count_semantics_reason",
  "scan_health_verdict",
  "scan_health_verdict_reason",
  "final_verdict",
  "forensic_export_available",
  "forensic_export_scan_run_id",
  "accepted_target_ledger_present"
] as const;

/** Strip stale overcollection proof that must not block a fresh or reset scan. */
export function clearStaleOvercollectionDiagnostics(summary: Record<string, unknown>): Record<string, unknown> {
  const cleared = { ...summary };
  for (const key of STALE_OVERCOLLECTION_DIAGNOSTIC_KEYS) {
    cleared[key] = null;
  }
  return cleared;
}

export function clearStaleRuntimeScanDiagnostics(summary: Record<string, unknown>): Record<string, unknown> {
  return clearStaleOvercollectionDiagnostics(clearStaleCollectBlockDiagnostics(summary));
}

function numericProfileContextDiagnostic(value: unknown): number | null {
  const numeric = typeof value === "number" ? value : typeof value === "string" && value.trim() ? Number(value) : Number.NaN;
  return Number.isFinite(numeric) ? numeric : null;
}

function scanFinalizationTerminalForOvercollection(
  diagnostics: Record<string, unknown>,
  state: WholeProfileHarvestState
): boolean {
  const result = String(diagnostics.scan_finalization_result ?? "").trim();
  if (result === "success" || result === "completed_with_warning" || result === "completed_with_api_over_displayed_count") {
    return true;
  }
  return state.layer.profile_scan_ready || state.profile_scan.status === "success";
}

/**
 * Overcollection review is only actionable when diagnostics belong to a finished scan
 * for the stored profile with persisted queue data.
 */
export function overcollectionDiagnosticsTrusted(
  state: WholeProfileHarvestState,
  diagnostics: Record<string, unknown>
): boolean {
  const overCount = numericProfileContextDiagnostic(diagnostics.over_displayed_count);
  const hasOverdisplaySignal = (overCount != null && overCount > 0)
    || String(diagnostics.count_semantics_status ?? "") === "overcollected_needs_validation"
    || String(diagnostics.count_semantics_status ?? "") === "failed_overcollection_outside_profile"
    || diagnostics.over_displayed_validation_status === "needs_validation"
    || diagnostics.over_displayed_validation_status === "outside_profile_detected";
  if (!hasOverdisplaySignal) return false;
  if (!scanFinalizationTerminalForOvercollection(diagnostics, state)) return false;
  const hasQueueData = state.harvest.queue.length > 0 || (state.scan_job.total_persisted ?? 0) > 0;
  if (!hasQueueData) return false;
  if (!persistedScanJobTotalsTrustedForStoredProfile(state)) return false;
  const authorityRunId = state.scan_job.scan_job_id ?? state.run_id ?? null;
  if (!authorityRunId) return false;
  const diagRunId = typeof diagnostics.scan_run_id === "string" && diagnostics.scan_run_id.trim()
    ? diagnostics.scan_run_id.trim()
    : null;
  const forensicRunId = typeof diagnostics.forensic_export_scan_run_id === "string" && diagnostics.forensic_export_scan_run_id.trim()
    ? diagnostics.forensic_export_scan_run_id.trim()
    : null;
  if (diagRunId && diagRunId !== authorityRunId && forensicRunId !== authorityRunId) return false;
  return true;
}

/** False when scan_job persisted totals belong to a different profile than state.profile_url. */
export function persistedScanJobTotalsTrustedForStoredProfile(state: WholeProfileHarvestState): boolean {
  const storedId = typeof state.profile_url === "string" && state.profile_url.trim()
    ? profileIdentifierFromUrl(state.profile_url.trim())
    : null;
  const jobId = typeof state.scan_job.profile_identifier === "string" ? state.scan_job.profile_identifier.trim() : "";
  if (storedId && jobId && storedId !== jobId) return false;
  return true;
}

/** False when diagnostics scan_run_id disagrees with the current scan_job / run_id. */
export function scanSessionTrustedForStoredProfile(state: WholeProfileHarvestState): boolean {
  if (!persistedScanJobTotalsTrustedForStoredProfile(state)) return false;
  const authorityRunId = state.scan_job.scan_job_id ?? state.run_id ?? null;
  if (!authorityRunId) return false;
  const profileDiag = state.profile_scan.diagnostics && typeof state.profile_scan.diagnostics === "object"
    ? state.profile_scan.diagnostics as Record<string, unknown>
    : {};
  const debugDiag = state.debug.last_response_summary && typeof state.debug.last_response_summary === "object"
    ? state.debug.last_response_summary as Record<string, unknown>
    : {};
  const diagRunId = typeof profileDiag.scan_run_id === "string" && profileDiag.scan_run_id.trim()
    ? profileDiag.scan_run_id.trim()
    : typeof debugDiag.scan_run_id === "string" && debugDiag.scan_run_id.trim()
      ? debugDiag.scan_run_id.trim()
      : null;
  if (diagRunId && diagRunId !== authorityRunId) return false;
  return true;
}

/** Collect / scan-ready presentation must not use another profile's session. */
export function scanSessionTrustedForActiveProfile(
  state: WholeProfileHarvestState,
  activeTabUrl?: string | null
): boolean {
  if (!scanSessionTrustedForStoredProfile(state)) return false;
  const tabUrl = typeof activeTabUrl === "string" && activeTabUrl.trim()
    ? activeTabUrl.trim()
    : typeof state.page_context.current_url === "string" && state.page_context.current_url.trim()
      ? state.page_context.current_url.trim()
      : typeof state.safety.tab_health.current_url === "string" && state.safety.tab_health.current_url.trim()
        ? state.safety.tab_health.current_url.trim()
        : null;
  if (tabUrl && detectProfileContextMismatch(state, tabUrl)) return false;
  return true;
}

export function activeProfileIdentifierFromTab(
  activeTabUrl: string | null | undefined
): string | null {
  const normalized = normalizeProfileUrlForComparison(activeTabUrl);
  if (!normalized) return null;
  const identifier = profileIdentifierFromUrl(normalized);
  return identifier === "unknown_profile" ? null : identifier;
}

/** True when durable scan_job rows belong to a different creator than the active tab. */
export function storedScanJobProfileIdentifierMismatch(
  state: WholeProfileHarvestState,
  activeTabUrl: string | null | undefined
): boolean {
  const storedJobId = typeof state.scan_job.profile_identifier === "string"
    ? state.scan_job.profile_identifier.trim()
    : "";
  if (!storedJobId) return false;
  const activeId = activeProfileIdentifierFromTab(activeTabUrl);
  if (!activeId) return false;
  return storedJobId !== activeId;
}

export function detectProfileContextMismatch(
  state: WholeProfileHarvestState,
  activeTabUrl: string | null | undefined
): boolean {
  const stored = detectCurrentDouyinProfileIdentity(state.profile_url, { sec_uid: state.classification.sec_uid });
  const active = detectCurrentDouyinProfileIdentity(activeTabUrl ?? state.page_context.current_url ?? state.safety.tab_health.current_url);
  if (!stored.canonical_profile_url) return false;
  if (!active.canonical_profile_url) return false;
  const storedNorm = stored.canonical_profile_url.replace(/\/+$/, "");
  const activeNorm = active.canonical_profile_url.replace(/\/+$/, "");
  if (storedNorm === activeNorm) {
    return storedScanJobProfileIdentifierMismatch(state, activeTabUrl);
  }
  return isDifferentProfile(stored, active);
}

/** Actionable harvest queue rows prove the scan produced a collect plan even when finalize status is failed. */
export function harvestQueueActionableCountForPresentation(state: WholeProfileHarvestState): number {
  const actionable = new Set([
    "new",
    "pending",
    "processing",
    "retry",
    "incomplete",
    "needs_metadata",
    "failed_recoverable"
  ]);
  return state.harvest.queue.filter((item) => actionable.has(String(item.status))).length;
}

export function scanQueueProvesSessionCompleteForPresentation(
  state: WholeProfileHarvestState,
  activeTabUrl?: string | null
): boolean {
  if (!storedScanSessionAppliesToActiveTab(state, activeTabUrl)) return false;
  if (harvestQueueActionableCountForPresentation(state) <= 0) return false;
  const classificationReady = state.classification.status === "success"
    || state.workflow.classification.status === "success";
  if (!classificationReady) return false;
  return alignedPartialScanPersistedCount(state, activeTabUrl) > 0
    || (state.profile_scan.accepted_target_count ?? 0) > 0
    || (state.scan_job.total_persisted ?? 0) > 0;
}

/** Scan failure / blocked presentation applies only when the active tab matches stored session profile. */
export function storedScanSessionAppliesToActiveTab(
  state: WholeProfileHarvestState,
  activeTabUrl: string | null | undefined
): boolean {
  const tabUrl = typeof activeTabUrl === "string" ? activeTabUrl.trim() : "";
  if (!tabUrl) return true;
  return !detectProfileContextMismatch(state, tabUrl);
}

/** Persisted scan totals on the aligned active tab when scan is not fully ready (partial/failed rescan). */
export function alignedPartialScanPersistedCount(
  state: WholeProfileHarvestState,
  activeTabUrl?: string | null
): number {
  if (!storedScanSessionAppliesToActiveTab(state, activeTabUrl)) return 0;
  return Math.max(
    0,
    state.scan_job.total_persisted ?? 0,
    state.profile_scan.accepted_target_count ?? 0,
    state.verify.verified_target_count ?? 0,
    state.verify.accepted_target_count ?? 0
  );
}

export function resolveScanJobExpectedCount(state: WholeProfileHarvestState): number | null {
  const raw = state.scan_job.expected_count;
  if (typeof raw === "number" && Number.isFinite(raw) && raw > 0) return Math.round(raw);
  const profileDiagnostics = state.profile_scan.diagnostics && typeof state.profile_scan.diagnostics === "object"
    ? state.profile_scan.diagnostics as Record<string, unknown>
    : {};
  const verifyDiagnostics = state.verify.diagnostics && typeof state.verify.diagnostics === "object"
    ? state.verify.diagnostics as Record<string, unknown>
    : {};
  const summary = state.debug.last_response_summary && typeof state.debug.last_response_summary === "object"
    ? state.debug.last_response_summary as Record<string, unknown>
    : {};
  for (const candidate of [
    profileDiagnostics.expected_profile_video_count,
    verifyDiagnostics.expected_profile_video_count,
    summary.expected_profile_video_count
  ]) {
    const numeric = typeof candidate === "number"
      ? candidate
      : typeof candidate === "string" && candidate.trim()
        ? Number(candidate)
        : Number.NaN;
    if (Number.isFinite(numeric) && numeric > 0) return Math.round(numeric);
  }
  return null;
}

/** True when persisted scan totals meet or exceed the profile expected video count. */
export function scanPersistedMeetsExpectedCount(
  expected: number | null | undefined,
  persisted: number | null | undefined
): boolean {
  if (expected == null || !Number.isFinite(expected) || expected <= 0) return false;
  const collected = typeof persisted === "number" && Number.isFinite(persisted) ? Math.max(0, Math.round(persisted)) : 0;
  return collected >= Math.round(expected);
}

/** True when persisted is within the near-complete gap threshold (exclusive of exact match). */
export function scanPersistedWithinNearCompleteGap(
  expected: number | null | undefined,
  persisted: number | null | undefined
): boolean {
  if (scanPersistedMeetsExpectedCount(expected, persisted)) return false;
  if (expected == null || !Number.isFinite(expected) || expected <= 0) return false;
  const collected = typeof persisted === "number" && Number.isFinite(persisted) ? Math.max(0, Math.round(persisted)) : 0;
  const gap = Math.round(expected) - collected;
  const threshold = Math.max(5, Math.ceil(expected * 0.01));
  return gap > 0 && gap <= threshold;
}

export function alignedScanPersistedMeetsExpected(
  state: WholeProfileHarvestState,
  activeTabUrl?: string | null
): boolean {
  if (!storedScanSessionAppliesToActiveTab(state, activeTabUrl)) return false;
  return scanPersistedMeetsExpectedCount(
    resolveScanJobExpectedCount(state),
    alignedPartialScanPersistedCount(state, activeTabUrl)
  );
}

/** Decide whether Scan Profile must clear stale session state before starting a new run. */
export function resolveScanProfileResetMode(
  state: WholeProfileHarvestState,
  activeTabUrl: string | null | undefined,
  options?: { lastPresentedProfileUrl?: string | null; profileScanReady?: boolean }
): ScanProfileResetMode {
  if (!activeTabOnDouyinProfile(activeTabUrl)) return "none";
  if (detectProfileContextMismatch(state, activeTabUrl)) return "new_profile";

  const active = detectCurrentDouyinProfileIdentity(activeTabUrl, null);
  const activeCanonical = normalizeProfileUrlForComparison(active.canonical_profile_url ?? activeTabUrl);
  if (!activeCanonical) return "none";

  const activeId = profileIdentifierFromUrl(activeCanonical);
  const jobId = typeof state.scan_job.profile_identifier === "string" ? state.scan_job.profile_identifier.trim() : "";
  if (jobId && activeId && jobId !== activeId) return "new_profile";

  const stored = detectCurrentDouyinProfileIdentity(state.profile_url, { sec_uid: state.classification.sec_uid });
  if (stored.canonical_profile_url && isDifferentProfile(stored, active)) return "new_profile";

  const profileScanReady = options?.profileScanReady === true
    || state.layer.profile_scan_ready === true
    || state.profile_scan.status === "success"
    || state.post_scan_counter_snapshot?.status === "applied";

  const lastPresented = normalizeProfileUrlForComparison(options?.lastPresentedProfileUrl ?? null);
  const visitedOtherProfile = Boolean(lastPresented && lastPresented !== activeCanonical);
  const storedCanonical = normalizeProfileUrlForComparison(state.profile_url);
  const pageCanonical = normalizeProfileUrlForComparison(
    state.page_context.current_url ?? state.safety.tab_health.current_url ?? null
  );
  const visitedOtherViaPageContext = Boolean(
    storedCanonical && pageCanonical && pageCanonical !== storedCanonical && pageCanonical !== activeCanonical
  );

  const hasPriorScanSession = profileScanReady
    || state.scan_job.status === "completed"
    || state.scan_job.status === "failed"
    || state.workflow.scan.status === "failed"
    || state.profile_scan.status === "failed"
    || state.profile_scan.status === "success"
    || (state.post_scan_counter_snapshot?.status === "applied" && (state.post_scan_counter_snapshot.scanned_total ?? 0) > 0);

  if (hasPriorScanSession || visitedOtherProfile || visitedOtherViaPageContext) return "current_profile_rescan";
  return "none";
}

export function activeTabOnDouyinProfile(activeTabUrl: string | null | undefined): boolean {
  const active = detectCurrentDouyinProfileIdentity(activeTabUrl);
  return active.page_type === "profile" || Boolean(active.canonical_profile_url?.includes("/user/"));
}

export function storedScannerSessionHasProgress(state: WholeProfileHarvestState): boolean {
  const snap = state.post_scan_counter_snapshot;
  if (snap?.status === "applied" && ((snap.already_collected ?? 0) > 0 || (snap.scanned_total ?? 0) > 0)) {
    return true;
  }
  const stored = detectCurrentDouyinProfileIdentity(state.profile_url, { sec_uid: state.classification.sec_uid });
  if (!stored.canonical_profile_url) return false;
  return state.profile_scan.status === "success" || state.scan_job.total_persisted > 0;
}

/** Keep tile/header presentation stable while a same-profile rescan is starting. */
export function shouldHoldScanPresentationForRescan(state: WholeProfileHarvestState): boolean {
  const snap = state.post_scan_counter_snapshot;
  if (snap?.status === "applied" && ((snap.scanned_total ?? 0) > 0 || (snap.queue ?? 0) > 0 || (snap.new ?? 0) > 0)) {
    return true;
  }
  if (state.profile_scan.status === "success" && (state.scan_job.total_persisted ?? 0) > 0) return true;
  return state.scan_job.status === "completed" && (state.scan_job.total_persisted ?? 0) > 0;
}

/** Gate stale "complete" tiles when saved work exists but the active tab is not a profile page. */
export function shouldGateScannerPanelForProfileContext(
  state: WholeProfileHarvestState,
  activeTabUrl: string | null | undefined
): boolean {
  if (detectProfileContextMismatch(state, activeTabUrl)) return true;
  if (!storedScannerSessionHasProgress(state)) return false;
  const tabUrl = typeof activeTabUrl === "string" ? activeTabUrl.trim() : "";
  if (!tabUrl) return false;
  return !activeTabOnDouyinProfile(tabUrl);
}

/** Snapshot claims collected videos but no stored profile URL anchors the session. */
export function orphanedPostCollectSnapshot(state: WholeProfileHarvestState): boolean {
  const snap = state.post_scan_counter_snapshot;
  if (snap?.status !== "applied" || (snap.already_collected ?? 0) <= 0) return false;
  const stored = detectCurrentDouyinProfileIdentity(state.profile_url, { sec_uid: state.classification.sec_uid });
  return !stored.canonical_profile_url;
}

export function deriveProfileContextViewModel(
  state: WholeProfileHarvestState,
  renderContext: ScannerControlPanelRenderContext,
  options?: { collectionRunning?: boolean }
): ProfileContextViewModel | null {
  const activeTabUrl = renderContext.active_tab_url ?? state.page_context.current_url ?? state.safety.tab_health.current_url ?? null;
  if (!shouldGateScannerPanelForProfileContext(state, activeTabUrl)) return null;

  const stored = detectCurrentDouyinProfileIdentity(state.profile_url, { sec_uid: state.classification.sec_uid });
  const active = detectCurrentDouyinProfileIdentity(activeTabUrl);
  const activeTabOnProfile = active.page_type === "profile" || Boolean(active.canonical_profile_url?.includes("/user/"));
  const storedProgress = storedProgressLabel(state);
  const activeSummary = renderContext.active_profile_inbox_summary ?? null;
  const collectionRunning = options?.collectionRunning === true;
  const previousProfile = humanStoredSessionLabel(storedProgress);

  let bannerMessage: string;
  if (collectionRunning) {
    bannerMessage = `Collection is still running on ${previousProfile}. Return to that Douyin tab or reset before working on this profile.`;
  } else if (!activeTabOnProfile) {
    bannerMessage = `Saved work is on ${previousProfile}. Open a Douyin profile tab to continue on another creator.`;
  } else if (activeSummary && activeProfileInboxSummaryIsComplete(activeSummary)) {
    bannerMessage = `You were working on ${previousProfile}. This creator has ${activeSummary.already_collected} videos collected in Capture Inbox.`;
  } else if (activeSummary && activeProfileInboxSummaryIsResumeEligible(activeSummary) && activeProfileInboxHasActionableWork(activeSummary)) {
    const remaining = profileContextCollectableRemaining(activeSummary);
    bannerMessage = `You were working on ${previousProfile}. After you scan, Capture Inbox may have ${activeSummary.already_collected} ready and ${remaining} left to collect for this creator.`;
  } else if (activeSummary && activeProfileInboxSummaryIsResumeEligible(activeSummary) && activeSummary.already_collected > 0) {
    bannerMessage = `You were working on ${previousProfile}. After you scan, Capture Inbox may have ${activeSummary.already_collected} ready videos for this creator.`;
  } else {
    bannerMessage = `You were working on ${previousProfile}. Scan this profile to discover videos and build a collection plan.`;
  }

  return {
    mismatch: true,
    active_tab_on_profile: activeTabOnProfile,
    stored_profile_url: stored.canonical_profile_url,
    stored_progress_label: storedProgress,
    active_profile_url: active.canonical_profile_url,
    active_profile_label: "this profile",
    active_inbox_summary: activeSummary,
    banner_message: bannerMessage,
    show_previous_inbox_link: Boolean(stored.canonical_profile_url && storedProgress),
    collection_running_on_stored_profile: collectionRunning
  };
}
