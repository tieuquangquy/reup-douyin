import { isHybridTailGapCollect } from "./hybridBackendGapAwemeIds.js";
import type { WholeProfileHarvestState } from "./state.js";

export const HYBRID_UNREACHABLE_TAIL_GAP_STOP_REASON = "gap_ids_unreachable_rescan_required" as const;
export const HYBRID_UNREACHABLE_TAIL_GAP_CLOSED_OUTCOME = "phase_4_4e_unreachable_tail_gap_closed" as const;
export const HYBRID_UNREACHABLE_TAIL_GAP_BLOCKED_REASON = "unreachable_tail_gap_offer_active" as const;

export type HybridTailGapPresentation = "none" | "unreachable_offer" | "closed";

const PROFILE_POST_EXHAUSTED_STOPS = new Set([
  "has_more_false",
  "pagination_exhausted",
  "discovery_exhausted",
  "extractor_no_targets",
  "extractor_no_targets_retry_failed",
  "page_fetch_message_failed",
  "no_profile_post_fetch",
  "scan_gap_empty"
]);

const DOM_UNREACHABLE_STOPS = new Set([
  "all_tail_reconcile_candidates_already_captured",
  "no_tail_reconcile_candidates"
]);

function summaryRecord(state: WholeProfileHarvestState): Record<string, unknown> {
  return state.debug.last_response_summary && typeof state.debug.last_response_summary === "object"
    ? state.debug.last_response_summary as Record<string, unknown>
    : {};
}

export function isHybridTailGapClosed(state: WholeProfileHarvestState): boolean {
  const presentation = state.hybrid_tail_gap_presentation;
  const summary = summaryRecord(state);
  const explicitlyClosed = presentation === "closed"
    || summary.hybrid_unreachable_tail_gap_closed === "yes"
    || summary.hybrid_runner_outcome === HYBRID_UNREACHABLE_TAIL_GAP_CLOSED_OUTCOME;
  if (!explicitlyClosed) return false;
  const snap = state.post_scan_counter_snapshot;
  const snapGap = snap?.status === "applied" ? Math.max(0, snap.new) + Math.max(0, snap.queue) : 0;
  const summaryTileNew = numericField(summary.hybrid_runner_post_run_tile_new);
  if (snapGap > 0 || (summaryTileNew != null && summaryTileNew > 0)) {
    return false;
  }
  return true;
}

/** True when operator closed or unreachable offer is active — inbox refresh must not reinflate gap. */
export function isHybridTailGapAuthorityLocked(state: WholeProfileHarvestState): boolean {
  return isHybridTailGapClosed(state) || isHybridUnreachableTailGapOffer(state);
}

export function isHybridTailGapCollectBlocked(
  state: WholeProfileHarvestState,
  fossil?: Record<string, unknown> | null
): boolean {
  if (isHybridTailGapAuthorityLocked(state)) return true;
  const summary = summaryRecord(state);
  const remaining = resolveUnreachableTailGapRemaining(state);
  if (isHybridTailGapCollect(remaining) && isProvenUnreachableTailGapEvidence(summary)) return true;
  if (fossil && isHybridTailGapCollect(remaining) && isProvenUnreachableTailGapEvidence(fossil)) return true;
  const fossilRemaining = numericField(fossil?.hybrid_tail_gap_live_remaining)
    ?? numericField(fossil?.hybrid_runner_post_run_tile_new);
  if (fossil && isHybridTailGapCollect(fossilRemaining ?? 0) && isProvenUnreachableTailGapEvidence(fossil)) {
    return true;
  }
  return false;
}

export function getHybridTailGapPresentation(state: WholeProfileHarvestState): HybridTailGapPresentation {
  const explicit = state.hybrid_tail_gap_presentation;
  if (explicit === "unreachable_offer") return "unreachable_offer";
  if (explicit === "closed" && isHybridTailGapClosed(state)) return "closed";
  const summary = summaryRecord(state);
  if (isHybridTailGapClosed(state)) return "closed";
  if (summary.hybrid_unreachable_tail_gap_closed === "yes") return "closed";
  if (summary.hybrid_runner_outcome === HYBRID_UNREACHABLE_TAIL_GAP_CLOSED_OUTCOME) return "closed";
  if (isProvenUnreachableTailGapEvidence(summary) && isHybridTailGapCollect(resolveUnreachableTailGapRemaining(state))) {
    return "unreachable_offer";
  }
  return "none";
}

