import { buildPassiveNetworkStoredTarget22C12A } from "../networkProbe22C12A.js";
import type { NetworkVideoMetadata, PassiveNetworkProbeStoredTarget22C12A } from "../types.js";
import {
  enrichQueueItemEvidenceFromHydrationCaches,
  hydrateNonModalForAwemeId,
  type HybridHydrationSourceBundle
} from "./hybridHydration.js";

export const HYBRID_PROFILE_POST_TAIL_PAGE_ABSOLUTE_CAP = 128;
export const HYBRID_PROFILE_POST_TAIL_PAGE_MIN = 40;
/** Stop paging when this many consecutive pages match zero pending targets. */
export const HYBRID_PROFILE_POST_CONSECUTIVE_EMPTY_PAGE_LIMIT = 5;

export type ProfilePostPageFetchResponse = {
  ok: boolean;
  verified_target_details: Array<Record<string, unknown>>;
  has_more: boolean | null;
  next_cursor: string | number | null;
  stop_reason: string;
};

export type ProfilePostTailHydrationTarget = {
  aweme_id: string;
  source_url?: string | null;
  profile_card_evidence?: Record<string, unknown> | null;
};

export function resolveHybridProfilePostTailPageBudget(scannedTotal?: number | null): number {
  const estimatedPages = scannedTotal != null && scannedTotal > 0
    ? Math.ceil(scannedTotal / 18) + 2
    : HYBRID_PROFILE_POST_TAIL_PAGE_MIN;
  return Math.min(
    HYBRID_PROFILE_POST_TAIL_PAGE_ABSOLUTE_CAP,
    Math.max(HYBRID_PROFILE_POST_TAIL_PAGE_MIN, estimatedPages)
  );
}

/** Scale profile-post paging to the still-pending batch instead of full profile depth. */
export function resolveHybridProfilePostTailPageBudgetForPending(
  pendingCount: number,
  scannedTotal?: number | null
): number {
  const fullBudget = resolveHybridProfilePostTailPageBudget(scannedTotal);
  const pending = Math.max(0, Math.round(pendingCount));
  if (pending <= 0) return 0;
  const pendingScaled = Math.ceil(pending / 18) + 3;
  return Math.min(fullBudget, Math.max(pendingScaled, Math.min(12, fullBudget)));
}

export function resolveHybridProfilePostTailTimeoutMs(pageBudget: number): number {
  const safe = Math.max(0, Math.round(pageBudget));
  return Math.min(600_000, Math.max(60_000, safe * 8_000));
}

function buildHydrationSources(
  target: ProfilePostTailHydrationTarget,
  networkCacheByAwemeId: Map<string, unknown>,
  passiveByAwemeId: Map<string, Record<string, unknown>>
): HybridHydrationSourceBundle {
  const passiveTarget = passiveByAwemeId.get(target.aweme_id) as PassiveNetworkProbeStoredTarget22C12A | undefined;
  const networkCacheItem = networkCacheByAwemeId.get(target.aweme_id);
  const mergedEvidence = enrichQueueItemEvidenceFromHydrationCaches(
    { aweme_id: target.aweme_id, profile_card_evidence: target.profile_card_evidence ?? null },
    passiveTarget ?? null,
    networkCacheItem ? networkCacheItem as NetworkVideoMetadata : null
  );
  return {
    profile_repository: mergedEvidence,
    network_cache: (networkCacheItem ?? null) as NetworkVideoMetadata | null,
    passive_aweme: passiveTarget ?? null,
    profile_post_api: passiveTarget?.endpoint_kind === "profile_post" ? passiveTarget : null,
    calibrated_non_modal_dom: null
  };
}

export function targetNeedsProfilePostTailHydration(
  target: ProfilePostTailHydrationTarget,
  networkCacheByAwemeId: Map<string, unknown>,
  passiveByAwemeId: Map<string, Record<string, unknown>>
): boolean {
  return Boolean(hydrateNonModalForAwemeId(target.aweme_id, buildHydrationSources(target, networkCacheByAwemeId, passiveByAwemeId)).pending_reason);
}

