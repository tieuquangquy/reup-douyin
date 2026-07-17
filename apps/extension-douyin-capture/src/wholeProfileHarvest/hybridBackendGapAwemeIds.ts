import {
  createProfileTargetRepository,
  profileIdentifierFromUrl,
  type ProfileTargetRepository
} from "./profileTargetRepository.js";
import type { WholeProfileHarvestState, WholeProfileHarvestQueueStatus } from "./state.js";

export const HYBRID_EXACT_GAP_RECOVERY_CAP = 25;

export function isHybridTailGapCollect(remaining: number): boolean {
  const safe = Math.max(0, Math.round(remaining));
  return safe > 0 && safe <= HYBRID_EXACT_GAP_RECOVERY_CAP;
}

export function normalizeAwemeIdForBackendGap(value: string | null | undefined): string | null {
  const trimmed = typeof value === "string" ? value.trim() : "";
  return /^\d+$/.test(trimmed) ? trimmed : null;
}

export function collectKnownScannedAwemeIds(state: WholeProfileHarvestState): string[] {
  const seen = new Set<string>();
  const ordered: string[] = [];
  const add = (raw: string | null | undefined): void => {
    const normalized = normalizeAwemeIdForBackendGap(raw);
    if (!normalized || seen.has(normalized)) return;
    seen.add(normalized);
    ordered.push(normalized);
  };
  for (const id of state.classification.collect_aweme_ids) add(id);
  for (const target of state.classification.targets) add(target.aweme_id);
  for (const detail of state.profile_scan.target_details) add(detail.aweme_id);
  for (const id of state.profile_scan.targets ?? []) add(id);
  return ordered;
}

export function diffAwemeIdsMissingFromCaptured(
  scannedIds: readonly string[],
  capturedIds: ReadonlySet<string>,
  limit: number
): string[] {
  const capped = Math.max(0, Math.round(limit));
  if (capped <= 0) return [];
  const found: string[] = [];
  const seen = new Set<string>();
  for (const raw of scannedIds) {
    const normalized = normalizeAwemeIdForBackendGap(raw);
    if (!normalized || seen.has(normalized) || capturedIds.has(normalized)) continue;
    seen.add(normalized);
    found.push(normalized);
    if (found.length >= capped) break;
  }
  return found;
}

/** Tail-gap collect should target the last profile videos missing from inbox, not the first stale diff window. */
export function diffAwemeIdsMissingFromCapturedTailFirst(
  scannedIds: readonly string[],
  capturedIds: ReadonlySet<string>,
  limit: number
): string[] {
  const capped = Math.max(0, Math.round(limit));
  if (capped <= 0) return [];
  const found: string[] = [];
  const seen = new Set<string>();
  for (let index = scannedIds.length - 1; index >= 0; index -= 1) {
    const normalized = normalizeAwemeIdForBackendGap(scannedIds[index]);
    if (!normalized || seen.has(normalized) || capturedIds.has(normalized)) continue;
    seen.add(normalized);
    found.unshift(normalized);
    if (found.length >= capped) break;
  }
  return found;
}

function numericTailGapCandidate(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) return Math.max(0, Math.round(value));
  if (typeof value === "string" && value.trim()) {
    const parsed = Number(value);
    if (Number.isFinite(parsed)) return Math.max(0, Math.round(parsed));
  }
  return null;
}

export function tailGapFromFossilRecord(record: Record<string, unknown>): number | null {
  const tileNew = numericTailGapCandidate(record.hybrid_runner_post_run_tile_new);
  if (tileNew != null) {
    return isHybridTailGapCollect(tileNew) ? tileNew : null;
  }
  const liveRemaining = numericTailGapCandidate(record.hybrid_tail_gap_live_remaining);
  if (liveRemaining != null && isHybridTailGapCollect(liveRemaining)) return liveRemaining;
  return null;
}

/** Profile total shown on Douyin minus inbox captured — no tail-gap cap. */
export function resolveHybridDisplayedProfileCollectGapUncapped(state: WholeProfileHarvestState): number {
  const summary = state.debug.last_response_summary && typeof state.debug.last_response_summary === "object"
    ? state.debug.last_response_summary as Record<string, unknown>
    : {};
  const scanDiagnostics = state.profile_scan?.diagnostics && typeof state.profile_scan.diagnostics === "object"
    ? state.profile_scan.diagnostics as Record<string, unknown>
    : {};
  const displayed = Math.max(
    numericTailGapCandidate(scanDiagnostics.displayed_profile_count) ?? 0,
    numericTailGapCandidate(scanDiagnostics.expected_profile_video_count) ?? 0,
    numericTailGapCandidate(summary.post_scan_scanned_total_count) ?? 0,
    state.post_scan_counter_snapshot?.scanned_total ?? 0
  );
  if (displayed <= 0) return 0;
  const captured = Math.max(
    state.post_scan_counter_snapshot?.backend_captured ?? 0,
    state.post_scan_counter_snapshot?.already_collected ?? 0,
    numericTailGapCandidate(summary.hybrid_runner_post_run_backend_captured) ?? 0
  );
  return Math.max(0, displayed - captured);
}

