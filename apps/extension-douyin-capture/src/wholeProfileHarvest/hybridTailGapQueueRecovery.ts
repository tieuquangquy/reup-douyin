import {
  isHybridTailGapCollect,
  resolveExactBackendGapAwemeIds,
  diffAwemeIdsMissingFromCapturedTailFirst
} from "./hybridBackendGapAwemeIds.js";
import {
  discoverMissingAwemeIdsViaProfilePost,
  type ProfilePostPageFetchResponse
} from "./hybridProfilePostTailHydration.js";
import {
  buildUnreachableTailGapSkipDiscoveryDiagnostics,
  shouldSkipTailGapRediscovery,
  upgradeUnreachableTailGapDiscoveryDiagnostics
} from "./hybridUnreachableTailGap.js";
import { profileIdentifierFromUrl } from "./profileTargetRepository.js";
import type { WholeProfileHarvestState } from "./state.js";

export type TailReconcileAwemeCandidate = {
  aweme_id: string;
  source_url: string;
  profile_url: string | null;
};

function parseTailReconcileAwemeCandidates(value: unknown): TailReconcileAwemeCandidate[] {
  if (!Array.isArray(value)) return [];
  const candidates: TailReconcileAwemeCandidate[] = [];
  for (const entry of value) {
    if (typeof entry === "string") {
      if (/^\d{8,24}$/.test(entry)) {
        candidates.push({
          aweme_id: entry,
          source_url: `https://www.douyin.com/video/${entry}`,
          profile_url: null
        });
      }
      continue;
    }
    if (!entry || typeof entry !== "object") continue;
    const record = entry as Record<string, unknown>;
    const awemeId = typeof record.aweme_id === "string"
      ? record.aweme_id
      : typeof record.awemeId === "string"
        ? record.awemeId
        : null;
    if (!awemeId || !/^\d{8,24}$/.test(awemeId)) continue;
    const sourceUrl = typeof record.source_url === "string" && record.source_url.trim()
      ? record.source_url.trim()
      : typeof record.sourceUrl === "string" && record.sourceUrl.trim()
        ? record.sourceUrl.trim()
        : `https://www.douyin.com/video/${awemeId}`;
    const profileUrl = typeof record.profile_url === "string"
      ? record.profile_url
      : typeof record.profileUrl === "string"
        ? record.profileUrl
        : null;
    candidates.push({ aweme_id: awemeId, source_url: sourceUrl, profile_url: profileUrl });
  }
  return candidates;
}

export function finalizeTailGapDiscoveryDiagnostics(
  diagnostics: Record<string, unknown>,
  gapIds: readonly string[],
  remaining: number
): Record<string, unknown> {
  const next: Record<string, unknown> = { ...diagnostics };
  if (gapIds.length > 0 && next.hybrid_tail_gap_discovery_found == null) {
    next.hybrid_tail_gap_discovery_found = gapIds.length;
  }
  if (!next.hybrid_tail_gap_discovery_stop_reason) {
    if (gapIds.length > 0) {
      next.hybrid_tail_gap_discovery_stop_reason = "ids_resolved";
    } else if (typeof next.hybrid_tail_gap_tail_reconcile_stop_reason === "string") {
      next.hybrid_tail_gap_discovery_stop_reason = next.hybrid_tail_gap_tail_reconcile_stop_reason;
    } else if (next.hybrid_tail_gap_discovery_attempted === "skipped_ids_from_scan") {
      next.hybrid_tail_gap_discovery_stop_reason = "scan_gap_empty";
    } else {
      next.hybrid_tail_gap_discovery_stop_reason = "discovery_exhausted";
    }
  }
  if (next.hybrid_tail_gap_tail_reconcile_found == null && next.hybrid_tail_gap_tail_reconcile_stop_reason != null) {
    next.hybrid_tail_gap_tail_reconcile_found = 0;
  }
  if (isHybridTailGapCollect(remaining)) {
    next.hybrid_tail_gap_live_remaining = remaining;
  }
  return next;
}

function tailReconcileCandidateSameProfile(candidate: TailReconcileAwemeCandidate, profileUrl: string): boolean {
  if (!candidate.profile_url) return true;
  return profileIdentifierFromUrl(candidate.profile_url) === profileIdentifierFromUrl(profileUrl);
}

