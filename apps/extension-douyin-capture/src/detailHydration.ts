import { mergeNetworkItems, normalizeDouyinNetworkPayload } from "./networkCache.js";
import type { NetworkVideoMetadata } from "./types.js";

const DEFAULT_TIMEOUT_MS = 8_000;
const DEFAULT_CONCURRENCY = 3;

export type DetailHydrationDiscovery = {
  aweme_id: string;
  source_url: string | null;
  share_url?: string | null;
};

export type DetailHydrationStats = {
  detail_hydrate_attempted_count: number;
  detail_hydrate_success_count: number;
  detail_hydrate_failed_count: number;
  detail_hydrate_timeout_count: number;
  raw_detail_aweme_attached_count: number;
};

export type DetailHydrationResult = {
  items: NetworkVideoMetadata[];
  stats: DetailHydrationStats;
};

export type DetailHydrationOptions = {
  fetchImpl?: typeof fetch;
  timeoutMs?: number;
  concurrency?: number;
};

export async function hydrateDetailEvidenceForDiscoveries(
  discoveries: DetailHydrationDiscovery[],
  options: DetailHydrationOptions = {}
): Promise<DetailHydrationResult> {
  const fetchImpl = options.fetchImpl ?? fetch;
  const timeoutMs = options.timeoutMs ?? DEFAULT_TIMEOUT_MS;
  const concurrency = Math.max(1, options.concurrency ?? DEFAULT_CONCURRENCY);
  const stats: DetailHydrationStats = {
    detail_hydrate_attempted_count: 0,
    detail_hydrate_success_count: 0,
    detail_hydrate_failed_count: 0,
    detail_hydrate_timeout_count: 0,
    raw_detail_aweme_attached_count: 0
  };

  const tasks = discoveries
    .filter((item) => typeof item.aweme_id === "string" && item.aweme_id.trim() && Boolean(item.source_url || item.share_url))
    .map((item) => async () => {
      stats.detail_hydrate_attempted_count += 1;
      try {
        const hydrated = await hydrateOneDetailEvidence(item, { fetchImpl, timeoutMs });
        if (!hydrated) {
          stats.detail_hydrate_failed_count += 1;
          return null;
        }
        stats.detail_hydrate_success_count += 1;
        if (hydrated.raw_detail_aweme) stats.raw_detail_aweme_attached_count += 1;
        return hydrated;
      } catch (error) {
        if (error instanceof DetailHydrationTimeoutError) {
          stats.detail_hydrate_timeout_count += 1;
        } else {
          stats.detail_hydrate_failed_count += 1;
        }
        return null;
      }
    });

  const results = await runWithConcurrencyLimit(tasks, concurrency);
  return {
    items: mergeNetworkItems(results.filter((item): item is NetworkVideoMetadata => Boolean(item))),
    stats
  };
}

export async function hydrateOneDetailEvidence(
  discovery: DetailHydrationDiscovery,
  options: { fetchImpl?: typeof fetch; timeoutMs?: number } = {}
): Promise<NetworkVideoMetadata | null> {
  const fetchImpl = options.fetchImpl ?? fetch;
  const timeoutMs = options.timeoutMs ?? DEFAULT_TIMEOUT_MS;
  const targetAwemeId = normalizeAwemeId(discovery.aweme_id);
  const sourceUrl = discovery.source_url ?? discovery.share_url ?? null;
  if (!targetAwemeId || !sourceUrl) return null;

  for (const url of buildHybridDetailFetchUrls(targetAwemeId, sourceUrl)) {
    const response = await fetchWithTimeout(fetchImpl, url, timeoutMs);
    if (!response.ok) continue;
    const contentType = response.headers.get("content-type") || "";
    const body = await response.text();
    const selected = selectBestDetailCandidate(
      extractExactDetailCandidates(body, contentType, targetAwemeId),
      targetAwemeId
    );
    if (selected) return selected;
  }
  return null;
}

export function buildHybridDetailFetchUrls(awemeId: string, sourceUrl?: string | null): string[] {
  const normalizedId = normalizeAwemeId(awemeId);
  if (!normalizedId) return [];
  const urls: string[] = [];
  const videoUrl = typeof sourceUrl === "string" && sourceUrl.trim()
    ? sourceUrl.trim()
    : `https://www.douyin.com/video/${normalizedId}`;
  urls.push(videoUrl);
  const apiUrl = `https://www.douyin.com/aweme/v1/web/aweme/detail/?device_platform=webapp&aid=6383&channel=channel_pc_web&aweme_id=${encodeURIComponent(normalizedId)}`;
  if (!urls.includes(apiUrl)) urls.push(apiUrl);
  return urls;
}

export function networkMetadataHasHybridRequiredMetrics(item: NetworkVideoMetadata): boolean {
  const duration = item.duration_seconds;
  const like = item.like_count;
  const comment = item.comment_count;
  const favorite = item.favorite_count;
  const share = item.share_count;
  return duration != null && duration > 0
    && like != null && like >= 0
    && comment != null && comment >= 0
    && favorite != null && favorite >= 0
    && share != null && share >= 0;
}

