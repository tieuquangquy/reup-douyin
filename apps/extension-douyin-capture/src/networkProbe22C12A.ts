import type {
  PassiveNetworkProbeBatchMessage22C12A,
  PassiveNetworkProbeCursorFields22C12BR2,
  PassiveNetworkProbeEndpointKind22C12A,
  PassiveNetworkProbeStoredTarget22C12A,
  PassiveNetworkProbeTarget22C12A
} from "./types.js";

export type PassiveNetworkProbeSummary22C12A = {
  network_probe_version: "22C-12A-R3";
  network_probe_installed: "yes" | "no";
  network_probe_bridge_ready: "yes" | "no";
  network_probe_page_bridge_ready: "yes" | "no";
  network_probe_content_listener_ready: "yes" | "no";
  network_probe_page_script_injection_attempted: "yes" | "no";
  network_probe_page_script_injected: "yes" | "no";
  network_probe_page_ready_at: string | null;
  network_probe_batches_seen: number;
  network_probe_unique_aweme_count: number;
  network_probe_candidate_endpoint_count: number;
  network_probe_endpoint_count: number;
  network_probe_endpoint_samples: string[];
  network_probe_first_10_aweme_ids: string[];
  network_probe_last_10_aweme_ids: string[];
  network_probe_last_batch_at: string | null;
  network_probe_last_error: string | null;
  network_profile_post_unique_count: number;
  network_favorite_unique_count: number;
  network_other_aweme_unique_count: number;
  network_excluded_favorite_count: number;
  network_excluded_other_count: number;
};

type ExtractedPassiveNetworkBatch22C12A = Omit<PassiveNetworkProbeBatchMessage22C12A, "type" | "traceVersion">;

const MAX_TARGETS_PER_BATCH_22C12A = 80;
const MAX_DESC_LENGTH_22C12A = 280;

export function createPassiveNetworkProbeSummary22C12A(): PassiveNetworkProbeSummary22C12A {
  return {
    network_probe_version: "22C-12A-R3",
    network_probe_installed: "no",
    network_probe_bridge_ready: "no",
    network_probe_page_bridge_ready: "no",
    network_probe_content_listener_ready: "no",
    network_probe_page_script_injection_attempted: "no",
    network_probe_page_script_injected: "no",
    network_probe_page_ready_at: null,
    network_probe_batches_seen: 0,
    network_probe_unique_aweme_count: 0,
    network_probe_candidate_endpoint_count: 0,
    network_probe_endpoint_count: 0,
    network_probe_endpoint_samples: [],
    network_probe_first_10_aweme_ids: [],
    network_probe_last_10_aweme_ids: [],
    network_probe_last_batch_at: null,
    network_probe_last_error: null,
    network_profile_post_unique_count: 0,
    network_favorite_unique_count: 0,
    network_other_aweme_unique_count: 0,
    network_excluded_favorite_count: 0,
    network_excluded_other_count: 0
  };
}

export function markPassiveNetworkProbeListenerReady22C12A(current: PassiveNetworkProbeSummary22C12A): PassiveNetworkProbeSummary22C12A {
  return {
    ...current,
    network_probe_version: "22C-12A-R3",
    network_probe_content_listener_ready: "yes"
  };
}

export function markPassiveNetworkProbeInjectionAttempted22C12A(current: PassiveNetworkProbeSummary22C12A): PassiveNetworkProbeSummary22C12A {
  return {
    ...current,
    network_probe_version: "22C-12A-R3",
    network_probe_page_script_injection_attempted: "yes",
    network_probe_last_error: current.network_probe_last_error
  };
}

export function markPassiveNetworkProbeInjected22C12A(current: PassiveNetworkProbeSummary22C12A): PassiveNetworkProbeSummary22C12A {
  return {
    ...current,
    network_probe_version: "22C-12A-R3",
    network_probe_page_script_injected: "yes"
  };
}

export function markPassiveNetworkProbeReady22C12A(current: PassiveNetworkProbeSummary22C12A, at: string): PassiveNetworkProbeSummary22C12A {
  return {
    ...current,
    network_probe_version: "22C-12A-R3",
    network_probe_installed: "yes",
    network_probe_bridge_ready: "yes",
    network_probe_page_bridge_ready: "yes",
    network_probe_page_ready_at: at,
    network_probe_last_error: null
  };
}

export function markPassiveNetworkProbeError22C12A(current: PassiveNetworkProbeSummary22C12A, error: string): PassiveNetworkProbeSummary22C12A {
  return {
    ...current,
    network_probe_version: "22C-12A-R3",
    network_probe_installed: "no",
    network_probe_bridge_ready: "no",
    network_probe_page_bridge_ready: "no",
    network_probe_last_error: error
  };
}