export function resolveHybridTailGapClosedAlready(state: WholeProfileHarvestState): number {
  const snap = state.post_scan_counter_snapshot;
  const summary = summaryRecord(state);
  return Math.max(
    snap?.status === "applied" ? snap.already_collected ?? 0 : 0,
    numericField(summary.hybrid_runner_post_run_tile_already) ?? 0,
    numericField(summary.hybrid_runner_post_run_backend_captured) ?? 0,
    state.target_status.complete,
    state.harvest.updated
  );
}

export function resolveHybridTailGapClosedCount(state: WholeProfileHarvestState): number {
  const summary = summaryRecord(state);
  return Math.max(
    0,
    numericField(summary.hybrid_unreachable_tail_gap_closed_count) ?? 0,
    numericField(scanDiagnosticsRecord(state).hybrid_unreachable_gap_closed_count) ?? 0
  );
}

function scanDiagnosticsRecord(state: WholeProfileHarvestState): Record<string, unknown> {
  return state.profile_scan.diagnostics && typeof state.profile_scan.diagnostics === "object"
    ? state.profile_scan.diagnostics as Record<string, unknown>
    : {};
}

/** Rehydrate durable presentation from persisted summary/fossil on popup reopen. */
export function hydrateHybridTailGapPresentationFromDiagnostics(
  state: WholeProfileHarvestState
): WholeProfileHarvestState {
  const current = state.hybrid_tail_gap_presentation;
  if (current === "unreachable_offer") return state;
  if (current === "closed" && isHybridTailGapClosed(state)) return state;
  if (isHybridTailGapClosed(state)) {
    return { ...state, hybrid_tail_gap_presentation: "closed" };
  }
  if (isHybridUnreachableTailGapOffer(state)) {
    return applyUnreachableTailGapOfferToState(state);
  }
  const summary = summaryRecord(state);
  if (isProvenUnreachableTailGapEvidence(summary) && isHybridTailGapCollect(resolveUnreachableTailGapRemaining(state))) {
    return applyUnreachableTailGapOfferToState(state);
  }
  return state;
}

export function clearHybridTailGapPresentationForRescan(state: WholeProfileHarvestState): WholeProfileHarvestState {
  if (getHybridTailGapPresentation(state) === "none") return state;
  const summary = summaryRecord(state);
  return {
    ...state,
    hybrid_tail_gap_presentation: "none",
    debug: {
      ...state.debug,
      last_response_summary: {
        ...summary,
        hybrid_unreachable_tail_gap_offer: null,
        hybrid_unreachable_tail_gap_closed: null,
        hybrid_tail_gap_discovery_stop_reason: null,
        hybrid_tail_gap_live_remaining: null,
        hybrid_runner_post_run_tile_new: null
      }
    }
  };
}

/** Persist durable unreachable-offer authority (popup reopen + workflow routing). */
export function applyUnreachableTailGapOfferToState(
  state: WholeProfileHarvestState,
  at = state.updated_at
): WholeProfileHarvestState {
  const remaining = resolveUnreachableTailGapRemaining(state);
  const summary = summaryRecord(state);
  const upgraded = upgradeUnreachableTailGapDiscoveryDiagnostics({
    ...summary,
    hybrid_tail_gap_discovery_stop_reason: HYBRID_UNREACHABLE_TAIL_GAP_STOP_REASON,
    hybrid_unreachable_tail_gap_offer: "yes",
    hybrid_tail_gap_discovery_found: numericField(summary.hybrid_tail_gap_discovery_found) ?? 0,
    hybrid_tail_gap_live_remaining: remaining,
    hybrid_runner_post_run_tile_new: remaining
  });
  return {
    ...state,
    hybrid_tail_gap_presentation: "unreachable_offer",
    updated_at: at,
    debug: {
      ...state.debug,
      last_response_summary: upgraded
    }
  };
}

function numericField(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) return Math.max(0, Math.round(value));
  if (typeof value === "string" && value.trim()) {
    const parsed = Number(value);
    if (Number.isFinite(parsed)) return Math.max(0, Math.round(parsed));
  }
  return null;
}

/**
 * Proven unreachable: canonical stop, or profile-post exhausted + DOM only sees
 * already-captured / no candidates + discovery found 0 (operator 736/739 fossil).
 */
