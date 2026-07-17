import type { WholeProfileHarvestState } from "./state.js";
import { mergeScanAuthorityDiagnostics } from "./backendCollectAuthority.js";

export const DISPLAYED_PROFILE_COLLECT_SCOPE = "displayed_profile_only" as const;

function numericDiagnostic(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) return Math.max(0, Math.round(value));
  if (typeof value === "string" && value.trim()) {
    const parsed = Number(value);
    if (Number.isFinite(parsed)) return Math.max(0, Math.round(parsed));
  }
  return null;
}

/** Visible profile video count from scan diagnostics (operator collect scope). */
export function resolveDisplayedProfileVideoLimit(diagnostics: Record<string, unknown>): number | null {
  const displayed = numericDiagnostic(diagnostics.displayed_profile_count);
  if (displayed != null && displayed > 0) return displayed;
  const expected = numericDiagnostic(
    diagnostics.expected_profile_video_count
      ?? diagnostics.expected_count
      ?? diagnostics.profile_expected_count
  );
  return expected != null && expected > 0 ? expected : null;
}

export function resolveOverDisplayedExtraAwemeIds(diagnostics: Record<string, unknown>): string[] {
  const exact = Array.isArray(diagnostics.over_displayed_extra_ids_exact)
    ? diagnostics.over_displayed_extra_ids_exact
        .map((value) => (typeof value === "string" ? value.trim() : ""))
        .filter(Boolean)
    : [];
  if (exact.length > 0) return exact;

  const overDisplayedCount = numericDiagnostic(diagnostics.over_displayed_count) ?? 0;
  const displayedLimit = resolveDisplayedProfileVideoLimit(diagnostics);
  const persisted = numericDiagnostic(
    diagnostics.queue_total_persisted
      ?? diagnostics.scan_job_total_persisted
      ?? diagnostics.profile_queue_total_count
      ?? diagnostics.persisted_count
  );
  if (displayedLimit == null || overDisplayedCount <= 0 || persisted == null || persisted <= displayedLimit) {
    return [];
  }
  return [];
}

export function resolveOverDisplayedExtraAwemeIdSet(diagnostics: Record<string, unknown>): Set<string> {
  return new Set(resolveOverDisplayedExtraAwemeIds(diagnostics));
}

export type DisplayedProfileQueueCapResult<T extends { aweme_id: string }> = {
  queue: T[];
  excludedIds: string[];
  excludedCount: number;
  capped: boolean;
  displayedLimit: number | null;
};

/**
 * Keep only videos within the visible profile count. API tail extras are excluded
 * from persist/collect — operator scope is displayed profile videos only.
 */
export function capOrderedQueueToDisplayedProfileLimit<T extends { aweme_id: string }>(
  queue: readonly T[],
  displayedLimit: number | null,
  extraIdSet: ReadonlySet<string> = new Set()
): DisplayedProfileQueueCapResult<T> {
  if (displayedLimit == null || displayedLimit <= 0) {
    return {
      queue: [...queue],
      excludedIds: [],
      excludedCount: 0,
      capped: false,
      displayedLimit: null
    };
  }

  const excludedById = queue.filter((item) => extraIdSet.has(item.aweme_id));
  const withoutKnownExtras = extraIdSet.size > 0
    ? queue.filter((item) => !extraIdSet.has(item.aweme_id))
    : queue;

  if (withoutKnownExtras.length <= displayedLimit) {
    return {
      queue: [...withoutKnownExtras],
      excludedIds: excludedById.map((item) => item.aweme_id),
      excludedCount: excludedById.length,
      capped: excludedById.length > 0,
      displayedLimit
    };
  }

  const capped = withoutKnownExtras.slice(0, displayedLimit);
  const cappedIdSet = new Set(capped.map((item) => item.aweme_id));
  const excludedTail = withoutKnownExtras
    .filter((item) => !cappedIdSet.has(item.aweme_id))
    .map((item) => item.aweme_id);
  const excludedIds = [...excludedById.map((item) => item.aweme_id), ...excludedTail];

  return {
    queue: capped,
    excludedIds,
    excludedCount: excludedIds.length,
    capped: true,
    displayedLimit
  };
}

export function capTargetDetailsToAwemeIds<T extends { aweme_id: string }>(
  targetDetails: readonly T[],
  allowedAwemeIds: ReadonlySet<string>
): T[] {
  return targetDetails.filter((target) => allowedAwemeIds.has(target.aweme_id));
}

export function buildDisplayedProfileQueueCapDiagnostics(args: {
  beforeCount: number;
  result: DisplayedProfileQueueCapResult<{ aweme_id: string }>;
  apiDiscoveredCount?: number | null;
}): Record<string, unknown> {
  const { result, beforeCount } = args;
  const apiDiscovered = args.apiDiscoveredCount ?? beforeCount;
  return {
    collect_scope: DISPLAYED_PROFILE_COLLECT_SCOPE,
    displayed_profile_collect_limit: result.displayedLimit,
    queue_cap_applied: result.capped ? "yes" : "no",
    queue_cap_excluded_count: result.excludedCount,
    queue_cap_excluded_ids_sample: result.excludedIds.slice(0, 10),
    queue_cap_before_count: beforeCount,
    queue_cap_after_count: result.queue.length,
    api_discovered_count_before_cap: apiDiscovered,
    over_displayed_excluded_from_collect: result.excludedCount > 0 ? "yes" : "no"
  };
}

export function mergeDisplayedProfileQueueCapDiagnostics(
  diagnostics: Record<string, unknown>,
  capDiagnostics: Record<string, unknown>
): Record<string, unknown> {
  return { ...diagnostics, ...capDiagnostics, collect_scope: DISPLAYED_PROFILE_COLLECT_SCOPE };
}

export function shouldExcludeAwemeIdFromDisplayedProfileCollect(
  awemeId: string,
  diagnostics: Record<string, unknown>,
  queueIndex?: number
): boolean {
  const normalized = awemeId.trim();
  if (!normalized) return true;
  const extraIds = resolveOverDisplayedExtraAwemeIdSet(diagnostics);
  if (extraIds.has(normalized)) return true;
  const displayedLimit = resolveDisplayedProfileVideoLimit(diagnostics);
  if (displayedLimit == null || displayedLimit <= 0) return false;
  if (typeof queueIndex === "number" && queueIndex >= displayedLimit) return true;
  return false;
}

export function filterQueueToDisplayedProfileCollectScope<
  T extends { aweme_id: string }
>(queue: readonly T[], diagnostics: Record<string, unknown>): T[] {
  const displayedLimit = resolveDisplayedProfileVideoLimit(diagnostics);
  const extraIds = resolveOverDisplayedExtraAwemeIdSet(diagnostics);
  return capOrderedQueueToDisplayedProfileLimit(queue, displayedLimit, extraIds).queue;
}

export function resolveDisplayedProfileCollectDiagnosticsFromState(
  state: WholeProfileHarvestState
): Record<string, unknown> {
  return mergeScanAuthorityDiagnostics(state);
}

export function filterHarvestQueueToDisplayedProfileCollectScope<
  T extends { aweme_id: string }
>(state: WholeProfileHarvestState, queue: readonly T[]): T[] {
  return filterQueueToDisplayedProfileCollectScope(queue, resolveDisplayedProfileCollectDiagnosticsFromState(state));
}