function filterPassiveProfilePostCandidates(
  diagnostics: Record<string, unknown>,
  profileUrl: string
): TailReconcileAwemeCandidate[] {
  const raw = diagnostics.network_profile_post_targets;
  if (!Array.isArray(raw)) return [];
  const candidates: TailReconcileAwemeCandidate[] = [];
  for (const entry of raw) {
    if (!entry || typeof entry !== "object") continue;
    const record = entry as Record<string, unknown>;
    const endpointKind = typeof record.endpoint_kind === "string" ? record.endpoint_kind : null;
    const endpointPath = typeof record.endpoint_path === "string" ? record.endpoint_path : null;
    if (endpointKind === "favorite") continue;
    if (endpointPath != null && endpointPath !== "/aweme/v1/web/aweme/post/") continue;
    const parsed = parseTailReconcileAwemeCandidates([entry]);
    for (const candidate of parsed) {
      if (tailReconcileCandidateSameProfile(candidate, profileUrl)) candidates.push(candidate);
    }
  }
  return candidates;
}

export function discoverMissingAwemeIdsViaTailReconcileSources(args: {
  capturedIds: ReadonlySet<string>;
  limit: number;
  profileUrl: string;
  passiveDiagnostics: Record<string, unknown>;
  domProbeDiagnostics: Record<string, unknown>;
}): {
  aweme_ids: string[];
  stop_reason: string;
  candidate_count: number;
  passive_count: number;
  dom_count: number;
} {
  const passiveCandidates = filterPassiveProfilePostCandidates(args.passiveDiagnostics, args.profileUrl);
  const domCandidates = parseTailReconcileAwemeCandidates(
    args.domProbeDiagnostics.tail_reconcile_candidate_ids
      ?? args.domProbeDiagnostics.tail_reconcile_candidates
  ).filter((candidate) => tailReconcileCandidateSameProfile(candidate, args.profileUrl));
  const merged = [...passiveCandidates, ...domCandidates];
  const orderedAwemeIds: string[] = [];
  const seenOrder = new Set<string>();
  for (const candidate of merged) {
    if (seenOrder.has(candidate.aweme_id)) continue;
    seenOrder.add(candidate.aweme_id);
    orderedAwemeIds.push(candidate.aweme_id);
  }
  const found = isHybridTailGapCollect(args.limit)
    ? diffAwemeIdsMissingFromCapturedTailFirst(orderedAwemeIds, args.capturedIds, args.limit)
    : (() => {
      const tailFound: string[] = [];
      const seen = new Set<string>();
      for (const candidate of merged) {
        if (seen.has(candidate.aweme_id) || args.capturedIds.has(candidate.aweme_id)) continue;
        seen.add(candidate.aweme_id);
        tailFound.push(candidate.aweme_id);
        if (tailFound.length >= args.limit) break;
      }
      return tailFound;
    })();
  return {
    aweme_ids: found,
    stop_reason: found.length > 0
      ? "tail_reconcile_found"
      : merged.length === 0
        ? "no_tail_reconcile_candidates"
        : "all_tail_reconcile_candidates_already_captured",
    candidate_count: merged.length,
    passive_count: passiveCandidates.length,
    dom_count: domCandidates.length
  };
}

export type TailGapQueueRecoveryDeps = {
  state: WholeProfileHarvestState;
  remaining: number;
  at: string;
  capturedIds: ReadonlySet<string>;
  profileUrl: string | null;
  fetchProfilePostPage: ((cursor: string | number | null, pageIndex: number) => Promise<ProfilePostPageFetchResponse>) | null;
  profilePostPageBudget: number;
  /** Prior fossil / summary proving gap IDs unreachable — skip rediscovery. */
  priorFossil?: Record<string, unknown> | null;
  discoverViaTailReconcile?: () => Promise<{
    aweme_ids: string[];
    stop_reason: string;
    candidate_count: number;
    passive_count: number;
    dom_count: number;
  }>;
  rebuildQueue: (missingIds: string[]) => Promise<WholeProfileHarvestState | null>;
};