export function isProvenUnreachableTailGapEvidence(record: Record<string, unknown> | null | undefined): boolean {
  if (!record || typeof record !== "object") return false;
  if (record.hybrid_unreachable_tail_gap_closed === "yes") return false;
  if (record.hybrid_unreachable_tail_gap_offer === "yes") return true;
  if (String(record.hybrid_tail_gap_discovery_stop_reason ?? "") === HYBRID_UNREACHABLE_TAIL_GAP_STOP_REASON) {
    return true;
  }
  const found = numericField(record.hybrid_tail_gap_discovery_found)
    ?? numericField(record.hybrid_tail_gap_tail_reconcile_found);
  if (found != null && found > 0) return false;
  const profileStop = String(record.hybrid_tail_gap_discovery_stop_reason ?? "");
  const reconcileStop = String(record.hybrid_tail_gap_tail_reconcile_stop_reason ?? "");
  return PROFILE_POST_EXHAUSTED_STOPS.has(profileStop) && DOM_UNREACHABLE_STOPS.has(reconcileStop);
}

export function upgradeUnreachableTailGapDiscoveryDiagnostics(
  diagnostics: Record<string, unknown>
): Record<string, unknown> {
  if (!isProvenUnreachableTailGapEvidence(diagnostics)) return diagnostics;
  if (String(diagnostics.hybrid_tail_gap_discovery_stop_reason ?? "") === HYBRID_UNREACHABLE_TAIL_GAP_STOP_REASON
    && diagnostics.hybrid_unreachable_tail_gap_offer === "yes") {
    return diagnostics;
  }
  return {
    ...diagnostics,
    hybrid_tail_gap_discovery_stop_reason: HYBRID_UNREACHABLE_TAIL_GAP_STOP_REASON,
    hybrid_unreachable_tail_gap_offer: "yes",
    hybrid_tail_gap_operator_hint:
      typeof diagnostics.hybrid_tail_gap_operator_hint === "string" && diagnostics.hybrid_tail_gap_operator_hint.trim()
        ? diagnostics.hybrid_tail_gap_operator_hint
        : "Scan Profile again on this Douyin tab, then Collect remaining. Profile-post and DOM did not yield the missing IDs."
  };
}

/** Remaining count shown as a small tail gap (1–25) with empty actionable queue. */
export function resolveUnreachableTailGapRemaining(state: WholeProfileHarvestState): number {
  const summary = summaryRecord(state);
  const candidates = [
    numericField(summary.hybrid_tail_gap_live_remaining),
    numericField(summary.hybrid_runner_post_run_tile_new),
    state.post_scan_counter_snapshot?.status === "applied" ? state.post_scan_counter_snapshot.new : null,
    state.post_scan_counter_snapshot?.status === "applied" ? state.post_scan_counter_snapshot.queue : null
  ];
  for (const value of candidates) {
    if (value != null && isHybridTailGapCollect(value)) return value;
  }
  return 0;
}

export function isHybridUnreachableTailGapOffer(state: WholeProfileHarvestState): boolean {
  const presentation = getHybridTailGapPresentation(state);
  if (presentation === "closed") return false;
  const remaining = resolveUnreachableTailGapRemaining(state);
  if (!isHybridTailGapCollect(remaining)) return false;
  const summary = summaryRecord(state);
  // Proven unreachable / durable presentation wins over phantom tail-gap queue rows.
  if (presentation === "unreachable_offer") return true;
  if (isProvenUnreachableTailGapEvidence(summary)) return true;
  if (String(summary.start_collecting_blocked_reason ?? "") === HYBRID_UNREACHABLE_TAIL_GAP_BLOCKED_REASON) {
    return true;
  }
  const actionable = state.harvest.queue.filter((item) =>
    item.status === "new"
    || item.status === "pending"
    || item.status === "needs_metadata"
    || item.status === "incomplete"
    || item.status === "retry"
    || item.status === "failed_recoverable"
  ).length;
  if (actionable > 0) return false;
  return false;
}

/**
 * When a prior run already proved the tail gap unreachable, skip profile-post / DOM
 * rediscovery so Collect does not hang on "Collecting 736/739".
 */