export function selectBestDetailCandidate(
  candidates: NetworkVideoMetadata[],
  targetAwemeId: string
): NetworkVideoMetadata | null {
  const normalizedTargetId = normalizeAwemeId(targetAwemeId);
  if (!normalizedTargetId) return null;
  const exactMatches = candidates.filter((item) => normalizeAwemeId(item.aweme_id) === normalizedTargetId);
  if (!exactMatches.length) return null;
  const withRaw = exactMatches.find((item) => item.raw_detail_aweme);
  const withMetrics = exactMatches.find((item) => networkMetadataHasHybridRequiredMetrics(item));
  return withRaw ?? withMetrics ?? exactMatches[0] ?? null;
}

export function extractExactDetailCandidates(body: string, contentType: string, targetAwemeId: string): NetworkVideoMetadata[] {
  const normalizedTargetId = normalizeAwemeId(targetAwemeId);
  if (!body || !normalizedTargetId) return [];
  const roots: unknown[] = [];
  const direct = safeParseJson(body);
  if (direct) roots.push(direct);
  if (contentType.includes("html") || !direct) {
    roots.push(...extractJsonRootsFromHtml(body));
  }
  const exact: NetworkVideoMetadata[] = [];
  for (const root of roots) {
    for (const item of normalizeDouyinNetworkPayload(root, "detail_hydrate")) {
      if (normalizeAwemeId(item.aweme_id) === normalizedTargetId) {
        exact.push(item);
      }
    }
  }
  return mergeNetworkItems(exact);
}

export async function runWithConcurrencyLimit<T>(tasks: Array<() => Promise<T>>, limit: number): Promise<T[]> {
  const normalizedLimit = Math.max(1, Math.floor(limit));
  const results: T[] = new Array(tasks.length);
  let index = 0;

  async function worker(): Promise<void> {
    while (true) {
      const currentIndex = index;
      index += 1;
      if (currentIndex >= tasks.length) return;
      const task = tasks[currentIndex];
      if (!task) return;
      results[currentIndex] = await task();
    }
  }

  await Promise.all(Array.from({ length: Math.min(normalizedLimit, tasks.length || 1) }, () => worker()));
  return results;
}

function extractJsonRootsFromHtml(html: string): unknown[] {
  const roots: unknown[] = [];
  const scriptMatches = html.matchAll(/<script\b([^>]*)>([\s\S]*?)<\/script>/gi);
  for (const match of scriptMatches) {
    const attrs = match[1] ?? "";
    const scriptBody = match[2]?.trim();
    if (!scriptBody) continue;
    const direct = safeParseJson(scriptBody);
    if (direct) {
      roots.push(direct);
      continue;
    }
    if (/\bid\s*=\s*["']RENDER_DATA["']/i.test(attrs) || scriptBody.includes("%7B") || scriptBody.startsWith("%22")) {
      try {
        const decoded = decodeURIComponent(scriptBody);
        const decodedJson = safeParseJson(decoded);
        if (decodedJson) {
          roots.push(decodedJson);
          continue;
        }
      } catch {
        // ignore malformed percent-encoding
      }
    }
    for (const literal of extractBalancedJsonLiterals(scriptBody)) {
      const parsed = safeParseJson(literal);
      if (parsed) roots.push(parsed);
    }
  }
  return roots;
}

function extractBalancedJsonLiterals(source: string): string[] {
  const literals: string[] = [];
  for (let index = 0; index < source.length; index += 1) {
    const current = source[index];
    if (current !== "{" && current !== "[") continue;
    const extracted = readBalancedLiteral(source, index);
    if (!extracted) continue;
    if (extracted.value.includes("\"aweme_id\"")) literals.push(extracted.value);
    index = extracted.endIndex;
  }
  return literals;
}

function readBalancedLiteral(source: string, startIndex: number): { value: string; endIndex: number } | null {
  const opening = source[startIndex];
  const closing = opening === "{" ? "}" : "]";
  let depth = 0;
  let inString = false;
  let escaped = false;
  for (let index = startIndex; index < source.length; index += 1) {
    const current = source[index];
    if (inString) {
      if (escaped) {
        escaped = false;
        continue;
      }
      if (current === "\\") {
        escaped = true;
        continue;
      }
      if (current === "\"") inString = false;
      continue;
    }
    if (current === "\"") {
      inString = true;
      continue;
    }
    if (current === opening) depth += 1;
    if (current === closing) {
      depth -= 1;
      if (depth === 0) {
        return { value: source.slice(startIndex, index + 1), endIndex: index };
      }
    }
  }
  return null;
}

function safeParseJson(value: string): unknown | null {
  const trimmed = value.trim();
  if (!trimmed || (trimmed[0] !== "{" && trimmed[0] !== "[")) return null;
  try {
    return JSON.parse(trimmed);
  } catch {
    return null;
  }
}

function normalizeAwemeId(value: string | number | null | undefined): string | null {
  if (typeof value === "string" && value.trim()) return value.trim();
  if (typeof value === "number" && Number.isFinite(value)) return String(value).trim();
  return null;
}

async function fetchWithTimeout(fetchImpl: typeof fetch, url: string, timeoutMs: number): Promise<Response> {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetchImpl(url, {
      credentials: "include",
      redirect: "follow",
      signal: controller.signal
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new DetailHydrationTimeoutError();
    }
    throw error;
  } finally {
    clearTimeout(timeoutId);
  }
}

class DetailHydrationTimeoutError extends Error {
  constructor() {
    super("detail_hydration_timeout");
    this.name = "DetailHydrationTimeoutError";
  }
}