export async function recoverTailGapCollectQueue(
  deps: TailGapQueueRecoveryDeps
): Promise<{
  state: WholeProfileHarvestState;
  discoveredIds: string[];
  discoveryDiagnostics: Record<string, unknown>;
}> {
  if (!isHybridTailGapCollect(deps.remaining)) {
    return { state: deps.state, discoveredIds: [], discoveryDiagnostics: {} };
  }

  if (shouldSkipTailGapRediscovery({
    state: deps.state,
    remaining: deps.remaining,
    ...(deps.priorFossil !== undefined ? { fossil: deps.priorFossil } : {})
  })) {
    return {
      state: deps.state,
      discoveredIds: [],
      discoveryDiagnostics: finalizeTailGapDiscoveryDiagnostics(
        buildUnreachableTailGapSkipDiscoveryDiagnostics(deps.remaining),
        [],
        deps.remaining
      )
    };
  }

  let gapIds = await resolveExactBackendGapAwemeIds({
    state: deps.state,
    capturedIds: deps.capturedIds,
    limit: deps.remaining,
    preferTailOrder: true
  });

  let discoveryDiagnostics: Record<string, unknown> = {
    hybrid_tail_gap_discovery_attempted: gapIds.length === 0 ? "yes" : "skipped_ids_from_scan"
  };
  if (gapIds.length === 0 && deps.profileUrl && deps.fetchProfilePostPage) {
    const discovery = await discoverMissingAwemeIdsViaProfilePost({
      capturedIds: deps.capturedIds,
      limit: deps.remaining,
      profileUrl: deps.profileUrl,
      maxPages: deps.profilePostPageBudget,
      capturedAt: deps.at,
      fetchPage: deps.fetchProfilePostPage
    });
    gapIds = discovery.aweme_ids;
    discoveryDiagnostics = {
      ...discoveryDiagnostics,
      hybrid_tail_gap_discovery_pages: discovery.pages_fetched,
      hybrid_tail_gap_discovery_stop_reason: discovery.stop_reason,
      hybrid_tail_gap_discovery_found: discovery.aweme_ids.length
    };
  } else if (gapIds.length === 0 && !deps.profileUrl) {
    discoveryDiagnostics.hybrid_tail_gap_discovery_stop_reason = "no_profile_url";
  } else if (gapIds.length === 0 && !deps.fetchProfilePostPage) {
    discoveryDiagnostics.hybrid_tail_gap_discovery_stop_reason = "no_profile_post_fetch";
  }

  if (gapIds.length === 0 && deps.discoverViaTailReconcile) {
    const tailDiscovery = await deps.discoverViaTailReconcile();
    if (tailDiscovery.aweme_ids.length > 0) {
      gapIds = tailDiscovery.aweme_ids;
    }
    discoveryDiagnostics = upgradeUnreachableTailGapDiscoveryDiagnostics({
      ...discoveryDiagnostics,
      hybrid_tail_gap_tail_reconcile_stop_reason: tailDiscovery.stop_reason,
      hybrid_tail_gap_tail_reconcile_candidates: tailDiscovery.candidate_count,
      hybrid_tail_gap_tail_reconcile_passive_count: tailDiscovery.passive_count,
      hybrid_tail_gap_tail_reconcile_dom_count: tailDiscovery.dom_count,
      hybrid_tail_gap_tail_reconcile_found: tailDiscovery.aweme_ids.length,
      hybrid_tail_gap_discovery_source: tailDiscovery.aweme_ids.length > 0 ? "tail_reconcile" : "profile_post_then_tail_reconcile",
      hybrid_tail_gap_discovery_found: gapIds.length
    });
  }

  if (gapIds.length === 0) {
    return {
      state: deps.state,
      discoveredIds: [],
      discoveryDiagnostics: upgradeUnreachableTailGapDiscoveryDiagnostics(
        finalizeTailGapDiscoveryDiagnostics(discoveryDiagnostics, gapIds, deps.remaining)
      )
    };
  }

  const gapState = await deps.rebuildQueue(gapIds);
  if (!gapState) {
    return {
      state: deps.state,
      discoveredIds: gapIds,
      discoveryDiagnostics: finalizeTailGapDiscoveryDiagnostics(discoveryDiagnostics, gapIds, deps.remaining)
    };
  }

  const rebuildSource = discoveryDiagnostics.hybrid_tail_gap_discovery_source === "tail_reconcile"
    ? "exact_tail_gap_tail_reconcile"
    : "exact_tail_gap_profile_post_discovery";
  const summaryPatch: Record<string, unknown> = {
    hybrid_collect_queue_rebuilt: rebuildSource,
    hybrid_backend_gap_missing_ids: gapIds.join(","),
    hybrid_exact_tail_gap_mode: "yes",
    hybrid_force_exact_tail_gap_collect: "yes",
    hybrid_tail_gap_live_remaining: deps.remaining
  };

  return {
    state: {
      ...gapState,
      debug: {
        ...gapState.debug,
        last_response_summary: {
          ...(gapState.debug.last_response_summary && typeof gapState.debug.last_response_summary === "object"
            ? gapState.debug.last_response_summary as Record<string, unknown>
            : {}),
          ...summaryPatch
        }
      },
      updated_at: deps.at
    },
    discoveredIds: gapIds,
    discoveryDiagnostics: finalizeTailGapDiscoveryDiagnostics(discoveryDiagnostics, gapIds, deps.remaining)
  };
}
