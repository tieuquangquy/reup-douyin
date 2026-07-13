// hybridHydration.ts — shared, pure-function module for non-modal metric hydration.
//
// Mirrors the merge primitives proven by the popup.ts pilot (buildHybridOnlyHydrationContext,
// fieldsFromRecord, fieldsFromNetworkMetadata, fieldsFromPassiveTarget, mergeHydrationFields,
// buildViewCountDiagnosticsFromSources, buildEstimatedViewsDiagnostics, ...) so that the
// Hybrid-network-cache controller runner can hydrate a per-target finalized payload without
// opening a modal.
//
// Hard invariants enforced by this module:
//   - exact_aweme_id_only: every per-target hydration is keyed by a literal aweme_id; this
//     module never accepts wildcards or partial matches.
//   - estimated_views NEVER copied into view_count; estimated_views_formula stays
//     "tiered_like_multiplier_v1".
//   - view_count only populated from a trusted-allowlist field; otherwise null with a reason.
//   - missing required fields → result.pending_reason set; finalized payload is null.
//
// This module has no side effects, no DOM access, no chrome.* access, and no network access.
// It is safe to call from the controller and from popup.ts.

import type {
  FullModalHarvestItemPayload,
  NetworkVideoMetadata,
  PassiveNetworkProbeStoredTarget22C12A
} from "../types.js";

// ---------- Public types ----------

export type HybridHydrationSource =
  | "profile_repository"
  | "network_cache"
  | "passive_aweme"
  | "profile_post_api"
  | "calibrated_non_modal_dom";

export type HybridMetricField =
  | "duration_seconds"
  | "like_count"
  | "comment_count"
  | "favorite_count"
  | "share_count";

export interface HybridHydrationFields {
  duration_seconds: number | null;
  duration_text: string | null;
  like_count: number | null;
  comment_count: number | null;
  favorite_count: number | null;
  share_count: number | null;
}

export interface HybridThumbnailEvidence {
  present: "yes" | "no";
  field_used: string | null;
  source: HybridHydrationSource | "missing";
  valid_url: "yes" | "no";
  url: string | null;
  url_host: string | null;
}

export interface HybridViewCountDiagnostics {
  normalized_view_count: number | null;
  normalized_view_count_source: HybridHydrationSource | null;
  normalized_view_count_field_used: string | null;
  normalized_view_count_defaulted: "yes" | "no";
  normalized_view_count_default_reason: string | null;
  real_view_count_found: "yes" | "no";
  selected_field_trusted: "yes" | "no";
  selected_field_semantic_reason: string | null;
}

export interface HybridEstimatedViewsDiagnostics {
  estimated_views: number | null;
  estimated_views_source: string;
  estimated_views_formula: "tiered_like_multiplier_v1";
  like_count_used: number | null;
  like_count_source: string | null;
  multiplier_used: number | null;
  rounded: "yes" | "no";
  confidence: "high" | "medium" | "low";
  validity: "valid" | "missing_like_count" | "invalid_like_count";
}

export interface HybridHydrationSourceBundle {
  /** profile_card_evidence already attached to the queue item by Scan Profile. */
  profile_repository: Record<string, unknown> | null;
  /** Item from window.__REUP_DOUYIN_NETWORK_CACHE__, looked up by aweme_id. */
  network_cache: NetworkVideoMetadata | null;
  /** Union of profile_post + favorite + other_aweme_list passive probe targets, looked up by aweme_id. */
  passive_aweme: PassiveNetworkProbeStoredTarget22C12A | null;
  /** Subset of passive_aweme restricted to /aweme/v1/web/aweme/post/. */
  profile_post_api: PassiveNetworkProbeStoredTarget22C12A | null;
  /** Reserved for a future calibrated non-modal DOM probe. */
  calibrated_non_modal_dom: Record<string, unknown> | null;
}

export interface HybridHydrationResult {
  aweme_id: string;
  fields: HybridHydrationFields;
  metric_value_source: Record<HybridMetricField, HybridHydrationSource | null>;
  thumbnail: HybridThumbnailEvidence;
  view_count_diagnostics: HybridViewCountDiagnostics;
  estimated_views_diagnostics: HybridEstimatedViewsDiagnostics;
  posted: string | number | null;
  posted_at: string | null;
  posted_source: HybridHydrationSource | "missing";
  title: string | null;
  title_source: string | null;
  title_is_id_fallback: boolean;
  title_valid_real_text: boolean;
  raw_like_count_source: string | null;
  raw_like_count_value_type: string;
  raw_like_count_exact_numeric: boolean;
  display_like_text: string | null;
  display_like_text_source: string | null;
  rounded_like_display_rejected_for_raw: boolean;
  sources_attempted: HybridHydrationSource[];
  sources_used: HybridHydrationSource[];
  missing_required_fields: string[];
  pending_reason: string | null;
}

// ---------- Constants ----------

export const HYBRID_REQUIRED_METRIC_FIELDS: ReadonlyArray<HybridMetricField> = [
  "duration_seconds",
  "like_count",
  "comment_count",
  "favorite_count",
  "share_count"
];

const DOUYIN_CDN_HOST = "p3-sign.douyinpic.com";
const DOUYIN_IMAGE_HOST_MARKERS = ["douyinpic.com", "byteimg.com", "douyinstatic.com"];

function hasDouyinThumbnailSignature(value: string): boolean {
  return /[?&]x-signature=/i.test(value) || /[?&]x-expires=/i.test(value);
}

function isDouyinImageHost(value: string): boolean {
  try {
    const host = new URL(value, "https://www.douyin.com").hostname.toLowerCase();
    return DOUYIN_IMAGE_HOST_MARKERS.some((marker) => host.includes(marker));
  } catch {
    return false;
  }
}

/** Prefer signed CDN covers; avoid synthesizing unsigned CDN templates (403 in browser). */
export function pickBestDouyinThumbnailUrl(candidates: Array<string | null | undefined>): string | null {
  const normalized = candidates
    .flatMap((candidate) => {
      if (!candidate || typeof candidate !== "string" || !candidate.trim()) return [];
      const withProtocol = candidate.trim().startsWith("//") ? `https:${candidate.trim()}` : candidate.trim();
      return /^https?:\/\//i.test(withProtocol) ? [withProtocol] : [];
    });
  const signed = normalized.find((url) => isDouyinImageHost(url) && hasDouyinThumbnailSignature(url));
  if (signed) return signed;
  const cdn = normalized.find((url) => isDouyinImageHost(url));
  if (cdn) return cdn;
  const tos = normalized.find((url) => /\/tos-/i.test(url));
  if (tos) return tos;
  return normalized[0] ?? null;
}

/**
 * Normalize Douyin thumbnail URLs for backend persistence.
 * Signed CDN URLs are kept intact; bare www.douyin.com/tos paths are kept as-is
 * (backend accepts /tos- and the API thumbnail proxy can fetch them).
 * Unsigned p3-sign templates without query params return 403 — do not synthesize them.
 */
