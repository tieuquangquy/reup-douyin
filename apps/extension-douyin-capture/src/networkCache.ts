import type { CaptureContext, NetworkVideoMetadata, RawAwemeEvidence, RawEvidenceValue } from "./types.js";

const MAX_CACHE_ITEMS = 240;
const CACHE_ELEMENT_ID = "reup-douyin-network-cache";
const CACHE_EVENT_TYPE = "REUP_DOUYIN_NETWORK_CACHE_UPDATE";

declare global {
  interface Window {
    __REUP_DOUYIN_NETWORK_CACHE__?: NetworkVideoMetadata[];
    __REUP_DOUYIN_NETWORK_HOOK_INSTALLED__?: boolean;
  }
}

export function installDouyinNetworkHook(): void {
  if (typeof window === "undefined" || window.__REUP_DOUYIN_NETWORK_HOOK_INSTALLED__) return;
  window.__REUP_DOUYIN_NETWORK_HOOK_INSTALLED__ = true;
  window.__REUP_DOUYIN_NETWORK_CACHE__ = window.__REUP_DOUYIN_NETWORK_CACHE__ ?? [];

  const originalFetch = window.fetch.bind(window);
  window.fetch = async (...args) => {
    const response = await originalFetch(...args);
    observeResponse(response.url, response.clone());
    return response;
  };

  const OriginalXHR = window.XMLHttpRequest;
  const originalOpen = OriginalXHR.prototype.open as unknown as (this: XMLHttpRequest, method: string, url: string | URL, async?: boolean, username?: string | null, password?: string | null) => void;
  const originalSend = OriginalXHR.prototype.send;
  OriginalXHR.prototype.open = function open(this: XMLHttpRequest, method: string, url: string | URL, async?: boolean, username?: string | null, password?: string | null) {
    this.__reupDouyinUrl = String(url);
    return originalOpen.call(this, method, url, async ?? true, username ?? null, password ?? null);
  } as typeof OriginalXHR.prototype.open;
  OriginalXHR.prototype.send = function send(this: XMLHttpRequest, body?: Document | XMLHttpRequestBodyInit | null) {
    this.addEventListener("load", () => {
      const contentType = this.getResponseHeader("content-type") || "";
      const text = safeXhrResponseText(this);
      if (!contentType.includes("json") && typeof text !== "string") return;
      if (typeof text !== "string") return;
      observeJson(this.__reupDouyinUrl || "xhr", safeParseJson(text));
    });
    return originalSend.call(this, body);
  } as typeof OriginalXHR.prototype.send;
}

function safeXhrResponseText(xhr: XMLHttpRequest): string | null {
  const responseType = xhr.responseType || "";
  if (responseType !== "" && responseType !== "text") return null;
  try {
    return typeof xhr.responseText === "string" ? xhr.responseText : null;
  } catch {
    return null;
  }
}

export function readDouyinNetworkCache(document: Document, source = "dom_cache"): NetworkVideoMetadata[] {
  const fromElement = document.getElementById(CACHE_ELEMENT_ID)?.textContent;
  const normalizedFromElement = fromElement ? normalizeDouyinNetworkPayload(safeParseJson(fromElement), source) : [];
  if (normalizedFromElement.length) return normalizedFromElement;
  if (typeof window === "undefined") return [];
  return mergeItems(window.__REUP_DOUYIN_NETWORK_CACHE__ ?? []).slice(0, MAX_CACHE_ITEMS);
}

export function normalizeDouyinNetworkPayload(payload: unknown, source = "network_json"): NetworkVideoMetadata[] {
  const items: NetworkVideoMetadata[] = [];
  const seenObjects = new WeakSet<object>();
  visit(payload, source, items, seenObjects, 0);
  return mergeItems(items).slice(0, MAX_CACHE_ITEMS);
}

function observeResponse(url: string, response: Response): void {
  const contentType = response.headers.get("content-type") || "";
  if (!isDouyinUrl(url) || !contentType.includes("json")) return;
  response.json().then((json) => observeJson(url, json)).catch(() => undefined);
}

function observeJson(source: string, json: unknown): void {
  const observedAt = new Date().toISOString();
  const context = currentCaptureContext(observedAt);
  const normalized = normalizeDouyinNetworkPayload(json, safeSource(source)).map((item) => ({
    ...item,
    observed_at: observedAt,
    context
  }));
  if (!normalized.length) return;
  const current = window.__REUP_DOUYIN_NETWORK_CACHE__ ?? [];
  window.__REUP_DOUYIN_NETWORK_CACHE__ = mergeItems([...normalized, ...current]).slice(0, MAX_CACHE_ITEMS);
  publishCache(window.__REUP_DOUYIN_NETWORK_CACHE__);
}