export function shouldSkipTailGapRediscovery(args: {
  state: WholeProfileHarvestState;
  remaining: number;
  fossil?: Record<string, unknown> | null;
}): boolean {
  if (!isHybridTailGapCollect(args.remaining)) return false;
  const summary = summaryRecord(args.state);
  if (summary.hybrid_unreachable_tail_gap_closed === "yes") return false;
  if (isProvenUnreachableTailGapEvidence(summary)) return true;
  if (args.fossil && isProvenUnreachableTailGapEvidence(args.fossil)) return true;
  return false;
}

export function buildUnreachableTailGapSkipDiscoveryDiagnostics(remaining: number): Record<string, unknown> {
  const safe = Math.max(0, Math.round(remaining));
  return {
    hybrid_tail_gap_discovery_attempted: "skipped_already_unreachable",
    hybrid_tail_gap_discovery_stop_reason: HYBRID_UNREACHABLE_TAIL_GAP_STOP_REASON,
    hybrid_tail_gap_discovery_found: 0,
    hybrid_tail_gap_live_remaining: safe,
    hybrid_tail_gap_rediscovery_skipped: "yes",
    hybrid_unreachable_tail_gap_offer: "yes",
    hybrid_tail_gap_operator_hint:
      "Prior collect already proved these IDs unreachable. Close the gap or Scan Profile again — rediscovery was skipped."
  };
}

/** Merge fossil discovery stop into state so UI can offer Close without another Collect click. */
export function mergeUnreachableTailGapFossilIntoState(
  state: WholeProfileHarvestState,
  fossil: Record<string, unknown> | null | undefined
): WholeProfileHarvestState {
  if (!fossil || typeof fossil !== "object") return state;
  if (!isProvenUnreachableTailGapEvidence(fossil)) return state;
  const summary = summaryRecord(state);
  if (summary.hybrid_unreachable_tail_gap_closed === "yes") return state;
  const liveRemaining = numericField(fossil.hybrid_tail_gap_live_remaining)
    ?? numericField(fossil.hybrid_runner_post_run_tile_new)
    ?? resolveUnreachableTailGapRemaining(state);
  const alreadyHasStop = String(summary.hybrid_tail_gap_discovery_stop_reason ?? "") === HYBRID_UNREACHABLE_TAIL_GAP_STOP_REASON;
  const alreadyHasOffer = summary.hybrid_unreachable_tail_gap_offer === "yes";
  if (alreadyHasStop && alreadyHasOffer) {
    if (!isHybridTailGapCollect(liveRemaining) || numericField(summary.hybrid_tail_gap_live_remaining) != null) {
      return state;
    }
  }
  return {
    ...state,
    hybrid_tail_gap_presentation: "unreachable_offer",
    debug: {
      ...state.debug,
      last_response_summary: {
        ...summary,
        hybrid_tail_gap_tail_reconcile_stop_reason:
          fossil.hybrid_tail_gap_tail_reconcile_stop_reason
          ?? summary.hybrid_tail_gap_tail_reconcile_stop_reason
          ?? null,
        hybrid_tail_gap_discovery_found:
          numericField(fossil.hybrid_tail_gap_discovery_found)
          ?? numericField(summary.hybrid_tail_gap_discovery_found)
          ?? 0,
        hybrid_tail_gap_discovery_stop_reason: HYBRID_UNREACHABLE_TAIL_GAP_STOP_REASON,
        hybrid_unreachable_tail_gap_offer: "yes",
        ...(isHybridTailGapCollect(liveRemaining)
          ? { hybrid_tail_gap_live_remaining: liveRemaining, hybrid_runner_post_run_tile_new: liveRemaining }
          : {})
      }
    }
  };
}

export type HybridUnreachableTailGapUi = {
  remaining: number;
  title: string;
  description: string;
  buttonLabel: string;
};

export type HybridTailGapClosedCompleteUi = {
  already: number;
  closedCount: number;
  title: string;
  description: string;
  buttonLabel: string;
};

export function buildHybridTailGapClosedCompleteUi(
  already: number,
  closedCount: number
): HybridTailGapClosedCompleteUi {
  const safeAlready = Math.max(0, Math.round(already));
  const safeClosed = Math.max(0, Math.round(closedCount));
  const gapNote = safeClosed > 0
    ? ` ${safeClosed} unreachable ID(s) were closed — they are not in Capture Inbox.`
    : "";
  return {
    already: safeAlready,
    closedCount: safeClosed,
    title: "Profile collection complete",
    description: `${safeAlready} video(s) in Capture Inbox.${gapNote} Open Capture Inbox to review.`,
    buttonLabel: "Open Capture Inbox"
  };
}