export function mergePassiveNetworkProbeBatch22C12A(
  current: PassiveNetworkProbeSummary22C12A,
  batch: PassiveNetworkProbeBatchMessage22C12A,
  at: string
): PassiveNetworkProbeSummary22C12A {
  const currentIds = [
    ...current.network_probe_first_10_aweme_ids,
    ...current.network_probe_last_10_aweme_ids
  ];
  const mergedIds = uniqueStrings22C12A([
    ...currentIds,
    ...batch.targets.map((target) => target.aweme_id)
  ]);
  const endpointSamples = uniqueStrings22C12A([
    ...current.network_probe_endpoint_samples,
    batch.urlPath
  ]).slice(0, 5);
  return {
    ...current,
    network_probe_version: "22C-12A-R3",
    network_probe_installed: "yes",
    network_probe_bridge_ready: "yes",
    network_probe_page_bridge_ready: "yes",
    network_probe_batches_seen: current.network_probe_batches_seen + 1,
    network_probe_unique_aweme_count: mergedIds.length,
    network_probe_candidate_endpoint_count: endpointSamples.length,
    network_probe_endpoint_count: endpointSamples.length,
    network_probe_endpoint_samples: endpointSamples,
    network_probe_first_10_aweme_ids: mergedIds.slice(0, 10),
    network_probe_last_10_aweme_ids: mergedIds.slice(-10),
    network_probe_last_batch_at: at,
    network_probe_last_error: null
  };
}

export function extractPassiveNetworkBatch22C12A(input: {
  payload: unknown;
  urlPath: string;
  requestUrl?: string | null;
  method?: string | null;
  status?: number | null;
}): ExtractedPassiveNetworkBatch22C12A | null {
  const { payload } = input;
  const requestUrl = typeof input.requestUrl === "string" && input.requestUrl.trim() ? input.requestUrl.trim() : null;
  const targets = collectPassiveTargets22C12A(payload)
    .slice(0, MAX_TARGETS_PER_BATCH_22C12A)
    .map((target) => ({ ...target, request_url: target.request_url ?? requestUrl }));
  if (!targets.length) return null;
  const cursorFields = extractCursorFields22C12BR2(payload);
  return {
    urlPath: sanitizeUrlPath22C12A(input.urlPath),
    requestUrl,
    method: (input.method ?? "GET").toUpperCase(),
    status: typeof input.status === "number" ? input.status : null,
    detectedShape: detectPassiveShape22C12A(payload),
    hasMore: cursorFields.has_more ?? cursorFields.hasMore,
    cursor: cursorFields.cursor ?? cursorFields.max_cursor ?? cursorFields.next_cursor,
    cursorFields,
    awemeCount: targets.length,
    targets
  };
}

export function classifyPassiveNetworkEndpointKind22C12A(urlPath: string): PassiveNetworkProbeEndpointKind22C12A {
  const normalizedPath = sanitizeUrlPath22C12A(urlPath).toLowerCase();
  if (normalizedPath.includes("/aweme/v1/web/aweme/post/")) return "profile_post";
  if (normalizedPath.includes("/aweme/v1/web/aweme/favorite/")) return "favorite";
  return "other_aweme_list";
}

export function buildPassiveNetworkStoredTarget22C12A(input: {
  target: PassiveNetworkProbeTarget22C12A;
  profileUrl: string;
  urlPath: string;
  capturedAt: string;
}): PassiveNetworkProbeStoredTarget22C12A {
  return {
    ...input.target,
    profile_url: input.profileUrl,
    endpoint_path: sanitizeUrlPath22C12A(input.urlPath),
    endpoint_kind: classifyPassiveNetworkEndpointKind22C12A(input.urlPath),
    captured_at: input.capturedAt,
    trace_version: "22C-12A-R3"
  };
}

function sanitizeUrlPath22C12A(value: string): string {
  const source = typeof value === "string" ? value.trim() : "";
  if (!source) return "/";
  try {
    if (/^https?:\/\//i.test(source)) {
      const parsed = new URL(source);
      return parsed.pathname || "/";
    }
    const parsed = new URL(source, "https://www.douyin.com");
    return parsed.pathname || "/";
  } catch {
    const [pathOnly] = source.split("?");
    return pathOnly || "/";
  }
}

function collectPassiveTargets22C12A(payload: unknown): PassiveNetworkProbeTarget22C12A[] {
  const targets = new Map<string, PassiveNetworkProbeTarget22C12A>();
  const seen = new WeakSet<object>();
  visitPassive22C12A(payload, seen, (record) => {
    const target = normalizePassiveTarget22C12A(record);
    if (!target || targets.has(target.aweme_id)) return;
    targets.set(target.aweme_id, target);
  });
  return Array.from(targets.values());
}