function publishCache(items: NetworkVideoMetadata[]): void {
  const safeItems = items.slice(0, MAX_CACHE_ITEMS);
  let element = document.getElementById(CACHE_ELEMENT_ID) as HTMLScriptElement | null;
  if (!element) {
    element = document.createElement("script");
    element.id = CACHE_ELEMENT_ID;
    element.type = "application/json";
    document.documentElement.appendChild(element);
  }
  element.textContent = JSON.stringify(safeItems);
  window.postMessage({ type: CACHE_EVENT_TYPE, items: safeItems }, window.location.origin);
}

function visit(value: unknown, source: string, items: NetworkVideoMetadata[], seenObjects: WeakSet<object>, depth: number): void {
  if (!value || typeof value !== "object" || depth > 9) return;
  if (seenObjects.has(value)) return;
  seenObjects.add(value);
  const record = value as Record<string, unknown>;
  const item = normalizeAwemeRecord(record, source);
  if (item) items.push(item);
  for (const child of Object.values(record)) {
    if (Array.isArray(child)) {
      for (const entry of child) visit(entry, source, items, seenObjects, depth + 1);
    } else if (child && typeof child === "object") {
      visit(child, source, items, seenObjects, depth + 1);
    }
  }
}

function normalizeAwemeRecord(record: Record<string, unknown>, source: string): NetworkVideoMetadata | null {
  const awemeId = stringValue(record.aweme_id);
  if (!awemeId || !looksLikeAwemeRecord(record)) return null;
  const video = objectValue(record.video) ?? objectValue(record.video_info) ?? objectValue(record.videoInfo);
  const statistics = objectValue(record.statistics) ?? objectValue(record.stats) ?? objectValue(record.statistics_info) ?? objectValue(record.statisticsInfo);
  const shareInfo = objectValue(record.share_info) ?? objectValue(record.shareInfo);
  const covers = collectCoverCandidates(record, video);
  const createTime = numberValue(record.create_time) ?? numberValue(record.createTime) ?? numberValue(record.create_time_ms);
  const durationRaw = numberValue(video?.duration)
    ?? numberValue(video?.duration_ms)
    ?? numberValue(video?.durationMs)
    ?? numberValue(record.duration)
    ?? numberValue(record.duration_ms);
  const durationText = validDurationText(stringValue(record.duration_text) ?? stringValue(record.durationText));
  const durationSeconds = normalizeDurationSeconds(durationRaw)
    ?? parseDurationTextToSeconds(durationText)
    ?? durationSecondsFromImagePost(record);
  const postedAt = validPostedAtFromEpochSeconds(createTime);
  const viewMetric = metricValue(statistics, ["play_count", "view_count", "playCount"]);
  const likeMetric = metricValue(statistics, ["digg_count", "like_count", "diggCount"]);
  const commentMetric = metricValue(statistics, ["comment_count", "commentCount"]);
  const favoriteMetric = metricValue(statistics, ["collect_count", "favorite_count", "collectCount", "favoriteCount"]);
  const shareMetric = metricValue(statistics, ["share_count", "shareCount"]);
  const engagementRate = deriveEngagementRate({
    view_count: viewMetric.value,
    like_count: likeMetric.value,
    comment_count: commentMetric.value,
    share_count: shareMetric.value
  });
  const rawAweme = boundedRawEvidence(record);
  const rawEvidenceField: Pick<NetworkVideoMetadata, "raw_network_aweme" | "raw_detail_aweme"> = isDetailEvidenceSource(source)
    ? { raw_detail_aweme: rawAweme }
    : { raw_network_aweme: rawAweme };
  return {
    aweme_id: awemeId,
    title: stringValue(record.title) ?? stringValue(record.desc),
    desc: stringValue(record.desc) ?? stringValue(record.title),
    share_url: stringValue(record.share_url) ?? stringValue(shareInfo?.share_url) ?? stringValue(record.url),
    thumbnail_url: covers[0] ?? null,
    cover_url: firstCover(video?.cover) ?? covers[0] ?? null,
    origin_cover: firstCover(video?.origin_cover),
    dynamic_cover: firstCover(video?.dynamic_cover),
    url_list: covers,
    poster_aspect_ratio: 9 / 16,
    duration_text: durationText,
    duration_seconds: durationSeconds,
    posted_at: postedAt,
    view_count: viewMetric.value,
    view_count_text: viewMetric.raw,
    like_count: likeMetric.value,
    like_count_text: likeMetric.raw,
    comment_count: commentMetric.value,
    comment_count_text: commentMetric.raw,
    favorite_count: favoriteMetric.value,
    share_count: shareMetric.value,
    engagement_rate: engagementRate,
    raw_source: source,
    ...rawEvidenceField
  };
}