export function promoteDouyinThumbnailToCdnUrl(value: string): string | null {
  const trimmed = value.trim();
  if (!trimmed) return null;
  const withProtocol = trimmed.startsWith("//") ? `https:${trimmed}` : trimmed;
  if (!/^https?:\/\//i.test(withProtocol)) return null;
  try {
    const url = new URL(withProtocol);
    const path = url.pathname || "";
    const host = url.hostname.toLowerCase();
    if (isDouyinImageHost(withProtocol)) {
      return withProtocol;
    }
    if (!/\/tos-/i.test(path)) return withProtocol;
    if (host.includes("douyin.com") || host.includes("iesdouyin.com")) {
      return withProtocol;
    }
    const cdnPath = path.startsWith("/") ? path : `/${path}`;
    if (/\.(jpe?g|png|webp|gif|avif)$/i.test(cdnPath.split("?")[0] ?? "")) {
      return `https://${DOUYIN_CDN_HOST}${cdnPath}${url.search}`;
    }
    return withProtocol;
  } catch {
    return withProtocol;
  }
}

function numberOrNullFromEvidence(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function stringOrNullFromEvidence(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

/** Merge scan / probe / repository records into one profile_card_evidence for Hybrid. */
export function buildHybridProfileCardEvidence(
  base: Record<string, unknown> | null | undefined,
  overlays: Array<Record<string, unknown> | null | undefined> = []
): Record<string, unknown> {
  const merged: Record<string, unknown> = base && typeof base === "object" ? { ...base } : {};
  for (const overlay of overlays) {
    if (!overlay || typeof overlay !== "object") continue;
    for (const [key, value] of Object.entries(overlay)) {
      if (value == null) continue;
      if (typeof value === "string" && !value.trim()) continue;
      merged[key] = value;
    }
  }
  const thumb = pickBestDouyinThumbnailUrl([
    stringOrNullFromEvidence(merged.thumbnail_url),
    stringOrNullFromEvidence(merged.cover_url),
    stringOrNullFromEvidence(merged.poster_url),
    stringOrNullFromEvidence(merged.origin_cover),
    ...(Array.isArray(merged.url_list) ? merged.url_list.filter((entry): entry is string => typeof entry === "string") : [])
  ]);
  const cdnThumb = thumb ? promoteDouyinThumbnailToCdnUrl(thumb) : null;
  if (cdnThumb) {
    merged.thumbnail_url = cdnThumb;
    merged.cover_url = stringOrNullFromEvidence(merged.cover_url) ?? cdnThumb;
  }
  const duration = numberOrNullFromEvidence(merged.duration_seconds) ?? numberOrNullFromEvidence(merged.duration);
  if (duration != null) {
    merged.duration_seconds = duration;
    merged.duration = duration;
  }
  return merged;
}

/** Merge passive probe + network cache metrics into queue evidence before Hybrid hydrate. */
export function enrichQueueItemEvidenceFromHydrationCaches(
  item: { aweme_id: string; profile_card_evidence?: Record<string, unknown> | null },
  passive: PassiveNetworkProbeStoredTarget22C12A | null | undefined,
  network: NetworkVideoMetadata | null | undefined
): Record<string, unknown> {
  const passiveOverlay = passive ? {
    thumbnail_url: passive.cover_url ?? null,
    cover_url: passive.cover_url ?? null,
    caption: passive.desc ?? null,
    title: passive.desc ?? null,
    duration_seconds: passive.duration ?? null,
    duration: passive.duration ?? null,
    like_count: passive.like_count ?? null,
    comment_count: passive.comment_count ?? null,
    favorite_count: passive.favorite_count ?? null,
    share_count: passive.share_count ?? null,
    create_time: passive.create_time ?? null,
    posted_at: typeof passive.create_time === "number" && passive.create_time > 0
      ? new Date(passive.create_time * 1000).toISOString()
      : null
  } : null;
  const networkOverlay = network ? {
    thumbnail_url: pickBestDouyinThumbnailUrl([
      network.thumbnail_url,
      network.cover_url,
      network.origin_cover,
      ...(network.url_list ?? [])
    ]),
    cover_url: pickBestDouyinThumbnailUrl([
      network.cover_url,
      network.thumbnail_url,
      network.origin_cover,
      ...(network.url_list ?? [])
    ]),
    url_list: network.url_list ?? null,
    duration_seconds: network.duration_seconds ?? null,
    duration: network.duration_seconds ?? null,
    like_count: network.like_count ?? null,
    comment_count: network.comment_count ?? null,
    favorite_count: network.favorite_count ?? null,
    share_count: network.share_count ?? null,
    posted_at: network.posted_at ?? null
  } : null;
  return buildHybridProfileCardEvidence(item.profile_card_evidence ?? null, [passiveOverlay, networkOverlay]);
}

/** True when profile_card_evidence already carries Hybrid-required metrics. */
export function evidenceHasHybridRequiredMetrics(evidence: Record<string, unknown> | null | undefined): boolean {
  if (!evidence || typeof evidence !== "object") return false;
  const numberField = (key: string): number | null => {
    const value = evidence[key];
    return typeof value === "number" && Number.isFinite(value) ? value : null;
  };
  const duration = numberField("duration_seconds") ?? numberField("duration");
  const like = numberField("like_count");
  const comment = numberField("comment_count");
  const favorite = numberField("favorite_count");
  const share = numberField("share_count");
  return duration != null && duration > 0
    && like != null && like >= 0
    && comment != null && comment >= 0
    && favorite != null && favorite >= 0
    && share != null && share >= 0;
}

/** True when queue evidence can pass hydrate → finalize without pending_reason. */
export function evidenceIsHybridFlushReady(evidence: Record<string, unknown> | null | undefined): boolean {
  if (!evidence || typeof evidence !== "object") return false;
  const awemeId = String(evidence.aweme_id ?? "").trim();
  if (!awemeId) return false;
  const hydration = hydrateNonModalForAwemeId(awemeId, {
    profile_repository: evidence,
    network_cache: null,
    passive_aweme: null,
    profile_post_api: null,
    calibrated_non_modal_dom: null
  });
  return hydration.pending_reason == null;
}

/** Count pending queue items that already carry Hybrid-required metrics. */
export function countQueueItemsWithHybridMetrics(
  queue: Array<{ status?: string; capture_status?: string; profile_card_evidence?: Record<string, unknown> | null }>
): number {
  return queue.filter((item) => {
    const status = String(item.status ?? "");
    if (status === "already_collected" || status === "backend_verified" || status === "complete"
      || status === "extracted" || status === "skipped" || status === "duplicate") {
      return false;
    }
    if (item.capture_status === "complete" || item.capture_status === "skipped") return false;
    return evidenceHasHybridRequiredMetrics(item.profile_card_evidence);
  }).length;
}

const HYBRID_HYDRATION_ORDER: ReadonlyArray<HybridHydrationSource> = [
  "profile_repository",
  "network_cache",
  "passive_aweme",
  "profile_post_api",
  "calibrated_non_modal_dom"
];

/** Network-backed sources that carry real engagement (not scan DOM stubs). */
export const HYBRID_TRUSTED_ENGAGEMENT_SOURCES: ReadonlySet<HybridHydrationSource> = new Set([
  "network_cache",
  "passive_aweme",
  "profile_post_api"
]);

/**
 * True when engagement metrics are backed by network/profile_post/detail evidence,
 * not only a profile_repository row with numeric zeros that passed required-field checks.
 */
export function hydrationEngagementIsTrustedForFlush(
  result: Pick<
    HybridHydrationResult,
    "fields" | "sources_used" | "raw_like_count_exact_numeric" | "raw_like_count_source"
  >
): boolean {
  if (result.sources_used.some((source) => HYBRID_TRUSTED_ENGAGEMENT_SOURCES.has(source))) {
    return true;
  }
  const likeSource = result.raw_like_count_source ?? "";
  if (result.raw_like_count_exact_numeric && likeSource.startsWith("statistics.")) {
    return true;
  }
  const { like_count, comment_count, favorite_count, share_count } = result.fields;
  const totalEngagement =
    (like_count ?? 0) + (comment_count ?? 0) + (favorite_count ?? 0) + (share_count ?? 0);
  if (totalEngagement > 0 && result.raw_like_count_exact_numeric) {
    return true;
  }
  return false;
}

const TRUSTED_VIEW_COUNT_FIELD_PATHS: ReadonlySet<string> = new Set([
  "statistics.play_count",
  "statistics.view_count",
  "stats.play_count",
  "stats.view_count",
  "aweme_statistics.play_count",
  "aweme_statistics.view_count",
  "aweme_detail.statistics.play_count",
  "aweme_detail.statistics.view_count",
  "mix_info.statis.play_vv"
]);

// ---------- Public API ----------

/**
 * Hydrate a single target from non-modal sources, in the proven pilot order:
 *   profile_repository → network_cache → passive_aweme → profile_post_api → calibrated_non_modal_dom
 * The earliest source that supplies a numeric value for a given field wins for that field
 * (per `mergeHydrationFields`); other fields continue to fill from later sources.
 *
 * Returns a result with `pending_reason` set when one or more required metric fields are still
 * null after merging all five sources. The caller should leave such targets in `pending` status.
 */
export function hydrateNonModalForAwemeId(
  awemeId: string,
  sources: HybridHydrationSourceBundle
): HybridHydrationResult {
  const profileRepositoryRecord = sources.profile_repository ?? {};
  const networkCacheRecord = networkRecordFromMetadata(sources.network_cache);
  const passiveAwemeRecord = sources.passive_aweme as unknown as Record<string, unknown> ?? {};
  const profilePostApiRecord = sources.profile_post_api as unknown as Record<string, unknown> ?? {};
  const calibratedDomRecord = sources.calibrated_non_modal_dom ?? {};

  const sourceRecords: Array<{ source: HybridHydrationSource; record: Record<string, unknown> }> = [
    { source: "profile_repository", record: profileRepositoryRecord },
    { source: "network_cache", record: networkCacheRecord },
    { source: "passive_aweme", record: passiveAwemeRecord },
    { source: "profile_post_api", record: profilePostApiRecord },
    { source: "calibrated_non_modal_dom", record: calibratedDomRecord }
  ];

  const baseAttempts = [
    { source: "profile_repository" as const, fields: fieldsFromRecord(profileRepositoryRecord), record: profileRepositoryRecord },
    { source: "network_cache" as const, fields: fieldsFromNetworkMetadata(sources.network_cache ?? undefined), record: networkCacheRecord },
    { source: "passive_aweme" as const, fields: fieldsFromPassiveTarget(sources.passive_aweme ?? undefined), record: passiveAwemeRecord },
    { source: "profile_post_api" as const, fields: fieldsFromPassiveTarget(sources.profile_post_api ?? undefined), record: profilePostApiRecord },
    { source: "calibrated_non_modal_dom" as const, fields: fieldsFromRecord(calibratedDomRecord), record: calibratedDomRecord }
  ];

  const mergedFields = baseAttempts.reduce<HybridHydrationFields>(
    (acc, attempt) => mergeHydrationFields(acc, attempt.fields),
    emptyHydrationFields()
  );

  const metricValueSource = metricValueSourcesFromAttempts(baseAttempts, mergedFields);
  const thumbnail = firstThumbnailFromAttempts(baseAttempts);
  const viewCountDiagnostics = buildViewCountDiagnosticsFromSources(sourceRecords);
  const likeCountSource = metricValueSource.like_count;
  const estimatedViewsDiagnostics = buildEstimatedViewsDiagnostics(mergedFields.like_count, likeCountSource);

  const postedEvidence = mergedPostedEvidence(baseAttempts);
  const titleEvidence = firstTitleEvidenceFromAttempts(baseAttempts, awemeId);
  const rawLikeEvidence = firstRawLikeEvidenceFromAttempts(baseAttempts);
  const displayLike = firstDisplayLikeFromAttempts(baseAttempts);

  const sourcesUsed = sourcesUsedFromMergedFields(baseAttempts, mergedFields, thumbnail, postedEvidence.source);
  const missingRequiredFields = missingRequiredMetricFields(mergedFields);
  let pendingReason = pendingReasonFromMergedResult(missingRequiredFields, thumbnail, postedEvidence.posted_at);
  const hydrationCore = {
    aweme_id: awemeId,
    fields: mergedFields,
    metric_value_source: metricValueSource,
    thumbnail,
    view_count_diagnostics: viewCountDiagnostics,
    estimated_views_diagnostics: estimatedViewsDiagnostics,
    posted: postedEvidence.posted,
    posted_at: postedEvidence.posted_at,
    posted_source: postedEvidence.source,
    title: titleEvidence.title,
    title_source: titleEvidence.source,
    title_is_id_fallback: titleEvidence.is_id_fallback,
    title_valid_real_text: titleEvidence.valid_real_text,
    raw_like_count_source: rawLikeEvidence.source,
    raw_like_count_value_type: rawLikeEvidence.value_type,
    raw_like_count_exact_numeric: rawLikeEvidence.exact_numeric,
    display_like_text: displayLike.text,
    display_like_text_source: displayLike.source,
    rounded_like_display_rejected_for_raw: displayLike.text != null && rawLikeEvidence.exact_numeric,
    sources_attempted: HYBRID_HYDRATION_ORDER.slice(),
    sources_used: sourcesUsed,
    missing_required_fields: missingRequiredFields
  };
  if (!pendingReason && !hydrationEngagementIsTrustedForFlush(hydrationCore)) {
    pendingReason = "stub_engagement_untrusted:profile_repository_only";
  }

  return {
    ...hydrationCore,
    pending_reason: pendingReason
  };
}

/**
 * Build a backend-compatible FullModalHarvestItemPayload from a hybrid hydration result.
 * Returns null when required metric fields are missing OR thumbnail/posted_at are missing,
 * because /douyin-extension/full-modal-harvest with commit_policy:"finalized_only" rejects
 * such items. Finalized items always carry finalized_metadata_source:"guarded_hybrid_network_cache".
 *
 * Hard invariants:
 *   - view_count is sourced ONLY from view_count_diagnostics.normalized_view_count.
 *   - estimated_views is NEVER assigned to view_count.
 *   - aweme_id is exact_aweme_id_only.
 */
export function buildFinalizedMetadataFromHybridHydration(
  hydration: HybridHydrationResult,
  options: { profile_url?: string | null } = {}
): FullModalHarvestItemPayload | null {
  if (hydration.pending_reason) return null;

  const sourceUrl = `https://www.douyin.com/video/${hydration.aweme_id}`;
  const viewCount = hydration.view_count_diagnostics.normalized_view_count;
  const realViewCountAvailable = hydration.view_count_diagnostics.real_view_count_found === "yes"
    && hydration.view_count_diagnostics.normalized_view_count_defaulted === "no";
  const dataQuality = realViewCountAvailable
    ? "real_view_count_present_high_confidence"
    : "real_view_count_null_low_confidence_or_missing";
  const postedText = typeof hydration.posted === "string" ? hydration.posted : hydration.posted != null ? String(hydration.posted) : null;
  const thumbnailUrl = hydration.thumbnail.valid_url === "yes" ? hydration.thumbnail.url : null;
  const extractionSource = hydration.sources_used.includes("network_cache") || hydration.metric_value_source.like_count === "network_cache"
    ? "page_network_cache_aweme"
    : "exact_aweme_network_cache_object";

  const item: FullModalHarvestItemPayload & { finalized_metadata_source: "guarded_hybrid_network_cache" } = {
    aweme_id: hydration.aweme_id,
    source_video_external_id: hydration.aweme_id,
    target_aweme_id: hydration.aweme_id,
    metadata_status: "ready",
    review_status: "pending_review",
    source_url: sourceUrl,
    page_url: options.profile_url ?? sourceUrl,
    modal_id: hydration.aweme_id,
    view_count: viewCount,
    real_view_count_available: realViewCountAvailable,
    real_view_count_data_quality: dataQuality,
    estimated_views: hydration.estimated_views_diagnostics.estimated_views,
    estimated_views_formula: "tiered_like_multiplier_v1",
    estimated_views_used: true,
    real_view_count_overwritten: false,
    finalized_metadata_source: "guarded_hybrid_network_cache",
    raw_dom_detail_metrics: {
      aweme_id: hydration.aweme_id,
      target_aweme_id: hydration.aweme_id,
      duration_seconds: hydration.fields.duration_seconds,
      like_count: hydration.fields.like_count,
      comment_count: hydration.fields.comment_count,
      favorite_count: hydration.fields.favorite_count,
      share_count: hydration.fields.share_count,
      view_count: viewCount,
      posted_text: postedText,
      posted_text_raw: postedText,
      posted_at: hydration.posted_at,
      posted_display: postedText,
      posted_source: hydration.posted_source ?? "network_cache",
      posted_parse_confidence: "guarded_hybrid_validated",
      thumbnail_url: thumbnailUrl,
      thumbnail_source: hydration.thumbnail.source,
      title: hydration.title,
      title_source: hydration.title_source,
      title_is_id_fallback: hydration.title_is_id_fallback,
      title_valid_real_text: hydration.title_valid_real_text,
      raw_like_count_source: hydration.raw_like_count_source,
      raw_like_count_value_type: hydration.raw_like_count_value_type,
      raw_like_count_exact_numeric: hydration.raw_like_count_exact_numeric,
      display_like_text: hydration.display_like_text,
      display_like_text_source: hydration.display_like_text_source,
      rounded_like_display_rejected_for_raw: hydration.rounded_like_display_rejected_for_raw,
      extraction_source: extractionSource,
      confidence: "high"
    },
    raw_evidence_summary: {
      has_network_aweme: hydration.sources_used.includes("network_cache") || hydration.sources_used.includes("passive_aweme") || hydration.sources_used.includes("profile_post_api"),
      has_detail_aweme: false,
      has_dom_snapshot: false,
      has_dom_detail_metrics: true,
      network_keys: hydration.sources_used.includes("network_cache") ? ["aweme_id", "raw_network_aweme", "raw_detail_aweme"] : [],
      detail_keys: [],
      dom_detail_metric_keys: [
        "duration_seconds", "like_count", "comment_count", "favorite_count", "share_count",
        "view_count", "posted_text", "posted_at", "thumbnail_url", "title"
      ],
      evidence_sources: ["guarded_hybrid_network_cache", "hybrid_network_cache_payload", extractionSource],
      evidence_collection_version: "phase17a_finalized_only_harvest"
    },
    profile_card_evidence: {
      aweme_id: hydration.aweme_id,
      source_url: sourceUrl,
      title: hydration.title,
      caption: hydration.title,
      desc: hydration.title,
      description: hydration.title,
      thumbnail_url: thumbnailUrl,
      cover_url: thumbnailUrl,
      poster_url: null,
      posted_text: postedText,
      posted_text_raw: postedText,
      posted_at: hydration.posted_at,
      posted_display: postedText,
      thumbnail_source: hydration.thumbnail.source,
      title_source: hydration.title_source,
      title_is_id_fallback: hydration.title_is_id_fallback,
      title_valid_real_text: hydration.title_valid_real_text,
      posted_source: hydration.posted_source ?? "network_cache",
      posted_parse_confidence: "guarded_hybrid_validated"
    },
    modal_aweme_id_before_extract: hydration.aweme_id,
    modal_aweme_id_after_extract: hydration.aweme_id,
    extracted_aweme_id: hydration.aweme_id,
    data_integrity_status: "passed",
    data_integrity_reason: null,
    metric_signature: null,
    duplicate_signature_warning: null
  } as FullModalHarvestItemPayload & { finalized_metadata_source: "guarded_hybrid_network_cache" };

  return item;
}

// ---------- Internal helpers (mirrored from popup.ts pilot) ----------

export function emptyHydrationFields(): HybridHydrationFields {
  return {
    duration_seconds: null,
    duration_text: null,
    like_count: null,
    comment_count: null,
    favorite_count: null,
    share_count: null
  };
}

function mergeEngagementMetricField(base: number | null, next: number | null): number | null {
  if (base == null) return next;
  if (next == null) return base;
  // Repository scan stubs often carry numeric zeros; later network sources must win.
  if (base <= 0 && next > 0) return next;
  if (base > 0) return base;
  return base;
}

export function mergeHydrationFields(base: HybridHydrationFields, next: HybridHydrationFields): HybridHydrationFields {
  return {
    duration_seconds: base.duration_seconds ?? next.duration_seconds,
    duration_text: base.duration_text ?? next.duration_text,
    like_count: mergeEngagementMetricField(base.like_count, next.like_count),
    comment_count: mergeEngagementMetricField(base.comment_count, next.comment_count),
    favorite_count: mergeEngagementMetricField(base.favorite_count, next.favorite_count),
    share_count: mergeEngagementMetricField(base.share_count, next.share_count)
  };
}

export function fieldsFromRecord(record: Record<string, unknown>): HybridHydrationFields {
  const statistics = recordValue(record.statistics)
    ?? recordValue(record.stats)
    ?? recordValue(recordValue(record.raw_network_aweme)?.statistics)
    ?? recordValue(recordValue(record.raw_detail_aweme)?.statistics);
  const stats = statistics ?? {};
  const durationText = stringFromEvidence(record, "duration_text");
  return {
    duration_seconds: resolveHybridDurationSeconds(record, null, durationText),
    duration_text: durationText,
    like_count: rawLikeCountFromRecord(record),
    comment_count: numberFromEvidence(record, "comment_count") ?? numberFromEvidence(stats, "comment_count"),
    favorite_count: numberFromEvidence(record, "favorite_count") ?? numberFromEvidence(stats, "collect_count"),
    share_count: numberFromEvidence(record, "share_count")
      ?? numberFromEvidence(stats, "share_count")
      ?? numberFromEvidence(stats, "forward_count")
  };
}

export function fieldsFromNetworkMetadata(item: NetworkVideoMetadata | undefined): HybridHydrationFields {
  if (!item) return emptyHydrationFields();
  // Use the merged record so top-level cache fields + raw aweme are both visible
  // to duration/image-post recovery (production: network_cache present but
  // duration_seconds still missing for image/slide posts).
  const mergedRecord = networkRecordFromMetadata(item);
  const baseFields = fieldsFromRecord(mergedRecord);
  return {
    ...baseFields,
    duration_seconds: resolveHybridDurationSeconds(mergedRecord, item.duration_seconds, item.duration_text ?? baseFields.duration_text),
    duration_text: item.duration_text ?? baseFields.duration_text,
    like_count: item.like_count ?? baseFields.like_count,
    comment_count: item.comment_count ?? baseFields.comment_count,
    favorite_count: item.favorite_count ?? baseFields.favorite_count,
    share_count: item.share_count ?? baseFields.share_count
  };
}

export function fieldsFromPassiveTarget(target: PassiveNetworkProbeStoredTarget22C12A | undefined): HybridHydrationFields {
  if (!target) return emptyHydrationFields();
  const record = target as unknown as Record<string, unknown>;
  return {
    duration_seconds: resolveHybridDurationSeconds(record, target.duration, null),
    duration_text: null,
    like_count: target.like_count ?? null,
    comment_count: target.comment_count ?? null,
    // Was hard-coded null — passive-only targets (common for the last few
    // profile videos still in probe memory but missing from network cache)
    // always became skipped_pending with missing_required_fields:favorite_count.
    favorite_count: target.favorite_count ?? null,
    share_count: target.share_count ?? null
  };
}

export function thumbnailFromRecord(record: Record<string, unknown>, source: HybridHydrationSource): HybridThumbnailEvidence {
  const video = recordValue(record.video) ?? {};
  const rawNetworkAweme = recordValue(record.raw_network_aweme) ?? {};
  const rawDetailAweme = recordValue(record.raw_detail_aweme) ?? {};
  const rawNetworkVideo = recordValue(rawNetworkAweme.video) ?? {};
  const rawDetailVideo = recordValue(rawDetailAweme.video) ?? {};
  const imagePostInfo = recordValue(record.image_post_info) ?? recordValue(record.imagePostInfo) ?? {};
  const images = Array.isArray(record.images)
    ? record.images
    : Array.isArray(imagePostInfo.images)
      ? imagePostInfo.images as unknown[]
      : [];
  const firstImage = recordValue(images[0]) ?? {};
  const candidates: Array<[string, unknown]> = [
    ["thumbnail_url", record.thumbnail_url],
    ["cover_url", record.cover_url],
    ["poster_url", record.poster_url],
    ["origin_cover", record.origin_cover],
    ["dynamic_cover", record.dynamic_cover],
    ["cover", record.cover],
    ["video.origin_cover", video.origin_cover],
    ["video.cover_url", video.cover_url],
    ["video.cover", video.cover],
    ["video.dynamic_cover", video.dynamic_cover],
    ["video.poster", video.poster],
    ["raw_network_aweme.video.origin_cover", rawNetworkVideo.origin_cover],
    ["raw_network_aweme.video.cover", rawNetworkVideo.cover],
    ["raw_network_aweme.video.dynamic_cover", rawNetworkVideo.dynamic_cover],
    ["raw_detail_aweme.video.origin_cover", rawDetailVideo.origin_cover],
    ["raw_detail_aweme.video.cover", rawDetailVideo.cover],
    ["raw_detail_aweme.video.dynamic_cover", rawDetailVideo.dynamic_cover],
    ["images[0].url_list", firstImage.url_list ?? firstImage.url ?? firstImage.download_url_list],
    ["images[0].cover", firstImage.cover ?? firstImage.origin_cover]
  ];
  // Never return the first unusable URL — Douyin often puts a bare tos uri or
  // protocol-relative //p3-sign... before a later https cover. Returning early
  // with valid_url=no caused permanent missing_valid_thumbnail (production:
  // last queue items + Capture Inbox "needs action" for thumbnail).
  for (const [field, value] of candidates) {
    const url = firstThumbnailUrl(value);
    if (!url) continue;
    const normalized = normalizeThumbnailUrl(url);
    if (!normalized) continue;
    return {
      present: "yes",
      field_used: field,
      source,
      valid_url: "yes",
      url: normalized,
      url_host: safeUrlHost(normalized)
    };
  }
  return missingThumbnailEvidence();
}

export function missingThumbnailEvidence(): HybridThumbnailEvidence {
  return { present: "no", field_used: null, source: "missing", valid_url: "no", url: null, url_host: null };
}

export function buildViewCountDiagnosticsFromSources(
  sources: Array<{ source: HybridHydrationSource; record: Record<string, unknown> }>
): HybridViewCountDiagnostics {
  for (const { source, record } of sources) {
    const trusted = collectTrustedViewCountCandidates(record);
    for (const candidate of trusted) {
      const parsed = parseViewCountScalar(candidate.value);
      if (parsed != null && parsed >= 0) {
        return {
          normalized_view_count: parsed,
          normalized_view_count_source: source,
          normalized_view_count_field_used: candidate.path,
          normalized_view_count_defaulted: "no",
          normalized_view_count_default_reason: null,
          real_view_count_found: "yes",
          selected_field_trusted: "yes",
          selected_field_semantic_reason: "trusted_views_field_allowlist"
        };
      }
    }
  }
  return {
    normalized_view_count: null,
    normalized_view_count_source: null,
    normalized_view_count_field_used: null,
    normalized_view_count_defaulted: "yes",
    normalized_view_count_default_reason: "missing_trusted_candidate_field",
    real_view_count_found: "no",
    selected_field_trusted: "no",
    selected_field_semantic_reason: null
  };
}

export function buildEstimatedViewsDiagnostics(
  likeCount: number | null,
  likeCountSource: HybridHydrationSource | null
): HybridEstimatedViewsDiagnostics {
  const sourceLabel = likeCountSource ?? "missing";
  if (likeCount == null) {
    return {
      estimated_views: null,
      estimated_views_source: "missing_like_count",
      estimated_views_formula: "tiered_like_multiplier_v1",
      like_count_used: null,
      like_count_source: likeCountSource,
      multiplier_used: null,
      rounded: "no",
      confidence: "low",
      validity: "missing_like_count"
    };
  }
  if (!Number.isFinite(likeCount) || likeCount < 0) {
    return {
      estimated_views: null,
      estimated_views_source: "invalid_like_count",
      estimated_views_formula: "tiered_like_multiplier_v1",
      like_count_used: null,
      like_count_source: likeCountSource,
      multiplier_used: null,
      rounded: "no",
      confidence: "low",
      validity: "invalid_like_count"
    };
  }
  if (/text|compact|dom|calibrated/i.test(sourceLabel) && !/network|statistics|digg|raw/i.test(sourceLabel)) {
    return {
      estimated_views: null,
      estimated_views_source: "blocked_compact_or_display_like_count",
      estimated_views_formula: "tiered_like_multiplier_v1",
      like_count_used: null,
      like_count_source: likeCountSource,
      multiplier_used: null,
      rounded: "no",
      confidence: "low",
      validity: "invalid_like_count"
    };
  }
  const multiplier = estimatedViewsMultiplierForLikes(likeCount);
  return {
    estimated_views: estimateViewsFromLikes(likeCount),
    estimated_views_source: "derived_from_like_count",
    estimated_views_formula: "tiered_like_multiplier_v1",
    like_count_used: likeCount,
    like_count_source: sourceLabel,
    multiplier_used: multiplier,
    rounded: "yes",
    confidence: likeCount >= 1_000 ? "high" : likeCount >= 100 ? "medium" : "low",
    validity: "valid"
  };
}

export function estimateViewsFromLikes(likeCount: number): number {
  if (likeCount <= 0) return 0;
  return Math.round(likeCount * estimatedViewsMultiplierForLikes(likeCount));
}

export function estimatedViewsMultiplierForLikes(likeCount: number): number {
  if (likeCount < 100) return 45;
  if (likeCount < 1_000) return 35;
  if (likeCount < 10_000) return 28;
  if (likeCount < 100_000) return 22;
  return 18;
}

// ---------- Internal: per-source extraction primitives ----------

function rawLikeCountFromRecord(record: Record<string, unknown>): number | null {
  return rawLikeCountEvidenceFromRecord(record).value;
}

function rawLikeCountEvidenceFromRecord(record: Record<string, unknown>): { value: number | null; source: string | null; value_type: string; exact_numeric: boolean } {
  const rawNetworkStatistics = recordValue(recordValue(record.raw_network_aweme)?.statistics);
  const rawDetailStatistics = recordValue(recordValue(record.raw_detail_aweme)?.statistics);
  const statistics = recordValue(record.statistics) ?? recordValue(record.stats) ?? rawNetworkStatistics ?? rawDetailStatistics;
  const stats = statistics ?? {};
  const candidates: Array<[string, unknown]> = [
    ["statistics.digg_count", stats.digg_count],
    ["statistics.like_count", stats.like_count],
    ["aweme_statistics.digg_count", recordValue(record.aweme_statistics)?.digg_count],
    ["aweme_statistics.like_count", recordValue(record.aweme_statistics)?.like_count],
    ["raw_like_count", record.raw_like_count],
    ["like_count", record.like_count]
  ];
  for (const [source, raw] of candidates) {
    if (typeof raw === "number" && Number.isFinite(raw)) {
      return { value: raw, source, value_type: "number", exact_numeric: true };
    }
  }
  const firstRaw = candidates.find(([, raw]) => raw != null)?.[1] ?? null;
  return {
    value: null,
    source: null,
    value_type: firstRaw == null ? "null" : Array.isArray(firstRaw) ? "array" : typeof firstRaw,
    exact_numeric: false
  };
}

function networkRecordFromMetadata(item: NetworkVideoMetadata | null): Record<string, unknown> {
  if (!item) return {};
  const raw = (item.raw_detail_aweme ?? item.raw_network_aweme ?? {}) as Record<string, unknown>;
  // Prefer raw aweme for nested statistics/video, but keep top-level cache fields
  // (thumbnail_url, cover_url, posted_at). Using only raw_network_aweme dropped
  // covers that exist on NetworkVideoMetadata and caused missing_valid_thumbnail
  // even when the cache entry had a usable cover URL.
  return {
    ...raw,
    thumbnail_url: item.thumbnail_url ?? item.cover_url ?? item.origin_cover ?? raw.thumbnail_url ?? null,
    cover_url: item.cover_url ?? item.origin_cover ?? raw.cover_url ?? null,
    origin_cover: item.origin_cover ?? raw.origin_cover ?? null,
    dynamic_cover: item.dynamic_cover ?? raw.dynamic_cover ?? null,
    posted_at: item.posted_at ?? raw.posted_at ?? null,
    duration_seconds: item.duration_seconds ?? raw.duration_seconds ?? null,
    duration_text: item.duration_text ?? raw.duration_text ?? null,
    like_count: item.like_count ?? raw.like_count ?? null,
    comment_count: item.comment_count ?? raw.comment_count ?? null,
    favorite_count: item.favorite_count ?? raw.favorite_count ?? null,
    share_count: item.share_count ?? raw.share_count ?? null,
    raw_network_aweme: item.raw_network_aweme ?? null,
    raw_detail_aweme: item.raw_detail_aweme ?? null
  };
}

function metricValueSourcesFromAttempts(
  attempts: Array<{ source: HybridHydrationSource; fields: HybridHydrationFields }>,
  merged: HybridHydrationFields
): Record<HybridMetricField, HybridHydrationSource | null> {
  const sources = {} as Record<HybridMetricField, HybridHydrationSource | null>;
  for (const field of HYBRID_REQUIRED_METRIC_FIELDS) {
    const value = merged[field];
    sources[field] = attempts.find((attempt) => value != null && attempt.fields[field] === value)?.source ?? null;
  }
  return sources;
}

function firstThumbnailFromAttempts(
  attempts: Array<{ source: HybridHydrationSource; record: Record<string, unknown> }>
): HybridThumbnailEvidence {
  for (const attempt of attempts) {
    const t = thumbnailFromRecord(attempt.record, attempt.source);
    if (t.present === "yes") return t;
  }
  return missingThumbnailEvidence();
}

function mergedPostedEvidence(
  attempts: Array<{ source: HybridHydrationSource; record: Record<string, unknown> }>
): { posted: string | number | null; posted_at: string | null; source: HybridHydrationSource | "missing" } {
  for (const attempt of attempts) {
    const posted = firstPresentValue(
      attempt.record.posted ?? attempt.record.posted_text,
      attempt.record.posted_at,
      attempt.record.create_time,
      attempt.record.create_timestamp,
      attempt.record.publish_time,
      attempt.record.publish_timestamp,
      attempt.record.aweme_create_time,
      recordValue(attempt.record.raw_network_aweme)?.create_time,
      recordValue(attempt.record.raw_detail_aweme)?.create_time
    );
    const postedAt = normalizePostedAt(posted) ?? stringFromEvidence(attempt.record, "posted_at");
    if (posted != null || postedAt) {
      return {
        posted: typeof posted === "string" || typeof posted === "number" ? posted : null,
        posted_at: postedAt,
        source: attempt.source
      };
    }
  }
  return { posted: null, posted_at: null, source: "missing" };
}

function firstTitleEvidenceFromAttempts(
  attempts: Array<{ source: HybridHydrationSource; record: Record<string, unknown> }>,
  awemeId: string
): { title: string | null; source: string | null; is_id_fallback: boolean; valid_real_text: boolean } {
  for (const attempt of attempts) {
    const evidence = titleEvidenceFromRecord(attempt.record, awemeId);
    if (evidence.valid_real_text) return evidence;
  }
  return { title: awemeId, source: "aweme_id_fallback", is_id_fallback: true, valid_real_text: false };
}

function titleEvidenceFromRecord(
  record: Record<string, unknown>,
  awemeId: string
): { title: string | null; source: string | null; is_id_fallback: boolean; valid_real_text: boolean } {
  const rawNetworkAweme = recordValue(record.raw_network_aweme) ?? {};
  const rawDetailAweme = recordValue(record.raw_detail_aweme) ?? {};
  const candidates: Array<[string, unknown]> = [
    ["title", record.title],
    ["caption", record.caption],
    ["desc", record.desc],
    ["description", record.description],
    ["raw_network_aweme.title", rawNetworkAweme.title],
    ["raw_network_aweme.desc", rawNetworkAweme.desc],
    ["raw_detail_aweme.title", rawDetailAweme.title],
    ["raw_detail_aweme.desc", rawDetailAweme.desc]
  ];
  const ids = new Set([
    record.aweme_id,
    record.video_id,
    rawNetworkAweme.aweme_id,
    rawDetailAweme.aweme_id,
    awemeId
  ].map((value) => String(value ?? "").trim()).filter(Boolean));
  for (const [source, raw] of candidates) {
    const text = typeof raw === "string" ? raw.trim() : "";
    if (!text || ids.has(text)) continue;
    return { title: text, source, is_id_fallback: false, valid_real_text: true };
  }
  return { title: null, source: null, is_id_fallback: false, valid_real_text: false };
}

function firstRawLikeEvidenceFromAttempts(
  attempts: Array<{ source: HybridHydrationSource; record: Record<string, unknown> }>
): { value: number | null; source: string | null; value_type: string; exact_numeric: boolean } {
  for (const attempt of attempts) {
    const evidence = rawLikeCountEvidenceFromRecord(attempt.record);
    if (evidence.exact_numeric) return evidence;
  }
  return { value: null, source: null, value_type: "null", exact_numeric: false };
}

function firstDisplayLikeFromAttempts(
  attempts: Array<{ source: HybridHydrationSource; record: Record<string, unknown> }>
): { text: string | null; source: string | null } {
  for (const attempt of attempts) {
    const rawNetworkAweme = recordValue(attempt.record.raw_network_aweme) ?? {};
    const rawDetailAweme = recordValue(attempt.record.raw_detail_aweme) ?? {};
    const candidates: Array<[string, unknown]> = [
      ["like_count_text", attempt.record.like_count_text],
      ["display_like_text", attempt.record.display_like_text],
      ["raw_network_aweme.like_count_text", rawNetworkAweme.like_count_text],
      ["raw_detail_aweme.like_count_text", rawDetailAweme.like_count_text]
    ];
    for (const [source, raw] of candidates) {
      const text = typeof raw === "string" ? raw.trim() : "";
      if (text) return { text, source };
    }
  }
  return { text: null, source: null };
}

function sourcesUsedFromMergedFields(
  attempts: Array<{ source: HybridHydrationSource; fields: HybridHydrationFields }>,
  merged: HybridHydrationFields,
  thumbnail: HybridThumbnailEvidence,
  postedSource: HybridHydrationSource | "missing"
): HybridHydrationSource[] {
  const used = new Set<HybridHydrationSource>();
  for (const field of HYBRID_REQUIRED_METRIC_FIELDS) {
    const value = merged[field];
    const sourceUsed = attempts.find((attempt) => value != null && attempt.fields[field] === value)?.source;
    if (sourceUsed) used.add(sourceUsed);
  }
  if (thumbnail.present === "yes" && thumbnail.source !== "missing") used.add(thumbnail.source);
  if (postedSource !== "missing") used.add(postedSource);
  return HYBRID_HYDRATION_ORDER.filter((source) => used.has(source));
}

function missingRequiredMetricFields(fields: HybridHydrationFields): string[] {
  return HYBRID_REQUIRED_METRIC_FIELDS.filter((field) => {
    const value = fields[field];
    if (typeof value !== "number" || !Number.isFinite(value)) return true;
    if (field === "duration_seconds") return value <= 0;
    return value < 0;
  });
}

function pendingReasonFromMergedResult(
  missingRequiredFields: string[],
  thumbnail: HybridThumbnailEvidence,
  postedAt: string | null
): string | null {
  if (missingRequiredFields.length > 0) {
    return `missing_required_fields:${missingRequiredFields.join(",")}`;
  }
  if (thumbnail.valid_url !== "yes") return "missing_valid_thumbnail";
  if (!postedAt) return "missing_posted_at";
  return null;
}

function collectTrustedViewCountCandidates(record: Record<string, unknown>): Array<{ path: string; value: unknown }> {
  const trusted: Array<{ path: string; value: unknown }> = [];
  const visited = new Set<unknown>();
  const maxDepth = 6;
  const maxNodes = 240;
  let nodes = 0;
  const walk = (value: unknown, path: string, depth: number): void => {
    if (nodes >= maxNodes || depth > maxDepth) return;
    if (value && typeof value === "object") {
      if (visited.has(value)) return;
      visited.add(value);
    }
    const rec = recordValue(value);
    if (!rec) return;
    for (const [key, child] of Object.entries(rec)) {
      if (nodes >= maxNodes) return;
      nodes += 1;
      const childPath = path ? `${path}.${key}` : key;
      if (TRUSTED_VIEW_COUNT_FIELD_PATHS.has(childPath)) {
        trusted.push({ path: childPath, value: child });
      }
      if (recordValue(child)) walk(child, childPath, depth + 1);
    }
  };
  walk(record, "", 0);
  return trusted;
}

function parseViewCountScalar(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value) && value >= 0) return value;
  if (typeof value !== "string") return null;
  const normalized = value.trim().replace(/,/g, "");
  const match = normalized.match(/^(\d+(?:\.\d+)?)(万|w|k|m)?$/i);
  if (!match) return null;
  const base = Number(match[1]);
  if (!Number.isFinite(base) || base < 0) return null;
  const unit = (match[2] ?? "").toLowerCase();
  const multiplier = unit === "万" || unit === "w" ? 10_000 : unit === "k" ? 1_000 : unit === "m" ? 1_000_000 : 1;
  return Math.round(base * multiplier);
}

// ---------- Internal: low-level record + URL utilities ----------

function recordValue(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : null;
}

function numberFromEvidence(record: Record<string, unknown>, key: string): number | null {
  const raw = record[key];
  if (typeof raw === "number" && Number.isFinite(raw)) return raw;
  if (typeof raw === "string") {
    const trimmed = raw.trim();
    if (!trimmed) return null;
    const numeric = Number(trimmed);
    if (Number.isFinite(numeric)) return numeric;
  }
  return null;
}

function stringFromEvidence(record: Record<string, unknown>, key: string): string | null {
  const raw = record[key];
  return typeof raw === "string" && raw.trim() ? raw.trim() : null;
}

function normalizeHybridDurationSeconds(value: number | null): number | null {
  if (value == null || !Number.isFinite(value) || value <= 0) return null;
  // Douyin video.duration is usually milliseconds when > 1000.
  return value > 1000 ? Math.round(value / 1000) : Math.round(value);
}

/**
 * Resolve a positive duration_seconds from every known Douyin shape.
 * Production: last queue items often have network_cache/passive entries but no
 * video.duration (image/slide posts, or partial list payloads) → forever
 * skipped_pending with missing_required_fields:duration_seconds.
 */
function resolveHybridDurationSeconds(
  record: Record<string, unknown>,
  explicitSeconds: number | null | undefined,
  explicitText: string | null | undefined
): number | null {
  const video = recordValue(record.video) ?? recordValue(record.video_info) ?? recordValue(record.videoInfo) ?? {};
  const music = recordValue(record.music) ?? {};
  const rawNetwork = recordValue(record.raw_network_aweme) ?? {};
  const rawDetail = recordValue(record.raw_detail_aweme) ?? {};
  const rawNetworkVideo = recordValue(rawNetwork.video) ?? {};
  const rawDetailVideo = recordValue(rawDetail.video) ?? {};
  const numericCandidates = [
    explicitSeconds,
    numberFromEvidence(record, "duration_seconds"),
    numberFromEvidence(video, "duration"),
    numberFromEvidence(video, "duration_ms"),
    numberFromEvidence(video, "durationMs"),
    numberFromEvidence(record, "duration"),
    numberFromEvidence(record, "duration_ms"),
    numberFromEvidence(music, "duration"),
    numberFromEvidence(music, "end_time"),
    numberFromEvidence(rawNetworkVideo, "duration"),
    numberFromEvidence(rawNetworkVideo, "duration_ms"),
    numberFromEvidence(rawDetailVideo, "duration"),
    numberFromEvidence(rawDetailVideo, "duration_ms"),
    numberFromEvidence(rawNetwork, "duration"),
    numberFromEvidence(rawDetail, "duration")
  ];
  for (const candidate of numericCandidates) {
    const normalized = normalizeHybridDurationSeconds(typeof candidate === "number" ? candidate : null);
    if (normalized != null) return normalized;
  }

  const text = explicitText ?? stringFromEvidence(record, "duration_text") ?? stringFromEvidence(record, "durationText");
  const fromText = parseDurationTextToSeconds(text);
  if (fromText != null) return fromText;

  const fromImages = durationSecondsFromImagePost(record)
    ?? durationSecondsFromImagePost(rawNetwork)
    ?? durationSecondsFromImagePost(rawDetail);
  if (fromImages != null) return fromImages;

  return null;
}

function parseDurationTextToSeconds(text: string | null | undefined): number | null {
  if (!text || typeof text !== "string") return null;
  const trimmed = text.trim();
  const match = /^(?:(\d{1,2}):)?(\d{1,2}):(\d{2})$/.exec(trimmed);
  if (!match) return null;
  const hours = match[1] ? Number(match[1]) : 0;
  const minutes = Number(match[2]);
  const seconds = Number(match[3]);
  if (![hours, minutes, seconds].every((value) => Number.isFinite(value))) return null;
  const total = hours * 3600 + minutes * 60 + seconds;
  return total > 0 ? total : null;
}

/** Image / note / slideshow posts often omit video.duration. */
function durationSecondsFromImagePost(record: Record<string, unknown>): number | null {
  const images = Array.isArray(record.images)
    ? record.images
    : Array.isArray(recordValue(record.image_post_info)?.images)
      ? (recordValue(record.image_post_info)?.images as unknown[])
      : Array.isArray(recordValue(record.imagePostInfo)?.images)
        ? (recordValue(record.imagePostInfo)?.images as unknown[])
        : null;
  if (images && images.length > 0) {
    let total = 0;
    for (const image of images) {
      const imageRecord = recordValue(image) ?? {};
      const perImage = normalizeHybridDurationSeconds(
        numberFromEvidence(imageRecord, "duration")
          ?? numberFromEvidence(imageRecord, "duration_ms")
          ?? numberFromEvidence(imageRecord, "durationMs")
      );
      // Douyin slides default to ~3s when per-image duration is absent.
      total += perImage ?? 3;
    }
    return total > 0 ? total : null;
  }
  const awemeType = numberFromEvidence(record, "aweme_type") ?? numberFromEvidence(record, "awemeType");
  // Common Douyin non-video aweme types (image / note / carousel).
  if (awemeType === 2 || awemeType === 68 || awemeType === 150 || awemeType === 51) return 1;
  if (record.image_post_info || record.imagePostInfo || record.note_id || record.notes) return 1;
  return null;
}

function firstPresentValue(...values: unknown[]): unknown {
  return values.find((value) => value != null && !(typeof value === "string" && !value.trim())) ?? null;
}

function normalizePostedAt(value: unknown): string | null {
  const date = postedDateFromValue(value);
  return date ? date.toISOString() : null;
}

function postedDateFromValue(value: unknown): Date | null {
  if (typeof value === "string" && value.trim()) {
    const trimmed = value.trim();
    const numeric = Number(trimmed);
    if (Number.isFinite(numeric) && /^\d{10,13}$/.test(trimmed)) return postedDateFromTimestamp(numeric);
    const parsed = Date.parse(trimmed);
    if (Number.isFinite(parsed)) return plausiblePostedDate(new Date(parsed));
  }
  if (typeof value === "number" && Number.isFinite(value)) return postedDateFromTimestamp(value);
  return null;
}

function postedDateFromTimestamp(value: number): Date | null {
  const millis = value > 10_000_000_000 ? value : value * 1000;
  return plausiblePostedDate(new Date(millis));
}

function plausiblePostedDate(date: Date): Date | null {
  const time = date.getTime();
  const min = Date.UTC(2016, 0, 1);
  const max = Date.now() + 86_400_000;
  return Number.isFinite(time) && time >= min && time <= max ? date : null;
}

function firstThumbnailUrl(value: unknown): string | null {
  if (typeof value === "string" && value.trim()) return value.trim();
  if (Array.isArray(value)) {
    for (const item of value) {
      const url = firstThumbnailUrl(item);
      if (url) return url;
    }
    return null;
  }
  const record = recordValue(value);
  if (!record) return null;
  return firstThumbnailUrl(record.url_list)
    ?? firstThumbnailUrl(record.urlList)
    ?? firstThumbnailUrl(record.download_url_list)
    ?? firstThumbnailUrl(record.url)
    ?? firstThumbnailUrl(record.uri)
    ?? firstThumbnailUrl(record.src)
    ?? firstThumbnailUrl(record.href);
}

/** Accept https/http, protocol-relative covers, and promote www.douyin.com/tos-* to CDN. */
function normalizeThumbnailUrl(value: string): string | null {
  const trimmed = value.trim();
  if (!trimmed) return null;
  const withProtocol = trimmed.startsWith("//") ? `https:${trimmed}` : trimmed;
  if (!/^https?:\/\//i.test(withProtocol)) return null;
  if (!safeUrlHost(withProtocol)) return null;
  return promoteDouyinThumbnailToCdnUrl(withProtocol) ?? withProtocol;
}

function isSafeThumbnailUrl(value: string): boolean {
  return normalizeThumbnailUrl(value) != null;
}

function safeUrlHost(value: string): string | null {
  try {
    return new URL(value).hostname || null;
  } catch {
    return null;
  }
}
