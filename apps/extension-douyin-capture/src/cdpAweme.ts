import type { RawAwemeEvidence } from "./types.js";

export type CdpAwemeSource = "cdp_network_aweme" | "cdp_runtime_aweme" | "page_network_cache_aweme" | "script_hydration_aweme";

export interface CdpMappedAwemeMetrics {
  duration_seconds: number | null;
  duration_text: string | null;
  duration_raw: number | null;
  duration_validation_result: "accepted_exact_aweme" | "rejected_missing" | "rejected_non_positive" | "rejected_too_large";
  duration_candidate_list: Array<{ source: string; raw_value: number | null; normalized_seconds: number | null; accepted: boolean; reason: string }>;
  view_count: number | null;
  like_count: number | null;
  comment_count: number | null;
  favorite_count: number | null;
  share_count: number | null;
  posted_text: string | null;
  posted_at: string | null;
}

export interface CdpAwemeCandidate {
  aweme_id: string;
  source_used: CdpAwemeSource;
  raw_aweme: RawAwemeEvidence;
  raw_aweme_keys: string[];
  mapped: CdpMappedAwemeMetrics;
  response_url?: string | null;
}

export interface CdpAwemeSearchStats {
  candidate_count: number;
  exact_match_count: number;
}

export interface CdpAwemeSearchResult {
  candidates: CdpAwemeCandidate[];
  stats: CdpAwemeSearchStats;
}

export interface BoundedAwemeSearchOptions {
  maxDepth: number;
  maxObjects: number;
  maxArrayLength: number;
  maxKeysPerObject: number;
  timeoutMs: number;
}

const DEFAULT_SEARCH_OPTIONS: BoundedAwemeSearchOptions = {
  maxDepth: 8,
  maxObjects: 30_000,
  maxArrayLength: 100,
  maxKeysPerObject: 80,
  timeoutMs: 650
};

const SECRET_LIKE_KEY_PATTERN = /cookie|authorization|auth_token|access_token|refresh_token|token|secret|credential|password|passwd|session|header|csrf/i;
const PRIORITY_KEYS = ["aweme_list", "aweme_detail", "aweme", "awemeInfo", "aweme_info", "data", "detail", "item", "items", "list", "video", "statistics", "stats", "props", "memoizedProps", "pendingProps", "memoizedState", "stateNode", "child", "sibling", "return"];

export function parseCdpResponseBodyJson(body: string, base64Encoded = false): unknown | null {
  const decoded = base64Encoded ? decodeBase64(body) : body;
  if (!decoded) return null;
  try {
    return JSON.parse(decoded);
  } catch {
    return null;
  }
}

export function findExactAwemeCandidates(root: unknown, targetAwemeId: string, source_used: CdpAwemeSource, response_url?: string | null, options: Partial<BoundedAwemeSearchOptions> = {}): CdpAwemeSearchResult {
  const targetId = normalizeAwemeId(targetAwemeId);
  const config = { ...DEFAULT_SEARCH_OPTIONS, ...options };
  const candidates: CdpAwemeCandidate[] = [];
  const visited = new WeakSet<object>();
  const startedAt = Date.now();
  let objectCount = 0;
  let candidate_count = 0;
  const stack: Array<{ value: unknown; depth: number }> = [{ value: root, depth: 0 }];
  while (stack.length) {
    if (Date.now() - startedAt > config.timeoutMs || objectCount >= config.maxObjects) break;
    const current = stack.pop();
    if (!current || current.depth > config.maxDepth) continue;
    const value = current.value;
    if (!value || typeof value !== "object" || visited.has(value)) continue;
    visited.add(value);
    objectCount += 1;
    const record = value as Record<string, unknown>;
    const candidateId = normalizeAwemeId(record.aweme_id);
    if (candidateId && looksLikeAweme(record)) {
      candidate_count += 1;
      if (candidateId === targetId) candidates.push(buildCandidate(record, candidateId, source_used, response_url));
    }
    for (const key of priorityKeys(record).slice(0, config.maxKeysPerObject)) {
      if (SECRET_LIKE_KEY_PATTERN.test(key)) continue;
      let child: unknown;
      try {
        child = record[key];
      } catch {
        continue;
      }
      if (!child || typeof child === "function") continue;
      if (Array.isArray(child)) {
        for (const entry of child.slice(0, config.maxArrayLength)) stack.push({ value: entry, depth: current.depth + 1 });
      } else if (typeof child === "object") {
        stack.push({ value: child, depth: current.depth + 1 });
      }
    }
  }
  return { candidates, stats: { candidate_count, exact_match_count: candidates.length } };
}