function readNumberField(record: Record<string, unknown>, key: string): number | null {
  const value = record[key];
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function readStringField(record: Record<string, unknown>, key: string): string | null {
  const value = record[key];
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

export function verifiedDetailToPassiveProfilePostTarget(
  detail: Record<string, unknown>,
  profileUrl: string,
  capturedAt: string
): PassiveNetworkProbeStoredTarget22C12A | null {
  const awemeId = readStringField(detail, "aweme_id");
  if (!awemeId || !/^\d{8,}$/.test(awemeId)) return null;
  const evidence = detail.profile_card_evidence && typeof detail.profile_card_evidence === "object"
    ? detail.profile_card_evidence as Record<string, unknown>
    : {};
  const pickNumber = (...keys: string[]): number | null => {
    for (const key of keys) {
      const fromDetail = readNumberField(detail, key);
      if (fromDetail != null) return fromDetail;
      const fromEvidence = readNumberField(evidence, key);
      if (fromEvidence != null) return fromEvidence;
    }
    return null;
  };
  const pickString = (...keys: string[]): string | null => {
    for (const key of keys) {
      const fromDetail = readStringField(detail, key);
      if (fromDetail) return fromDetail;
      const fromEvidence = readStringField(evidence, key);
      if (fromEvidence) return fromEvidence;
    }
    return null;
  };
  return buildPassiveNetworkStoredTarget22C12A({
    target: {
      aweme_id: awemeId,
      source_url: pickString("source_url") ?? `https://www.douyin.com/video/${awemeId}`,
      desc: pickString("caption", "title", "desc"),
      cover_url: pickString("thumbnail_url", "cover_url"),
      duration: pickNumber("duration_seconds", "duration"),
      create_time: pickNumber("create_time"),
      like_count: pickNumber("like_count"),
      comment_count: pickNumber("comment_count"),
      favorite_count: pickNumber("favorite_count"),
      share_count: pickNumber("share_count"),
      author_uid: pickString("author_uid"),
      author_sec_uid: pickString("author_sec_uid"),
      author_unique_id: pickString("author_unique_id")
    },
    profileUrl,
    urlPath: pickString("endpoint_path") ?? "/aweme/v1/web/aweme/post/",
    capturedAt
  });
}

export async function recoverPendingTargetsViaProfilePostPagination(deps: {
  targets: ProfilePostTailHydrationTarget[];
  profileUrl: string;
  networkCacheByAwemeId: Map<string, unknown>;
  passiveByAwemeId: Map<string, Record<string, unknown>>;
  maxPages: number;
  capturedAt: string;
  fetchPage: (cursor: string | number | null, pageIndex: number) => Promise<ProfilePostPageFetchResponse>;
}): Promise<{
  pending_before: string[];
  pages_fetched: number;
  targets_matched: number;
  recovered: string[];
  stop_reason: string;
}> {
  const needsHydration = deps.targets.filter((target) =>
    targetNeedsProfilePostTailHydration(target, deps.networkCacheByAwemeId, deps.passiveByAwemeId)
  );
  const missingSet = new Set(needsHydration.map((target) => target.aweme_id));
  if (missingSet.size === 0) {
    return {
      pending_before: [],
      pages_fetched: 0,
      targets_matched: 0,
      recovered: [],
      stop_reason: "none_needed"
    };
  }

  let cursor: string | number | null = 0;
  let pageIndex = 0;
  let stopReason = "max_pages";
  let pagesFetched = 0;
  let targetsMatched = 0;
  let consecutiveEmptyPages = 0;
  const pageBudget = Math.max(1, Math.round(deps.maxPages));

  while (pageIndex < pageBudget && missingSet.size > 0) {
    const response: ProfilePostPageFetchResponse = await deps.fetchPage(cursor, pageIndex).catch((): ProfilePostPageFetchResponse => ({
      ok: false,
      verified_target_details: [],
      has_more: null,
      next_cursor: null,
      stop_reason: "fetch_failed"
    }));
    pagesFetched += 1;
    pageIndex += 1;

    if (!response.ok) {
      stopReason = response.stop_reason || "page_not_ok";
      break;
    }

    let pageMatched = 0;
    for (const detail of response.verified_target_details) {
      const passive = verifiedDetailToPassiveProfilePostTarget(detail, deps.profileUrl, deps.capturedAt);
      if (!passive) continue;
      deps.passiveByAwemeId.set(passive.aweme_id, passive as unknown as Record<string, unknown>);
      if (missingSet.has(passive.aweme_id)) {
        targetsMatched += 1;
        pageMatched += 1;
        missingSet.delete(passive.aweme_id);
      }
    }

    if (pageMatched === 0) {
      consecutiveEmptyPages += 1;
      if (consecutiveEmptyPages >= HYBRID_PROFILE_POST_CONSECUTIVE_EMPTY_PAGE_LIMIT) {
        stopReason = "consecutive_empty_pages";
        break;
      }
    } else {
      consecutiveEmptyPages = 0;
    }

    if (response.has_more === false || response.next_cursor == null) {
      stopReason = response.stop_reason || "pagination_exhausted";
      break;
    }
    cursor = response.next_cursor;
  }

  const recovered = needsHydration
    .filter((target) => !targetNeedsProfilePostTailHydration(target, deps.networkCacheByAwemeId, deps.passiveByAwemeId))
    .map((target) => target.aweme_id);

  return {
    pending_before: needsHydration.map((target) => target.aweme_id),
    pages_fetched: pagesFetched,
    targets_matched: targetsMatched,
    recovered,
    stop_reason: missingSet.size === 0 ? "all_missing_found" : stopReason
  };
}

/** Paginate profile-post API for aweme_ids on Douyin that are not yet in the captured set. */
export async function discoverMissingAwemeIdsViaProfilePost(deps: {
  capturedIds: ReadonlySet<string>;
  limit: number;
  profileUrl: string;
  maxPages: number;
  capturedAt: string;
  fetchPage: (cursor: string | number | null, pageIndex: number) => Promise<ProfilePostPageFetchResponse>;
}): Promise<{
  aweme_ids: string[];
  pages_fetched: number;
  stop_reason: string;
}> {
  const capped = Math.max(0, Math.round(deps.limit));
  if (capped <= 0) return { aweme_ids: [], pages_fetched: 0, stop_reason: "limit_zero" };

  const found: string[] = [];
  const seen = new Set<string>();
  let cursor: string | number | null = 0;
  let pagesFetched = 0;
  let stopReason = "limit_reached";
  let consecutiveExtractorEmpty = 0;

  for (let pageIndex = 0; pageIndex < deps.maxPages && found.length < capped; pageIndex += 1) {
    let response: ProfilePostPageFetchResponse = await deps.fetchPage(cursor, pageIndex).catch((): ProfilePostPageFetchResponse => ({
      ok: false,
      verified_target_details: [],
      has_more: null,
      next_cursor: null,
      stop_reason: "fetch_failed"
    }));
    // First page often fails while the profile-post template is still warming — retry once.
    if (!response.ok && pageIndex === 0) {
      response = await deps.fetchPage(cursor, pageIndex).catch((): ProfilePostPageFetchResponse => ({
        ok: false,
        verified_target_details: [],
        has_more: null,
        next_cursor: null,
        stop_reason: "fetch_failed_retry"
      }));
    }
    // extractor_no_targets on early pages: template/parser not ready — retry same cursor up to 2 times.
    if (
      !response.ok
      && response.stop_reason === "extractor_no_targets"
      && consecutiveExtractorEmpty < 2
    ) {
      consecutiveExtractorEmpty += 1;
      response = await deps.fetchPage(cursor, pageIndex).catch((): ProfilePostPageFetchResponse => ({
        ok: false,
        verified_target_details: [],
        has_more: null,
        next_cursor: null,
        stop_reason: "extractor_no_targets_retry_failed"
      }));
    }
    pagesFetched += 1;
    if (!response.ok) {
      stopReason = response.stop_reason || "page_not_ok";
      break;
    }
    consecutiveExtractorEmpty = 0;

    for (const detail of response.verified_target_details) {
      const passive = verifiedDetailToPassiveProfilePostTarget(detail, deps.profileUrl, deps.capturedAt);
      if (!passive) continue;
      const awemeId = passive.aweme_id;
      if (seen.has(awemeId) || deps.capturedIds.has(awemeId)) continue;
      seen.add(awemeId);
      found.push(awemeId);
      if (found.length >= capped) break;
    }

    if (found.length >= capped) {
      stopReason = "limit_reached";
      break;
    }
    if (response.has_more === false || response.next_cursor == null) {
      stopReason = response.stop_reason || "pagination_exhausted";
      break;
    }
    cursor = response.next_cursor;
  }

  return { aweme_ids: found, pages_fetched: pagesFetched, stop_reason: stopReason };
}