function visitPassive22C12A(value: unknown, seen: WeakSet<object>, onRecord: (record: Record<string, unknown>) => void, depth = 0): void {
  if (!value || typeof value !== "object" || depth > 10) return;
  if (seen.has(value as object)) return;
  seen.add(value as object);
  if (Array.isArray(value)) {
    value.forEach((entry) => visitPassive22C12A(entry, seen, onRecord, depth + 1));
    return;
  }
  const record = value as Record<string, unknown>;
  onRecord(record);
  for (const child of Object.values(record)) visitPassive22C12A(child, seen, onRecord, depth + 1);
}

function normalizePassiveTarget22C12A(record: Record<string, unknown>): PassiveNetworkProbeTarget22C12A | null {
  const awemeId = firstString22C12A(record.aweme_id, record.awemeId, record.aweme_id_str, record.awemeIdStr);
  if (!awemeId || !/^\d{6,22}$/.test(awemeId)) return null;
  const video = objectValue22C12A(record.video) ?? objectValue22C12A(record.video_info) ?? objectValue22C12A(record.videoInfo);
  const statistics = objectValue22C12A(record.statistics) ?? objectValue22C12A(record.stats);
  const author = objectValue22C12A(record.author) ?? objectValue22C12A(record.author_user) ?? objectValue22C12A(record.user);
  return {
    aweme_id: awemeId,
    source_url: `https://www.douyin.com/video/${awemeId}`,
    desc: truncate22C12A(firstString22C12A(record.desc, record.caption, record.title)),
    cover_url: firstCover22C12A(record, video),
    duration: resolvePassiveDuration22C12A(record, video),
    create_time: numberValue22C12A(record.create_time) ?? numberValue22C12A(record.createTime),
    like_count: metricCount22C12A(statistics, record, ["digg_count", "like_count", "diggCount", "likeCount"]),
    comment_count: metricCount22C12A(statistics, record, ["comment_count", "commentCount"]),
    // Hybrid requires favorite_count; Douyin exposes it as statistics.collect_count.
    // Without this, passive-only targets always stay skipped_pending forever.
    favorite_count: metricCount22C12A(statistics, record, ["collect_count", "favorite_count", "collectCount", "favoriteCount"]),
    share_count: metricCount22C12A(statistics, record, ["share_count", "shareCount"]),
    author_uid: firstString22C12A(author?.uid, author?.id, author?.user_id, author?.userId, record.author_uid, record.author_id, record.uid, record.user_id),
    author_sec_uid: firstString22C12A(author?.sec_uid, author?.secUid, author?.secUserId, record.author_sec_uid, record.authorSecUid, record.sec_uid, record.secUid),
    author_unique_id: firstString22C12A(author?.unique_id, author?.uniqueId, author?.short_id, author?.shortId, record.author_unique_id, record.authorUniqueId)
  };
}

function metricCount22C12A(statistics: Record<string, unknown> | null, fallback: Record<string, unknown>, keys: string[]): number | null {
  for (const key of keys) {
    const value = numberValue22C12A(statistics?.[key]);
    if (value != null) return value;
    const fallbackValue = numberValue22C12A(fallback[key]);
    if (fallbackValue != null) return fallbackValue;
  }
  return null;
}

function detectPassiveShape22C12A(payload: unknown): string {
  const shapes: Array<{ path: string[]; label: string }> = [
    { path: ["aweme_list"], label: "aweme_list" },
    { path: ["awemeList"], label: "awemeList" },
    { path: ["item_list"], label: "item_list" },
    { path: ["items"], label: "items" },
    { path: ["data", "list"], label: "data.list" },
    { path: ["data", "aweme_list"], label: "data.aweme_list" }
  ];
  for (const shape of shapes) {
    const value = readPath22C12A(payload, shape.path);
    if (Array.isArray(value) && value.length > 0) return shape.label;
  }
  return "recursive_aweme_record";
}

function readPath22C12A(value: unknown, ...paths: string[][]): unknown {
  for (const path of paths) {
    let current = value;
    let matched = true;
    for (const key of path) {
      if (!current || typeof current !== "object" || !(key in (current as Record<string, unknown>))) {
        matched = false;
        break;
      }
      current = (current as Record<string, unknown>)[key];
    }
    if (matched) return current;
  }
  return undefined;
}

function extractCursorFields22C12BR2(payload: unknown): PassiveNetworkProbeCursorFields22C12BR2 {
  return {
    cursor: scalarCursor22C12A(readPath22C12A(payload, ["cursor"], ["data", "cursor"])),
    max_cursor: scalarCursor22C12A(readPath22C12A(payload, ["max_cursor"], ["data", "max_cursor"])),
    min_cursor: scalarCursor22C12A(readPath22C12A(payload, ["min_cursor"], ["data", "min_cursor"])),
    next_cursor: scalarCursor22C12A(readPath22C12A(payload, ["next_cursor"], ["data", "next_cursor"])),
    has_more: booleanOrNull22C12A(readPath22C12A(payload, ["has_more"], ["data", "has_more"])),
    hasMore: booleanOrNull22C12A(readPath22C12A(payload, ["hasMore"], ["data", "hasMore"])),
    offset: scalarCursor22C12A(readPath22C12A(payload, ["offset"], ["data", "offset"])),
    page: scalarCursor22C12A(readPath22C12A(payload, ["page"], ["data", "page"])),
    next: scalarCursor22C12A(readPath22C12A(payload, ["next"], ["data", "next"]))
  };
}

