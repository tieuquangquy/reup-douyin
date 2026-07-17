import {
  resolveBackendCapturedCountFromState,
  resolveScannedTotalFromState,
  mergeScanAuthorityDiagnostics
} from "./backendCollectAuthority.js";
import {
  filterQueueToDisplayedProfileCollectScope,
  resolveDisplayedProfileVideoLimit
} from "./displayedProfileQueueCap.js";
import { evidenceIsHybridFlushReady } from "./hybridHydration.js";
import type { PostScanCounterSnapshot, WholeProfileHarvestState } from "./state.js";

export type ProfileCollectContract = {
  profile_identifier: string | null;
  displayed_total: number;
  collectable_total: number;
  api_discovered: number | null;
  api_extra_count: number;
  captured: number;
  pending_hydration: number;
  uncollectable: number;
  failed: number;
  new_count: number;
  queue_count: number;
  incomplete_count: number;
};

function numericDiagnostic(value: unknown, fallback = 0): number {
  if (typeof value === "number" && Number.isFinite(value)) return Math.max(0, Math.round(value));
  if (typeof value === "string" && value.trim()) {
    const parsed = Number(value);
    if (Number.isFinite(parsed)) return Math.max(0, Math.round(parsed));
  }
  return fallback;
}

function isCollectableQueueItem(item: {
  status?: string;
  capture_status?: string;
}): boolean {
  const status = String(item.status ?? "");
  if (
    status === "already_collected"
    || status === "backend_verified"
    || status === "complete"
    || status === "extracted"
    || status === "skipped"
    || status === "duplicate"
  ) {
    return false;
  }
  if (item.capture_status === "complete" || item.capture_status === "skipped") return false;
  return true;
}

/** Count in-scope queue rows that still need metrics before backend flush. */
export function countPendingHydrationInScopedQueue<
  T extends { aweme_id: string; status?: string; capture_status?: string; profile_card_evidence?: Record<string, unknown> | null }
>(queue: readonly T[], diagnostics: Record<string, unknown>): number {
  const scoped = filterQueueToDisplayedProfileCollectScope(queue, diagnostics);
  return scoped.filter((item) =>
    isCollectableQueueItem(item)
    && !evidenceIsHybridFlushReady(item.profile_card_evidence)
    && item.profile_card_evidence?.hybrid_uncollectable !== true
  ).length;
}

export function countUncollectableInScopedQueue<
  T extends { aweme_id: string; status?: string; capture_status?: string; profile_card_evidence?: Record<string, unknown> | null }
>(queue: readonly T[], diagnostics: Record<string, unknown>): number {
  const scoped = filterQueueToDisplayedProfileCollectScope(queue, diagnostics);
  return scoped.filter((item) =>
    isCollectableQueueItem(item) && item.profile_card_evidence?.hybrid_uncollectable === true
  ).length;
}

/**
 * Single profile-wide contract for scan, collect progress, popup tiles, and snapshots.
 * Operator scope is displayed profile count only — API extras are forensic only.
 */
export function buildProfileCollectContractFromState(state: WholeProfileHarvestState): ProfileCollectContract {
  const diagnostics = mergeScanAuthorityDiagnostics(state);
  const snap = state.post_scan_counter_snapshot;
  const displayedLimit = resolveDisplayedProfileVideoLimit(diagnostics);
  const scanAuthorityTotal = resolveScannedTotalFromState(state);
  const displayedTotal = displayedLimit ?? scanAuthorityTotal;

  const apiDiscovered = numericDiagnostic(
    diagnostics.api_collectable_count
      ?? diagnostics.api_discovered_count_before_cap
      ?? diagnostics.final_cumulative_collectable_count
      ?? diagnostics.collectable_count,
    0
  ) || null;
  const apiExtraCount = displayedLimit != null && apiDiscovered != null && apiDiscovered > displayedLimit
    ? apiDiscovered - displayedLimit
    : numericDiagnostic(diagnostics.over_displayed_count, 0);

  const captured = Math.max(
    resolveBackendCapturedCountFromState(state),
    snap?.status === "applied" ? numericDiagnostic(snap.already_collected) : 0
  );
  const failed = snap?.status === "applied" ? numericDiagnostic(snap.need_retry ?? snap.backend_fail) : 0;

  const pendingHydration = countPendingHydrationInScopedQueue(state.harvest.queue, diagnostics);
  const uncollectable = countUncollectableInScopedQueue(state.harvest.queue, diagnostics);

  const newCount = Math.max(0, displayedTotal - captured - uncollectable);
  const queueCount = Math.max(0, displayedTotal - captured);
  const incompleteCount = pendingHydration + uncollectable;

  return {
    profile_identifier: snap?.profile_identifier ?? null,
    displayed_total: displayedTotal,
    collectable_total: displayedTotal,
    api_discovered: apiDiscovered,
    api_extra_count: apiExtraCount,
    captured,
    pending_hydration: pendingHydration,
    uncollectable,
    failed,
    new_count: newCount,
    queue_count: queueCount,
    incomplete_count: incompleteCount
  };
}

/** Rebuild post-scan snapshot counters from PCC (fixes 3382 vs 3304 tile drift). */
export function applyProfileCollectContractToPostScanSnapshot(
  snapshot: PostScanCounterSnapshot,
  contract: ProfileCollectContract
): PostScanCounterSnapshot {
  const captured = Math.max(0, contract.captured);
  const newCount = Math.max(0, contract.displayed_total - captured);
  return {
    ...snapshot,
    scanned_total: contract.displayed_total,
    already_collected: captured,
    backend_captured: snapshot.backend_captured ?? captured,
    new: newCount,
    queue: newCount,
    incomplete: contract.incomplete_count
  };
}

export function resolveEffectiveScannedTotalForSnapshot(
  diagnostics: Record<string, unknown>,
  queueLength: number
): number {
  const displayed = resolveDisplayedProfileVideoLimit(diagnostics);
  if (displayed != null && displayed > 0) return displayed;
  return Math.max(0, queueLength);
}