export function resolveHybridOperatorCollectBacklog(
  state: WholeProfileHarvestState,
  fossilRecord: Record<string, unknown> = {}
): number {
  const summary = state.debug.last_response_summary && typeof state.debug.last_response_summary === "object"
    ? state.debug.last_response_summary as Record<string, unknown>
    : {};
  const snap = state.post_scan_counter_snapshot;
  return Math.max(
    numericTailGapCandidate(fossilRecord.hybrid_runner_post_run_tile_new) ?? 0,
    numericTailGapCandidate(summary.hybrid_runner_post_run_tile_new) ?? 0,
    snap?.new ?? 0,
    snap?.queue ?? 0,
    resolveHybridDisplayedProfileCollectGapUncapped(state),
    snap
      ? Math.max(
        0,
        Math.max(snap.scanned_total ?? 0, state.classification.total_candidates ?? 0)
          - Math.max(snap.backend_captured ?? 0, snap.already_collected ?? 0)
      )
      : 0
  );
}

export function resolveHybridExactTailGapCandidate(
  state: WholeProfileHarvestState,
  fossilRecord: Record<string, unknown> = {}
): number | null {
  if (resolveHybridOperatorCollectBacklog(state, fossilRecord) > HYBRID_EXACT_GAP_RECOVERY_CAP) {
    return null;
  }
  return tailGapFromFossilRecord(fossilRecord)
    ?? tailGapFromFossilRecord(
      state.debug.last_response_summary && typeof state.debug.last_response_summary === "object"
        ? state.debug.last_response_summary as Record<string, unknown>
        : {}
    )
    ?? resolveHybridOperatorVisibleTailGap(state);
}

/** Profile total shown on Douyin minus inbox captured — survives inbox refresh that zeros tile_new. */
export function resolveHybridDisplayedProfileTailGap(state: WholeProfileHarvestState): number | null {
  const gap = resolveHybridDisplayedProfileCollectGapUncapped(state);
  return isHybridTailGapCollect(gap) ? gap : null;
}

export function resolveHybridCollectTailGapHint(
  state: WholeProfileHarvestState,
  fossilRecord: Record<string, unknown> = {}
): number | null {
  return resolveHybridExactTailGapCandidate(state, fossilRecord);
}

/** UI-visible tail gap (post-run tiles, live tail authority) when snapshot.new is still inflated. */
export function resolveHybridOperatorVisibleTailGap(state: WholeProfileHarvestState): number | null {
  if (resolveHybridOperatorCollectBacklog(state) > HYBRID_EXACT_GAP_RECOVERY_CAP) {
    return null;
  }
  const summary = state.debug.last_response_summary && typeof state.debug.last_response_summary === "object"
    ? state.debug.last_response_summary as Record<string, unknown>
    : {};
  const snap = state.post_scan_counter_snapshot;
  const candidates = [
    numericTailGapCandidate(summary.hybrid_runner_post_run_tile_new),
    numericTailGapCandidate(summary.hybrid_tail_gap_live_remaining),
    resolveHybridDisplayedProfileTailGap(state),
    snap?.new,
    snap?.queue,
    snap
      ? Math.max(
        0,
        Math.max(snap.scanned_total ?? 0, state.classification.total_candidates ?? 0)
          - Math.max(snap.backend_captured ?? 0, snap.already_collected ?? 0)
      )
      : null
  ];
  for (const value of candidates) {
    if (value != null && isHybridTailGapCollect(value)) return value;
  }
  return null;
}

const ALL_REPOSITORY_STATUSES: WholeProfileHarvestQueueStatus[] = [
  "new",
  "pending",
  "needs_metadata",
  "skipped",
  "retry",
  "incomplete",
  "failed_recoverable",
  "already_collected",
  "complete",
  "extracted",
  "backend_verified",
  "failed_permanent",
  "duplicate"
];

export async function listAllRepositoryAwemeIds(
  profileIdentifier: string,
  repository: ProfileTargetRepository = createProfileTargetRepository()
): Promise<string[]> {
  const countResult = await repository.countProfileTargets(profileIdentifier, ALL_REPOSITORY_STATUSES).catch(() => null);
  const total = countResult?.total ?? 0;
  if (total <= 0) return [];
  const pageSize = 500;
  const ids: string[] = [];
  const seen = new Set<string>();
  for (let offset = 0; offset < total; offset += pageSize) {
    const window = await repository.getProfileTargetsByStatus(
      profileIdentifier,
      ALL_REPOSITORY_STATUSES,
      Math.min(pageSize, total - offset),
      offset
    ).catch(() => null);
    if (!window) break;
    for (const record of window.records) {
      const normalized = normalizeAwemeIdForBackendGap(record.aweme_id);
      if (!normalized || seen.has(normalized)) continue;
      seen.add(normalized);
      ids.push(normalized);
    }
  }
  return ids;
}