function scalarCursor22C12A(value: unknown): string | number | null {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string" && value.trim()) return value.trim();
  return null;
}

function booleanOrNull22C12A(value: unknown): boolean | null {
  if (typeof value === "boolean") return value;
  if (value === 1 || value === "1" || value === "true" || value === "yes") return true;
  if (value === 0 || value === "0" || value === "false" || value === "no") return false;
  return null;
}

function firstCover22C12A(record: Record<string, unknown>, video: Record<string, unknown> | null): string | null {
  return firstString22C12A(
    ...coverList22C12A(video?.cover),
    ...coverList22C12A(video?.origin_cover),
    ...coverList22C12A(record.cover),
    ...coverList22C12A(record.origin_cover)
  );
}

function coverList22C12A(value: unknown): Array<string | null> {
  if (!value) return [];
  if (typeof value === "string") return [value];
  if (Array.isArray(value)) return value.map((entry) => typeof entry === "string" ? entry : null);
  if (typeof value !== "object") return [];
  const record = value as Record<string, unknown>;
  return [
    firstString22C12A(record.url),
    firstString22C12A(record.src),
    ...coverList22C12A(record.url_list),
    ...coverList22C12A(record.urlList)
  ];
}

function normalizeDuration22C12A(value: number | null): number | null {
  if (value == null || !Number.isFinite(value) || value <= 0) return null;
  return value > 1000 ? Math.round(value / 1000) : Math.round(value);
}

/**
 * Image/slide posts and partial list payloads often omit video.duration.
 * Without a positive duration, Hybrid stays skipped_pending forever
 * (production: missing_required_fields:duration_seconds on the last queue items).
 */
function resolvePassiveDuration22C12A(record: Record<string, unknown>, video: Record<string, unknown> | null): number | null {
  const numeric = normalizeDuration22C12A(
    numberValue22C12A(video?.duration)
      ?? numberValue22C12A(video?.duration_ms)
      ?? numberValue22C12A(video?.durationMs)
      ?? numberValue22C12A(record.duration)
      ?? numberValue22C12A(record.duration_ms)
      ?? numberValue22C12A(objectValue22C12A(record.music)?.duration)
  );
  if (numeric != null) return numeric;

  const images = Array.isArray(record.images)
    ? record.images
    : Array.isArray(objectValue22C12A(record.image_post_info)?.images)
      ? (objectValue22C12A(record.image_post_info)?.images as unknown[])
      : Array.isArray(objectValue22C12A(record.imagePostInfo)?.images)
        ? (objectValue22C12A(record.imagePostInfo)?.images as unknown[])
        : null;
  if (images && images.length > 0) {
    let total = 0;
    for (const image of images) {
      const imageRecord = objectValue22C12A(image) ?? {};
      const perImage = normalizeDuration22C12A(
        numberValue22C12A(imageRecord.duration) ?? numberValue22C12A(imageRecord.duration_ms)
      );
      total += perImage ?? 3;
    }
    return total > 0 ? total : null;
  }

  const awemeType = numberValue22C12A(record.aweme_type) ?? numberValue22C12A(record.awemeType);
  if (awemeType === 2 || awemeType === 68 || awemeType === 150 || awemeType === 51) return 1;
  if (record.image_post_info || record.imagePostInfo || record.note_id || record.notes) return 1;
  return null;
}

function numberValue22C12A(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string" && value.trim()) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}

function objectValue22C12A(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : null;
}

function firstString22C12A(...values: unknown[]): string | null {
  for (const value of values) {
    if (typeof value === "string" && value.trim()) return value.trim();
    if (typeof value === "number" && Number.isFinite(value)) return String(value).trim();
  }
  return null;
}

function truncate22C12A(value: string | null): string | null {
  if (!value) return null;
  return value.length > MAX_DESC_LENGTH_22C12A ? `${value.slice(0, MAX_DESC_LENGTH_22C12A)}...` : value;
}

function uniqueStrings22C12A(values: string[]): string[] {
  const seen = new Set<string>();
  const result: string[] = [];
  for (const value of values) {
    const normalized = value.trim();
    if (!normalized || seen.has(normalized)) continue;
    seen.add(normalized);
    result.push(normalized);
  }
  return result;
}