export function buildHybridUnreachableTailGapUi(remaining: number): HybridUnreachableTailGapUi {
  const safe = Math.max(0, Math.round(remaining));
  return {
    remaining: safe,
    title: "Close unreachable gap",
    description: `${safe} video ID(s) could not be found on Douyin (scan/API/DOM). Close the gap to finish with the ${safe === 1 ? "video" : "videos"} already in Capture Inbox.`,
    buttonLabel: safe === 1 ? "Close 1 unreachable" : `Close ${safe} unreachable`
  };
}

/**
 * Align local tile authority to inbox captured count and clear the phantom tail gap.
 * Does not invent aweme_ids or write fake Capture Inbox items.
 */
export function applyClosedUnreachableTailGapToState(
  state: WholeProfileHarvestState,
  at: string,
  remaining: number
): WholeProfileHarvestState {
  const prior = state.post_scan_counter_snapshot;
  const already = Math.max(
    prior?.already_collected ?? 0,
    prior?.backend_captured ?? 0,
    numericField(summaryRecord(state).hybrid_runner_post_run_tile_already) ?? 0,
    numericField(summaryRecord(state).hybrid_runner_post_run_backend_captured) ?? 0
  );
  const scannedAligned = already;
  const scanDiagnostics = state.profile_scan.diagnostics && typeof state.profile_scan.diagnostics === "object"
    ? { ...(state.profile_scan.diagnostics as Record<string, unknown>) }
    : {};
  scanDiagnostics.displayed_profile_count = already;
  scanDiagnostics.expected_profile_video_count = already;
  scanDiagnostics.hybrid_unreachable_gap_closed_at = at;
  scanDiagnostics.hybrid_unreachable_gap_closed_count = Math.max(0, Math.round(remaining));

  const closedCount = Math.max(0, Math.round(remaining));
  const closedSummaryPatch = {
    hybrid_unreachable_tail_gap_closed: "yes",
    hybrid_unreachable_tail_gap_closed_at: at,
    hybrid_unreachable_tail_gap_closed_count: closedCount,
    hybrid_tail_gap_live_remaining: 0,
    hybrid_runner_post_run_tile_new: 0,
    hybrid_runner_post_run_tile_already: already,
    hybrid_runner_post_run_backend_captured: already,
    hybrid_exact_tail_gap_mode: "closed_unreachable",
    hybrid_force_exact_tail_gap_collect: "no",
    hybrid_collector_completed: "yes",
    hybrid_runner_outcome: HYBRID_UNREACHABLE_TAIL_GAP_CLOSED_OUTCOME,
    hybrid_runner_probe_step: HYBRID_UNREACHABLE_TAIL_GAP_CLOSED_OUTCOME,
    hybrid_runner_loop_phase: "closed_unreachable",
    hybrid_tail_gap_discovery_stop_reason: HYBRID_UNREACHABLE_TAIL_GAP_STOP_REASON
  };

  return {
    ...state,
    status: "harvest_ready",
    phase: "completed",
    hybrid_tail_gap_presentation: "closed",
    profile_scan: {
      ...state.profile_scan,
      diagnostics: scanDiagnostics
    },
    post_scan_counter_snapshot: {
      status: "applied",
      source: "backend_capture_inbox_profile_summary",
      profile_identifier: prior?.profile_identifier
        ?? state.scan_job.profile_identifier
        ?? state.profile_url
        ?? "unknown",
      scanned_total: scannedAligned,
      backend_captured_aweme_ids: prior?.backend_captured_aweme_ids ?? [],
      backend_captured: Math.max(prior?.backend_captured ?? 0, already),
      backend_ready: Math.max(prior?.backend_ready ?? 0, already),
      backend_dup: prior?.backend_dup ?? 0,
      backend_fail: prior?.backend_fail ?? 0,
      already_collected: already,
      incomplete: 0,
      need_retry: 0,
      new: 0,
      queue: 0,
      applied_at: at
    },
    harvest: {
      ...state.harvest,
      pending: 0,
      planned_total: already,
      updated_at: at
    },
    debug: {
      ...state.debug,
      last_response_summary: {
        ...summaryRecord(state),
        ...closedSummaryPatch
      }
    },
    updated_at: at
  };
}