function isDetailEvidenceSource(source: string): boolean {
  return /detail|hydrate|share/i.test(source);
}

function boundedRawEvidence(value: unknown, depth = 0): RawAwemeEvidence {
  if (!value || typeof value !== "object" || Array.isArray(value)) return {};
  const output: RawAwemeEvidence = {};
  for (const [key, child] of Object.entries(value as Record<string, unknown>).slice(0, 80)) {
    if (isSecretLikeKey(key)) continue;
    output[key] = boundedRawValue(child, depth + 1);
  }
  return output;
}

function boundedRawValue(value: unknown, depth: number): RawEvidenceValue {
  if (value === null || typeof value === "number" || typeof value === "boolean") return value;
  if (typeof value === "string") return value.length > 600 ? `${value.slice(0, 600)}…` : value;
  if (!value || typeof value !== "object") return null;
  if (depth >= 5) return "[Truncated]";
  if (Array.isArray(value)) return value.slice(0, 12).map((entry) => boundedRawValue(entry, depth + 1));
  const output: RawAwemeEvidence = {};
  for (const [key, child] of Object.entries(value as Record<string, unknown>).slice(0, 80)) {
    if (isSecretLikeKey(key)) continue;
    output[key] = boundedRawValue(child, depth + 1);
  }
  return output;
}

function isSecretLikeKey(key: string): boolean {
  return /cookie|authorization|auth|token|secret|credential|password|passwd|session|header|csrf/i.test(key);
}

function looksLikeAwemeRecord(record: Record<string, unknown>): boolean {
  return Boolean(record.aweme_id && (record.video || record.video_info || record.videoInfo || record.statistics || record.stats || record.statistics_info || record.statisticsInfo || record.share_info || record.desc || record.create_time));
}

function collectCoverCandidates(record: Record<string, unknown>, video: Record<string, unknown> | null): string[] {
  const candidates = uniqueStrings([
    ...coverList(video?.origin_cover),
    ...coverList(video?.cover),
    ...coverList(video?.dynamic_cover),
    ...coverList(video?.poster),
    ...coverList(video?.poster_url),
    ...coverList(video?.thumbnail),
    ...coverList(video?.thumbnail_url),
    ...coverList(video?.thumb_url),
    ...coverList(video?.image),
    ...coverList(video?.image_url),
    ...coverList(video?.animated_cover),
    ...coverList(record.origin_cover),
    ...coverList(record.cover),
    ...coverList(record.dynamic_cover),
    ...coverList(record.poster),
    ...coverList(record.poster_url),
    ...coverList(record.thumbnail),
    ...coverList(record.thumbnail_url),
    ...coverList(record.thumb_url),
    ...coverList(record.image),
    ...coverList(record.image_url),
    ...coverList(record.animated_cover)
  ].map(normalizeUrl).filter((url): url is string => Boolean(url)));
  return sortCoverCandidatesBySignedCdn(candidates);
}

function hasSignedDouyinCdnUrl(value: string): boolean {
  return /[?&]x-signature=/i.test(value) || /[?&]x-expires=/i.test(value);
}

function sortCoverCandidatesBySignedCdn(candidates: string[]): string[] {
  const signed: string[] = [];
  const cdn: string[] = [];
  const rest: string[] = [];
  for (const url of candidates) {
    if (hasSignedDouyinCdnUrl(url)) signed.push(url);
    else if (/douyinpic\.com|byteimg\.com/i.test(url)) cdn.push(url);
    else rest.push(url);
  }
  return [...signed, ...cdn, ...rest];
}

function firstCover(value: unknown): string | null {
  return coverList(value).map(normalizeUrl).find(Boolean) ?? null;
}

function coverList(value: unknown): string[] {
  if (!value) return [];
  if (typeof value === "string") return [value];
  if (Array.isArray(value)) return value.filter((entry): entry is string => typeof entry === "string");
  if (typeof value !== "object") return [];
  const record = value as Record<string, unknown>;
  return [
    stringValue(record.url),
    stringValue(record.uri),
    stringValue(record.src),
    stringValue(record.href),
    stringValue(record.poster),
    stringValue(record.poster_url),
    stringValue(record.thumbnail_url),
    stringValue(record.thumb_url),
    stringValue(record.image_url),
    ...coverList(record.url_list),
    ...coverList(record.urlList),
    ...coverList(record.urls)
  ].filter((entry): entry is string => Boolean(entry));
}