export function mapCdpAwemeMetrics(aweme: Record<string, unknown>): CdpMappedAwemeMetrics {
  const video = objectRecord(aweme.video) ?? objectRecord(aweme.video_info) ?? objectRecord(aweme.videoInfo);
  const statistics = objectRecord(aweme.statistics) ?? objectRecord(aweme.stats) ?? objectRecord(aweme.statistics_info) ?? objectRecord(aweme.statisticsInfo);
  const durationCandidates = [
    { source: "aweme.video.duration", raw_value: numberValue(video?.duration) },
    { source: "aweme.video.duration_millis", raw_value: numberValue(video?.duration_millis) },
    { source: "aweme.video.duration_ms", raw_value: numberValue(video?.duration_ms) },
    { source: "aweme.duration", raw_value: numberValue(aweme.duration) },
    { source: "aweme.duration_millis", raw_value: numberValue(aweme.duration_millis) }
  ];
  const selectedDurationCandidate = durationCandidates.find((candidate) => candidate.raw_value != null) ?? null;
  const durationRaw = selectedDurationCandidate?.raw_value ?? null;
  const duration_seconds = normalizeDurationSeconds(durationRaw);
  const duration_validation_result = durationRaw == null
    ? "rejected_missing"
    : durationRaw <= 0
      ? "rejected_non_positive"
      : duration_seconds == null
        ? "rejected_too_large"
        : "accepted_exact_aweme";
  const createTime = numberValue(aweme.create_time) ?? numberValue(aweme.createTime);
  return {
    duration_seconds,
    duration_text: duration_seconds != null ? formatDuration(duration_seconds) : null,
    duration_raw: durationRaw,
    duration_validation_result,
    duration_candidate_list: durationCandidates.map((candidate) => {
      const normalizedSeconds = normalizeDurationSeconds(candidate.raw_value);
      return {
        source: candidate.source,
        raw_value: candidate.raw_value,
        normalized_seconds: normalizedSeconds,
        accepted: candidate === selectedDurationCandidate && normalizedSeconds != null,
        reason: candidate.raw_value == null
          ? "missing"
          : normalizedSeconds == null
            ? "invalid"
            : candidate === selectedDurationCandidate
              ? "selected_exact_aweme"
              : "not_selected"
      };
    }),
    view_count: numberValue(statistics?.play_count) ?? null,
    like_count: numberValue(statistics?.digg_count) ?? null,
    comment_count: numberValue(statistics?.comment_count) ?? null,
    favorite_count: numberValue(statistics?.collect_count) ?? null,
    share_count: numberValue(statistics?.share_count) ?? numberValue(statistics?.forward_count),
    posted_text: null,
    posted_at: createTime ? new Date(createTime * 1000).toISOString() : null
  };
}

export function sanitizeAwemeEvidence(value: unknown, depth = 0): RawAwemeEvidence {
  if (!value || typeof value !== "object" || Array.isArray(value)) return {};
  const output: RawAwemeEvidence = {};
  for (const [key, child] of Object.entries(value as Record<string, unknown>).slice(0, 80)) {
    if (SECRET_LIKE_KEY_PATTERN.test(key)) continue;
    output[key] = sanitizeEvidenceValue(child, depth + 1);
  }
  return output;
}

function buildCandidate(aweme: Record<string, unknown>, aweme_id: string, source_used: CdpAwemeSource, response_url?: string | null): CdpAwemeCandidate {
  const raw_aweme = sanitizeAwemeEvidence(aweme);
  const candidate: CdpAwemeCandidate = { aweme_id, source_used, raw_aweme, raw_aweme_keys: Object.keys(raw_aweme), mapped: mapCdpAwemeMetrics(aweme) };
  if (typeof response_url !== "undefined") candidate.response_url = response_url;
  return candidate;
}

function looksLikeAweme(record: Record<string, unknown>): boolean {
  return Boolean(record.aweme_id && (record.statistics || record.stats || record.video || record.video_info || record.create_time || record.desc || record.author));
}

function priorityKeys(record: Record<string, unknown>): string[] {
  const keys = Object.keys(record);
  return [...PRIORITY_KEYS.filter((key) => key in record), ...keys.filter((key) => !PRIORITY_KEYS.includes(key))];
}

function sanitizeEvidenceValue(value: unknown, depth: number): RawAwemeEvidence[keyof RawAwemeEvidence] {
  if (value === null || typeof value === "number" || typeof value === "boolean") return value;
  if (typeof value === "string") return value.length > 600 ? `${value.slice(0, 600)}…` : value;
  if (!value || typeof value !== "object" || typeof value === "function") return null;
  if (depth >= 5) return "[Truncated]";
  if (Array.isArray(value)) return value.slice(0, 12).map((entry) => sanitizeEvidenceValue(entry, depth + 1));
  const output: RawAwemeEvidence = {};
  for (const [key, child] of Object.entries(value as Record<string, unknown>).slice(0, 80)) {
    if (SECRET_LIKE_KEY_PATTERN.test(key)) continue;
    output[key] = sanitizeEvidenceValue(child, depth + 1);
  }
  return output;
}

function decodeBase64(value: string): string | null {
  try {
    if (typeof atob === "function") return atob(value);
  } catch {
    return null;
  }
  try {
    return Buffer.from(value, "base64").toString("utf8");
  } catch {
    return null;
  }
}

function normalizeAwemeId(value: unknown): string | null {
  if (typeof value === "string" || typeof value === "number") {
    const normalized = String(value).trim();
    return normalized.length ? normalized : null;
  }
  return null;
}

function objectRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : null;
}

function numberValue(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string") {
    const normalized = value.replace(/,/g, "").trim();
    if (!normalized) return null;
    const parsed = Number(normalized);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}

function stringValue(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function normalizeDurationSeconds(value: number | null): number | null {
  if (value === null || !Number.isFinite(value) || value <= 0) return null;
  const seconds = value > 1000 ? value / 1000 : value;
  return Math.round(seconds * 1000) / 1000;
}

function formatDuration(value: number): string {
  const totalSeconds = Math.max(0, Math.round(value));
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${minutes}:${seconds.toString().padStart(2, "0")}`;
}