export function queueMatchesExactGapAwemeIds(
  queueAwemeIds: readonly string[],
  exactGapIds: readonly string[]
): boolean {
  if (exactGapIds.length === 0) return false;
  const queueSet = new Set<string>();
  for (const raw of queueAwemeIds) {
    const normalized = normalizeAwemeIdForBackendGap(raw);
    if (normalized) queueSet.add(normalized);
  }
  if (queueSet.size !== exactGapIds.length) return false;
  return exactGapIds.every((id) => queueSet.has(id));
}

/** Reopen skipped/already-collected rows so tail-gap rebuild stays actionable. */
export type ExactTailGapQueueItem = {
  aweme_id: string;
  status: string;
  capture_status?: string;
};

/** Actionable harvest rows that match the exact backend tail-gap aweme_ids. */
export function filterExactTailGapActionableTargets<T extends ExactTailGapQueueItem>(
  queue: readonly T[],
  exactGapIds: readonly string[],
  isActionable: (item: T) => boolean
): T[] {
  const exactGapSet = new Set(
    exactGapIds
      .map((id) => normalizeAwemeIdForBackendGap(id))
      .filter((id): id is string => Boolean(id))
  );
  if (exactGapSet.size === 0) return [];
  return queue.filter((item) => {
    const normalized = normalizeAwemeIdForBackendGap(item.aweme_id);
    return normalized != null && exactGapSet.has(normalized) && isActionable(item);
  });
}

/** True when nuclear tail-gap mode knows exact IDs but none are queued for this run. */
export function shouldExactTailGapPreSkipFail(args: {
  hybridExactTailGapActive: boolean;
  exactGapIds: readonly string[];
  preSkipPending: number;
  profileRemaining: number;
}): boolean {
  return args.hybridExactTailGapActive
    && args.exactGapIds.length > 0
    && args.preSkipPending === 0
    && args.profileRemaining > 0;
}

/**
 * Select one collect row per exact backend gap ID. Bypasses displayed-profile queue
 * cap — tail-gap IDs are already backend-authoritative. Reopens skipped rows and
 * synthesizes stubs when a gap ID is missing from the visible queue.
 */
export function selectExactTailGapCollectTargets<T extends ExactTailGapQueueItem>(
  queue: readonly T[],
  exactGapIds: readonly string[],
  isActionable: (item: T) => boolean,
  createStub: (awemeId: string, index: number) => T
): T[] {
  const byId = new Map<string, T>();
  for (const item of queue) {
    const normalized = normalizeAwemeIdForBackendGap(item.aweme_id);
    if (normalized) byId.set(normalized, item);
  }
  const selected: T[] = [];
  for (let index = 0; index < exactGapIds.length; index++) {
    const awemeId = exactGapIds[index]!;
    const normalized = normalizeAwemeIdForBackendGap(awemeId);
    const base = normalized && byId.has(normalized) ? byId.get(normalized)! : createStub(awemeId, index);
    const reopened = reopenTailGapQueueItemForCollect(base);
    if (isActionable(reopened)) selected.push(reopened);
  }
  return selected;
}

export function reopenTailGapQueueItemForCollect<T extends {
  status: string;
  capture_status?: string;
  last_error?: string | null;
  profile_card_evidence?: Record<string, unknown>;
}>(item: T): T {
  const status = String(item.status);
  const captureStatus = String(item.capture_status ?? "");
  const blockedStatuses = new Set(["skipped", "already_collected", "backend_verified", "complete", "extracted"]);
  const needsReopen = blockedStatuses.has(status)
    || captureStatus === "complete"
    || captureStatus === "skipped";
  if (!needsReopen) {
    return item;
  }
  return {
    ...item,
    status: "needs_metadata",
    capture_status: "incomplete",
    last_error: null,
    profile_card_evidence: {
      ...(item.profile_card_evidence ?? {}),
      hybrid_uncollectable: false,
      hybrid_uncollectable_reason: null
    }
  };
}

export async function resolveExactBackendGapAwemeIds(args: {
  state: WholeProfileHarvestState;
  capturedIds: ReadonlySet<string>;
  limit: number;
  preferTailOrder?: boolean;
}): Promise<string[]> {
  const safeLimit = Math.max(0, Math.round(args.limit));
  if (safeLimit <= 0) return [];
  const pickMissing = args.preferTailOrder || isHybridTailGapCollect(safeLimit)
    ? diffAwemeIdsMissingFromCapturedTailFirst
    : diffAwemeIdsMissingFromCaptured;

  const fromState = pickMissing(
    collectKnownScannedAwemeIds(args.state),
    args.capturedIds,
    safeLimit
  );
  if (fromState.length >= safeLimit) return fromState;

  const profileUrl = args.state.profile_url ?? args.state.source_url ?? null;
  if (!profileUrl) return fromState;

  const repository = createProfileTargetRepository();
  const profileIdentifier = profileIdentifierFromUrl(profileUrl);
  const repositoryIds = await listAllRepositoryAwemeIds(profileIdentifier, repository);
  const mergedScanOrder = [...fromState];
  const seen = new Set(fromState);
  for (const id of repositoryIds) {
    if (seen.has(id)) continue;
    seen.add(id);
    mergedScanOrder.push(id);
  }
  return pickMissing(mergedScanOrder, args.capturedIds, safeLimit);
}