export function mergeNetworkItems(items: NetworkVideoMetadata[]): NetworkVideoMetadata[] {
  return mergeItems(items).slice(0, MAX_CACHE_ITEMS);
}

function currentCaptureContext(observedAt: string): CaptureContext {
  const pageUrl = typeof window === "undefined" ? null : window.location.href;
  const profileUrl = profileUrlFromPage(pageUrl);
  const profileExternalId = profileExternalIdFromUrl(profileUrl);
  const pageUrlNormalized = normalizeContextUrl(pageUrl);
  return {
    page_url: pageUrl,
    page_url_normalized: pageUrlNormalized,
    profile_url: profileUrl,
    profile_external_id: profileExternalId,
    captured_at: observedAt,
    cache_scope_key: [pageUrlNormalized, profileUrl, profileExternalId].filter(Boolean).join("|") || null
  };
}

function normalizeContextUrl(value: string | null | undefined): string | null {
  if (!value) return null;
  try {
    const parsed = new URL(value, "https://www.douyin.com");
    return `${parsed.origin}${parsed.pathname.replace(/\/+$/, "")}`;
  } catch {
    return null;
  }
}

function profileUrlFromPage(url: string | null): string | null {
  if (!url) return null;
  try {
    const parsed = new URL(url);
    const userMatch = /\/user\/([^/?#]+)/.exec(parsed.pathname);
    if (userMatch?.[1]) return `https://www.douyin.com/user/${userMatch[1]}`;
    const path = parsed.pathname.replace(/^\//, "");
    if (path.startsWith("@")) return `https://www.douyin.com/${path.split("/")[0]}`;
  } catch {
    return null;
  }
  return null;
}

function profileExternalIdFromUrl(url: string | null): string | null {
  if (!url) return null;
  try {
    const parsed = new URL(url);
    const userMatch = /\/user\/([^/?#]+)/.exec(parsed.pathname);
    return userMatch?.[1] ?? null;
  } catch {
    return null;
  }
}

function mergeItems(items: NetworkVideoMetadata[]): NetworkVideoMetadata[] {
  const byId = new Map<string, NetworkVideoMetadata>();
  for (const item of items) {
    const awemeId = item.aweme_id?.trim();
    if (!awemeId) continue;
    const previous = byId.get(awemeId);
    const contextMismatchCodes = uniqueStrings([...(item.context_mismatch_codes ?? []), ...(previous?.context_mismatch_codes ?? [])]);
    byId.set(awemeId, {
      ...previous,
      ...item,
      aweme_id: awemeId,
      url_list: uniqueStrings([...(item.url_list ?? []), ...(previous?.url_list ?? [])]),
      raw_network_aweme: item.raw_network_aweme ?? previous?.raw_network_aweme ?? null,
      raw_detail_aweme: item.raw_detail_aweme ?? previous?.raw_detail_aweme ?? null,
      context: item.context ?? previous?.context ?? null,
      ...(contextMismatchCodes.length ? { context_mismatch_codes: contextMismatchCodes as NonNullable<NetworkVideoMetadata["context_mismatch_codes"]> } : {})
    });
  }
  return Array.from(byId.values()).map((item) => ({ ...item, url_list: [...(item.url_list ?? [])] }));
}

function normalizeUrl(value: string | null | undefined): string | null {
  const trimmed = value?.trim();
  if (!trimmed) return null;
  try {
    return new URL(trimmed, "https://www.douyin.com").href;
  } catch {
    return null;
  }
}

function isDouyinUrl(value: string): boolean {
  try {
    const host = new URL(value, window.location.href).hostname.toLowerCase();
    return host.includes("douyin.com") || host.includes("iesdouyin.com") || host.includes("byteimg.com") || host.includes("douyinpic.com");
  } catch {
    return false;
  }
}

function safeSource(value: string): string {
  try {
    const url = new URL(value, window.location.href);
    return `${url.hostname}${url.pathname}`.slice(0, 180);
  } catch {
    return "network_json";
  }
}

function safeParseJson(value: string): unknown {
  try {
    return JSON.parse(value);
  } catch {
    return null;
  }
}

function objectValue(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : null;
}

function metricValue(record: Record<string, unknown> | null, keys: string[]): { value: number | null; raw: string | null } {
  for (const key of keys) {
    const rawValue = record?.[key];
    const value = countValue(rawValue);
    const raw = typeof rawValue === "string" && rawValue.trim() ? rawValue.trim() : null;
    if (typeof value === "number" || raw) return { value, raw };
  }
  return { value: null, raw: null };
}

function stringValue(value: unknown): string | null {
  if (typeof value === "string" && value.trim()) return value.trim();
  if (typeof value === "number" && Number.isFinite(value)) return String(value).trim();
  return null;
}

function numberValue(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string" && value.trim()) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}

function countValue(value: unknown): number | null {
  const numeric = numberValue(value);
  if (typeof numeric !== "number" || !Number.isFinite(numeric)) return null;
  if (numeric < 0) return null;
  return Math.round(numeric);
}

function deriveEngagementRate(values: {
  view_count: number | null;
  like_count: number | null;
  comment_count: number | null;
  share_count: number | null;
}): number | null {
  const views = values.view_count;
  if (typeof views !== "number" || !Number.isFinite(views) || views <= 0) return null;
  const likes = typeof values.like_count === "number" ? values.like_count : 0;
  const comments = typeof values.comment_count === "number" ? values.comment_count : 0;
  const shares = typeof values.share_count === "number" ? values.share_count : 0;
  const numerator = likes + comments + shares;
  if (!Number.isFinite(numerator) || numerator < 0) return null;
  const rate = numerator / views;
  return Number.isFinite(rate) && rate >= 0 ? rate : null;
}

function uniqueStrings(values: string[]): string[] {
  const seen = new Set<string>();
  const unique: string[] = [];
  for (const value of values) {
    if (!value || seen.has(value)) continue;
    seen.add(value);
    unique.push(value);
  }
  return unique;
}

function normalizeDurationSeconds(value: number | null): number | null {
  if (typeof value !== "number" || !Number.isFinite(value) || value <= 0) return null;
  const seconds = value > 1000 ? value / 1000 : value;
  if (!Number.isFinite(seconds) || seconds <= 0 || seconds > 86_400) return null;
  return Math.round(seconds);
}

function parseDurationTextToSeconds(text: string | null): number | null {
  if (!text) return null;
  const match = /^(?:(\d{1,2}):)?(\d{1,2}):(\d{2})$/.exec(text.trim());
  if (!match) return null;
  const hours = match[1] ? Number(match[1]) : 0;
  const minutes = Number(match[2]);
  const seconds = Number(match[3]);
  if (![hours, minutes, seconds].every((value) => Number.isFinite(value))) return null;
  const total = hours * 3600 + minutes * 60 + seconds;
  return total > 0 ? total : null;
}

function durationSecondsFromImagePost(record: Record<string, unknown>): number | null {
  const imagePostInfo = objectValue(record.image_post_info) ?? objectValue(record.imagePostInfo);
  const images = Array.isArray(record.images)
    ? record.images
    : Array.isArray(imagePostInfo?.images)
      ? imagePostInfo.images as unknown[]
      : null;
  if (images && images.length > 0) {
    let total = 0;
    for (const image of images) {
      const imageRecord = objectValue(image) ?? {};
      const perImage = normalizeDurationSeconds(
        numberValue(imageRecord.duration) ?? numberValue(imageRecord.duration_ms)
      );
      total += perImage ?? 3;
    }
    return total > 0 ? total : null;
  }
  const awemeType = numberValue(record.aweme_type) ?? numberValue(record.awemeType);
  if (awemeType === 2 || awemeType === 68 || awemeType === 150 || awemeType === 51) return 1;
  if (record.image_post_info || record.imagePostInfo || record.note_id || record.notes) return 1;
  return null;
}

function validDurationText(value: string | null): string | null {
  if (!value) return null;
  const trimmed = value.trim();
  return /^(?:\d{1,2}:)?\d{1,2}:\d{2}$/.test(trimmed) ? trimmed : null;
}

function validPostedAtFromEpochSeconds(value: number | null): string | null {
  if (typeof value !== "number" || !Number.isFinite(value) || value <= 0) return null;
  const parsed = new Date(value * 1000);
  if (Number.isNaN(parsed.getTime())) return null;
  if (parsed.getUTCHours() === 0 && parsed.getUTCMinutes() === 0 && parsed.getUTCSeconds() === 0 && parsed.getUTCMilliseconds() === 0) return null;
  return parsed.toISOString();
}

declare global {
  interface XMLHttpRequest {
    __reupDouyinUrl?: string;
  }
}
