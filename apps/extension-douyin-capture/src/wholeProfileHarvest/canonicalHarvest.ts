import type { FullModalHarvestRequestPayload, FullModalHarvestItemPayload } from "../types.js";
import type { WholeProfileHarvestState, WholeProfileHarvestQueueItem, WholeProfileHarvestMode, WholeProfileHarvestSpeed, WholeProfileHarvestResult, WholeProfileHarvestMetrics } from "./state.js";

export type CanonicalHarvestOptions = {
  mode?: WholeProfileHarvestMode;
  collect_mode?: "one_item_smoke_test" | "one_item_backend_proof";
  batch_limit?: number | "all";
  speed?: WholeProfileHarvestSpeed;
  diagnostics?: Record<string, unknown>;
};

export type CaptureInboxItemPayload = FullModalHarvestRequestPayload;

export type ThumbnailCandidate = {
  url: string | null | undefined;
  source: string;
  alt?: string | null;
  text?: string | null;
  title?: string | null;
  aria?: string | null;
  containerText?: string | null;
  width?: number | null;
  height?: number | null;
  nearAweme?: boolean | null;
};

export type CanonicalHarvestSessionRequest = {
  schema_version: "douyin_extension_capture_session.v1";
  source: "whole_profile_harvest";
  profile_url: string;
  normalized_profile_url: string;
  profile_sec_uid_or_path: string | null;
  profile_display_name: string | null;
  profile_avatar_url: string | null;
  display_title: string;
  source_modal_aweme_id: string | null;
  verified_target_count: number;
  queued_count: number;
  run_id: string;
  mode: "whole_profile_harvest";
};

export type CanonicalHarvestPayload = {
  capture_session_id: string;
  commit_policy: "finalized_only";
  aweme_id: string;
  target_aweme_id: string;
  source_video_external_id: string;
  profile_url: string;
  source_url: string | null;
  current_modal_id_before: string | null;
  current_modal_id_after: string | null;
  extracted_aweme_id: string | null;
  duration_seconds: number | null;
  duration_text: string | null;
  like_count: number | null;
  comment_count: number | null;
  favorite_count: number | null;
  share_count: number | null;
  title?: string | null;
  caption?: string | null;
  thumbnail_url?: string | null;
  posted_text?: string | null;
  view_count?: number | null;
  profile_card_evidence: Record<string, unknown>;
  raw_evidence_summary: {
    source: "whole_profile_harvest";
    extraction_stage: "phase11a_production_stabilized_calibrated_harvest";
    extractor_version: "whole_profile_modal_extract_only.v1";
    metrics: {
      current_modal_id_before: string | null;
      current_modal_id_after: string | null;
      extracted_aweme_id: string | null;
      duration_seconds: number | null;
      duration_text: string | null;
      duration_raw?: number | null;
      duration_validation_result?: string | null;
      duration_candidate_list?: Array<{ source: string; raw_value: number | null; normalized_seconds: number | null; accepted: boolean; reason: string }>;
      like_count: number | null;
      comment_count: number | null;
      favorite_count: number | null;
      share_count: number | null;
      source_used: string | null;
      posted_text_raw?: string | null;
      posted_at?: string | null;
      posted_display?: string | null;
      posted_source?: string | null;
      posted_parse_confidence?: string | null;
    };
    profile_card_snapshot: {
      source_url: string | null;
      title: string | null;
      caption: string | null;
      posted_text: string | null;
      posted_text_raw?: string | null;
      posted_display?: string | null;
      thumbnail_url: string | null;
      view_count: number | null;
      view_text: string | null;
    };
  };
};

export type CanonicalPayloadRemovedField = {
  path: string;
  reason: "not_allowlisted";
};

export type CanonicalPayloadGuardResult =
  | { ok: true; offending_paths: [] }
  | { ok: false; code: "payload_contains_disallowed_field_local" | "payload_invalid" | "capture_inbox_payload_missing_required_fields"; path: string; offending_paths: string[] };

export type CaptureInboxPayloadSanitizerDiagnostic = {
  path: string;
  reason: "forbidden_key" | "unsupported_value" | "non_finite_number" | "oversized_string" | "oversized_array";
};

export type CaptureInboxPayloadSanitizeResult = {
  value: unknown;
  diagnostics: CaptureInboxPayloadSanitizerDiagnostic[];
};

const DISALLOWED_KEYS = new Set(["diagnostics", "debug", "trace", "state", "runtime", "capture_session_source", "session_source", "token", "cookie", "authorization", "password", "api_key", "secret", "headers", "payload_guard_full", "last_request", "last_response", "last_flush_request", "last_flush_response", "raw_script", "raw_scripts", "raw_state", "raw_dom", "chrome_storage", "local_storage", "session_storage", "browser_profile_path", "credential", "auth_token", "csrf"]);
const BACKEND_SECRET_KEY_MARKERS = ["cookie", "authorization", "auth_token", "csrf", "password", "credential", "local_storage", "session_storage", "browser_profile_path", "token", "secret", "api_key"];
const BACKEND_SECRET_ALLOWED_KEYS = new Set(["capture_session_id"]);
const CAPTURE_INBOX_SANITIZER_MAX_STRING_LENGTH = 4096;
const CAPTURE_INBOX_SANITIZER_MAX_ARRAY_LENGTH = 50;
const PROFILE_CARD_ALLOWLIST = new Set(["title", "caption", "desc", "description", "thumbnail_url", "cover_url", "poster_url", "source_url", "posted_text", "posted_text_raw", "posted_at", "posted_display", "thumbnail_source", "posted_source", "posted_parse_confidence", "posted_parser_pattern_matched", "posted_reference_time", "posted_timezone", "view_count", "view_text"]);
const UI_CHROME_IMAGE_TEXT = /(get\s*app|下载|app|logo|avatar|头像|douyin|抖音)/i;
const UI_CHROME_IMAGE_URL = /(logo|avatar|app|download|icon|sprite|favicon|badge|qrcode|qr_code)/i;

export function isLikelyDouyinUiChromeImage(candidate: ThumbnailCandidate | string | null | undefined): boolean {
  const value = typeof candidate === "string" ? { url: candidate, source: "unknown" } : candidate;
  if (!value?.url) return true;
  const url = value.url.trim();
  if (!url) return true;
  const text = [value.alt, value.text, value.title, value.aria, value.containerText].filter(Boolean).join(" ");
  if (UI_CHROME_IMAGE_TEXT.test(text)) return true;
  const lowerUrl = url.toLowerCase();
  if (lowerUrl.startsWith("data:image/svg") || lowerUrl.endsWith(".svg") || UI_CHROME_IMAGE_URL.test(lowerUrl)) return true;
  const width = typeof value.width === "number" ? value.width : null;
  const height = typeof value.height === "number" ? value.height : null;
  if (width !== null && height !== null) {
    if (width <= 48 || height <= 48) return true;
    const ratio = width / Math.max(1, height);
    if (ratio > 4 || ratio < 0.25) return true;
  }
  if (value.nearAweme === false && value.source !== "profile_card") return true;
  return false;
}

export function resolveAwemeThumbnail(args: { awemeId: string; target?: { profile_card_evidence?: Record<string, unknown> | null } | null; extracted?: Record<string, unknown> | null; candidates?: ThumbnailCandidate[] }): { thumbnail_url: string | null; thumbnail_source: string; candidates_count: number; rejected_ui_chrome_count: number; rejection_reasons: string[] } {
  const candidates: ThumbnailCandidate[] = [];
  const evidence = args.target?.profile_card_evidence ?? {};
  for (const [source, value] of [["profile_card", evidence.thumbnail_url], ["profile_card_cover", evidence.cover_url], ["profile_card_poster", evidence.poster_url], ["modal_extractor", args.extracted?.thumbnail_url]] as const) {
    if (typeof value === "string" && value.trim()) candidates.push({ url: value, source, nearAweme: true });
  }
  candidates.push(...(args.candidates ?? []));
  const rejectionReasons: string[] = [];
  let rejected = 0;
  for (const candidate of candidates) {
    if (!candidate.url) continue;
    if (isLikelyDouyinUiChromeImage(candidate)) {
      rejected += 1;
      rejectionReasons.push(`${candidate.source}:ui_chrome_rejected`);
      continue;
    }
    return { thumbnail_url: candidate.url.trim(), thumbnail_source: candidate.source, candidates_count: candidates.length, rejected_ui_chrome_count: rejected, rejection_reasons: rejectionReasons };
  }
  return { thumbnail_url: null, thumbnail_source: "none", candidates_count: candidates.length, rejected_ui_chrome_count: rejected, rejection_reasons: rejectionReasons };
}

export function normalizeProfileUrlForSession(profileUrl: string | null | undefined): string {
  const value = (profileUrl ?? "").trim();
  if (!value) return "";
  try {
    const parsed = new URL(value);
    const userMatch = parsed.pathname.match(/\/user\/([^/?#]+)/i);
    if (userMatch?.[1]) return `${parsed.origin}/user/${userMatch[1]}`;
    return `${parsed.origin}${parsed.pathname.replace(/\/+$/, "")}`;
  } catch {
    return value.split(/[?#]/)[0]?.replace(/\/+$/, "") ?? value;
  }
}

export function secUidFromProfileUrl(profileUrl: string | null | undefined): string | null {
  const normalized = normalizeProfileUrlForSession(profileUrl);
  const match = normalized.match(/\/user\/([^/?#]+)/i);
  return match?.[1] ?? null;
}

export function buildSessionDisplayTitle(profileUrl: string | null | undefined): string {
  const secUid = secUidFromProfileUrl(profileUrl);
  if (secUid) return `Douyin profile ${secUid.slice(0, 8)}…${secUid.slice(-6)}`;
  const normalized = normalizeProfileUrlForSession(profileUrl);
  return normalized || "Douyin profile collection";
}

export type DouyinPostedRawNormalization = {
  raw_original: string | null;
  raw_normalized: string | null;
  removed_prefix: string | null;
  normalization_notes: string[];
};

export function normalizeDouyinPostedRawText(rawText: string | null | undefined): DouyinPostedRawNormalization {
  const rawOriginal = typeof rawText === "string" ? rawText : null;
  let value = (rawText ?? "").normalize("NFKC").replace(/\s+/g, " ").trim();
  const notes: string[] = [];
  const prefixes: string[] = [];
  if (!value) return { raw_original: rawOriginal, raw_normalized: null, removed_prefix: null, normalization_notes: [] };

  const beforeLeading = value;
  value = value.replace(/^[·•・。\s]+/, "").trim();
  if (value !== beforeLeading) notes.push("leading_separator_removed");

  const label = value.match(/^(?:发布时间|发布于|发布时间为)\s*[:：]?\s*(.+)$/i);
  if (label?.[1]) {
    prefixes.push(value.slice(0, value.length - label[1].length).trim());
    value = label[1].trim();
    notes.push("label_prefix_removed");
  }

  const author = value.match(/^@?[^·•・。\n]{1,80}\s*[·•・。]\s*(.+)$/);
  if (author?.[1] && looksLikePostedDateText(author[1])) {
    prefixes.push(value.slice(0, value.length - author[1].length).trim());
    value = author[1].trim();
    notes.push("author_prefix_removed");
  }

  value = value.replace(/^[·•・。\s]+/, "").trim();
  return { raw_original: rawOriginal, raw_normalized: value || null, removed_prefix: prefixes.join(" ") || null, normalization_notes: notes };
}

export function extractDouyinPostedMetadataFromText(text: string | null | undefined, options: { referenceTime?: Date | string | null; timezone?: string | null } = {}): {
  posted_text: string | null;
  posted_text_raw: string | null;
  posted_at: string | null;
  posted_display: string | null;
  posted_source: "modal_author_row" | "direct_publish_time" | "profile_card" | "none";
  parse_confidence: "raw_only" | "parsed" | "none";
  parser_pattern_matched?: string | null;
  raw_normalized?: string | null;
  normalization_notes?: string[];
} {
  const normalized = normalizeDouyinPostedRawText(text);
  const value = normalized.raw_normalized;
  if (!value) {
    return { posted_text: null, posted_text_raw: null, posted_at: null, posted_display: null, posted_source: "none", parse_confidence: "none", parser_pattern_matched: null, raw_normalized: null, normalization_notes: normalized.normalization_notes };
  }

  const candidate = findPostedDateCandidate(value);
  if (!candidate) {
    return { posted_text: null, posted_text_raw: normalized.raw_original, posted_at: null, posted_display: null, posted_source: "none", parse_confidence: "none", parser_pattern_matched: null, raw_normalized: value, normalization_notes: normalized.normalization_notes };
  }
  const parsed = parseDouyinPostedTextToDate({ postedText: candidate, referenceTime: options.referenceTime ?? null, timezone: options.timezone ?? null });
  const pattern = postedPatternName(candidate);
  const source = /^(?:发布时间|发布于)/.test((text ?? "").normalize("NFKC").trim()) ? "direct_publish_time" : "modal_author_row";
  if (parsed) {
    const display = formatDateDdMmYyyy(parsed, options.timezone ?? undefined);
    return { posted_text: display, posted_text_raw: normalized.raw_original ?? candidate, posted_at: parsed.toISOString(), posted_display: display, posted_source: source, parse_confidence: "parsed", parser_pattern_matched: pattern, raw_normalized: candidate, normalization_notes: normalized.normalization_notes };
  }

  return { posted_text: candidate, posted_text_raw: normalized.raw_original ?? candidate, posted_at: null, posted_display: null, posted_source: source, parse_confidence: "raw_only", parser_pattern_matched: pattern, raw_normalized: candidate, normalization_notes: normalized.normalization_notes };
}

export function parseDouyinPostedText(postedText: string | null | undefined, now: Date = new Date()): string | null {
  return parseDouyinPostedTextToDate({ postedText, referenceTime: now })?.toISOString() ?? null;
}

export function parseDouyinPostedTextToDate(args: {
  postedText: string | null | undefined;
  referenceTime?: Date | string | null;
  timezone?: string | null;
}): Date | null {
  const normalized = normalizeDouyinPostedRawText(args.postedText);
  const text = normalized.raw_normalized ?? "";
  if (!text) return null;

  const timezone = args.timezone?.trim() || "Asia/Shanghai";
  const referenceTime = normalizeReferenceTime(args.referenceTime);
  const referenceParts = zonedDateParts(referenceTime, timezone);
  const candidate = findPostedDateCandidate(text) ?? text;
  const absolute = candidate.match(/^(\d{4})[-/.年](\d{1,2})[-/.月](\d{1,2})(?:日)?(?:\s+(\d{1,2}):(\d{2}))?$/);
  if (absolute) {
    const [, year, month, day, hour = "0", minute = "0"] = absolute;
    return zonedTimeToUtcDate({ year: Number(year), month: Number(month), day: Number(day), hour: Number(hour), minute: Number(minute), timezone });
  }

  const monthDay = candidate.match(/^(\d{1,2})月(\d{1,2})日(?:\s+(\d{1,2}):(\d{2}))?$/);
  if (monthDay) {
    const [, month, day, hour = "0", minute = "0"] = monthDay;
    let parsed = zonedTimeToUtcDate({ year: referenceParts.year, month: Number(month), day: Number(day), hour: Number(hour), minute: Number(minute), timezone });
    if (!parsed) return null;
    if (parsed.getTime() - referenceTime.getTime() > 7 * 86_400_000) {
      parsed = zonedTimeToUtcDate({ year: referenceParts.year - 1, month: Number(month), day: Number(day), hour: Number(hour), minute: Number(minute), timezone });
    }
    return parsed;
  }

  const englishAbsolute = parseEnglishPostedDate(candidate, referenceTime, timezone);
  if (englishAbsolute) return englishAbsolute;

  if (/^just now$/i.test(candidate) || candidate === "刚刚") return referenceTime;
  if (/^yesterday$/i.test(candidate) || candidate === "昨天") return addCalendarParts(referenceParts, { days: -1, timezone });
  if (candidate === "前天") return addCalendarParts(referenceParts, { days: -2, timezone });

  const chineseRelative = candidate.match(/^(\d+|一|两)\s*(秒|分钟|小时|天|周|星期|个月|月|年)前$/);
  if (chineseRelative) {
    const amount = parseDouyinRelativeAmount(chineseRelative[1] ?? "");
    if (!Number.isFinite(amount) || amount < 0) return null;
    const unit = chineseRelative[2] ?? "";
    if (unit === "秒") return new Date(referenceTime.getTime() - amount * 1000);
    if (unit === "分钟") return new Date(referenceTime.getTime() - amount * 60_000);
    if (unit === "小时") return new Date(referenceTime.getTime() - amount * 3_600_000);
    if (unit === "天") return addCalendarParts(referenceParts, { days: -amount, timezone });
    if (unit === "周" || unit === "星期") return addCalendarParts(referenceParts, { days: -(amount * 7), timezone });
    if (unit === "个月" || unit === "月") return addCalendarParts(referenceParts, { months: -amount, timezone });
    if (unit === "年") return addCalendarParts(referenceParts, { years: -amount, timezone });
  }

  const englishRelative = candidate.match(/^(\d+)\s*(second|minute|hour|day|week|month|year)s?\s+ago$/i);
  if (englishRelative) {
    const amount = Number(englishRelative[1]);
    const unit = englishRelative[2]?.toLowerCase();
    if (unit === "second") return new Date(referenceTime.getTime() - amount * 1000);
    if (unit === "minute") return new Date(referenceTime.getTime() - amount * 60_000);
    if (unit === "hour") return new Date(referenceTime.getTime() - amount * 3_600_000);
    if (unit === "day") return addCalendarParts(referenceParts, { days: -amount, timezone });
    if (unit === "week") return addCalendarParts(referenceParts, { days: -(amount * 7), timezone });
    if (unit === "month") return addCalendarParts(referenceParts, { months: -amount, timezone });
    if (unit === "year") return addCalendarParts(referenceParts, { years: -amount, timezone });
  }
  return null;
}

function parseDouyinRelativeAmount(value: string): number {
  if (/^\d+$/.test(value)) return Number(value);
  if (value === "一") return 1;
  if (value === "两") return 2;
  return Number.NaN;
}

function looksLikePostedDateText(value: string): boolean {
  return Boolean(findPostedDateCandidate(value) ?? value.match(/^(?:刚刚|昨天|前天|just now|yesterday)$/i));
}

function findPostedDateCandidate(value: string): string | null {
  const text = value.normalize("NFKC").replace(/\s+/g, " ").trim();
  const patterns = [
    /(?:发布时间|发布于)\s*[:：]?\s*(\d{4}[-/.年]\d{1,2}[-/.月]\d{1,2}(?:日)?(?:\s+\d{1,2}:\d{2})?)/,
    /(\d{4}[-/.年]\d{1,2}[-/.月]\d{1,2}(?:日)?(?:\s+\d{1,2}:\d{2})?)/,
    /(\d{1,2}月\d{1,2}日(?:\s+\d{1,2}:\d{2})?)/,
    /(((?:\d+|一|两)\s*(?:秒|分钟|小时|天|周|星期|个月|月|年))前|刚刚|昨天|前天)/,
    /((?:just now|yesterday|\d+\s*(?:second|minute|hour|day|week|month|year)s?\s+ago))/i,
    /([A-Za-z]{3,9}\s+\d{1,2}(?:,\s*\d{4})?)/
  ];
  for (const pattern of patterns) {
    const match = text.match(pattern);
    if (match?.[1]) return match[1].trim();
  }
  return null;
}

function postedPatternName(value: string): string | null {
  if (/^\d{4}[-/.年]/.test(value)) return "absolute_with_year";
  if (/^\d{1,2}月\d{1,2}日/.test(value)) return "absolute_month_day_without_year";
  if (/^(?:刚刚|昨天|前天|(?:\d+|一|两)\s*(?:秒|分钟|小时|天|周|星期|个月|月|年)前)$/.test(value)) return "chinese_relative";
  if (/^(?:just now|yesterday|\d+\s*(?:second|minute|hour|day|week|month|year)s?\s+ago)$/i.test(value)) return "english_relative";
  if (/^[A-Za-z]{3,9}\s+\d{1,2}/.test(value)) return "english_absolute";
  return null;
}

function parseEnglishPostedDate(value: string, referenceTime: Date, timezone: string): Date | null {
  const match = value.match(/^([A-Za-z]{3,9})\s+(\d{1,2})(?:,\s*(\d{4}))?$/);
  if (!match) return null;
  const monthNames = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"];
  const month = monthNames.findIndex((name) => match[1]!.toLowerCase().startsWith(name)) + 1;
  if (month <= 0) return null;
  const referenceParts = zonedDateParts(referenceTime, timezone);
  const year = match[3] ? Number(match[3]) : referenceParts.year;
  let parsed = zonedTimeToUtcDate({ year, month, day: Number(match[2]), hour: 0, minute: 0, timezone });
  if (!match[3] && parsed && parsed.getTime() - referenceTime.getTime() > 7 * 86_400_000) {
    parsed = zonedTimeToUtcDate({ year: year - 1, month, day: Number(match[2]), hour: 0, minute: 0, timezone });
  }
  return parsed;
}

function addCalendarParts(parts: { year: number; month: number; day: number; hour: number; minute: number }, delta: { years?: number; months?: number; days?: number; timezone: string }): Date | null {
  const date = new Date(Date.UTC(parts.year + (delta.years ?? 0), parts.month - 1 + (delta.months ?? 0), 1));
  const targetYear = date.getUTCFullYear();
  const targetMonth = date.getUTCMonth() + 1;
  const maxDay = new Date(Date.UTC(targetYear, targetMonth, 0)).getUTCDate();
  const day = Math.min(parts.day, maxDay) + (delta.days ?? 0);
  return zonedTimeToUtcDate({ year: targetYear, month: targetMonth, day, hour: parts.hour, minute: parts.minute, timezone: delta.timezone });
}

export function formatDateDdMmYyyy(value: Date | string | null | undefined, timezone = "Asia/Shanghai"): string | null {
  if (!value) return null;
  const date = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(date.getTime())) return null;
  const parts = zonedDateParts(date, timezone);
  return `${String(parts.day).padStart(2, "0")}/${String(parts.month).padStart(2, "0")}/${parts.year}`;
}

function normalizeReferenceTime(value: Date | string | null | undefined): Date {
  if (value instanceof Date && !Number.isNaN(value.getTime())) return value;
  if (typeof value === "string") {
    const parsed = new Date(value);
    if (!Number.isNaN(parsed.getTime())) return parsed;
  }
  return new Date();
}

function zonedDateParts(value: Date, timezone: string): { year: number; month: number; day: number; hour: number; minute: number; second: number } {
  const formatter = new Intl.DateTimeFormat("en-CA", {
    timeZone: timezone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false
  });
  const map = Object.fromEntries(formatter.formatToParts(value).map((part) => [part.type, part.value]));
  return {
    year: Number(map.year),
    month: Number(map.month),
    day: Number(map.day),
    hour: Number(map.hour),
    minute: Number(map.minute),
    second: Number(map.second)
  };
}

function zonedTimeToUtcDate(args: { year: number; month: number; day: number; hour: number; minute: number; timezone: string }): Date | null {
  const baseUtc = new Date(Date.UTC(args.year, args.month - 1, args.day, args.hour, args.minute, 0));
  const parts = zonedDateParts(baseUtc, args.timezone);
  const asIfUtc = Date.UTC(parts.year, parts.month - 1, parts.day, parts.hour, parts.minute, 0);
  const targetUtc = Date.UTC(args.year, args.month - 1, args.day, args.hour, args.minute, 0);
  const adjusted = new Date(baseUtc.getTime() - (asIfUtc - targetUtc));
  return Number.isNaN(adjusted.getTime()) ? null : adjusted;
}

export function buildCanonicalHarvestQueue(state: WholeProfileHarvestState, options: CanonicalHarvestOptions = {}): WholeProfileHarvestQueueItem[] {
  const mode = options.mode ?? "new_and_incomplete";
  const limit = options.batch_limit ?? 10;
  const completed = new Set(mode === "refresh_all" ? [] : state.harvest.results.filter((result) => result.status === "extracted").map((result) => result.aweme_id));
  const detailByAwemeId = new Map(state.verify.target_details.map((detail) => [detail.aweme_id, detail]));
  const seen = new Set<string>();
  const queue: WholeProfileHarvestQueueItem[] = [];
  for (const awemeId of state.verify.targets) {
    if (!awemeId || seen.has(awemeId) || completed.has(awemeId)) continue;
    seen.add(awemeId);
    const detail = detailByAwemeId.get(awemeId);
    queue.push({
      index: queue.length + 1,
      aweme_id: awemeId,
      capture_status: detail?.capture_status ?? "unknown",
      status: detail?.capture_status === "incomplete" ? "incomplete" : detail?.capture_status === "complete" ? "backend_verified" : "pending",
      attempts: 0,
      retry_count: 0,
      checkpoint_sequence: null,
      extraction_result: null,
      last_error: null,
      last_attempt_at: null,
      saved_at: detail?.capture_status === "complete" ? detail.backend_item?.updated_at ?? null : null,
      capture_inbox_item_id: detail?.backend_item?.item_id ?? null,
      backend_item_id: detail?.backend_item?.item_id ?? null,
      metadata_status: detail?.backend_item?.metadata_status ?? null,
      source_url: detail?.source_url ?? `https://www.douyin.com/video/${awemeId}`,
      thumbnail_url: detail?.thumbnail_url ?? null,
      caption: detail?.caption ?? detail?.title ?? null,
      profile_card_evidence: sanitizeProfileCardEvidenceForBackend(detail?.profile_card_evidence ?? {}).profile_card_evidence
    });
  }
  return limit === "all" ? queue : queue.slice(0, Math.max(0, limit));
}

export function buildCanonicalBatchFlushQueue(state: WholeProfileHarvestState, options: CanonicalHarvestOptions = {}): WholeProfileHarvestQueueItem[] {
  const mode = options.mode ?? state.harvest.backend.batch_flush.mode ?? state.harvest_options.mode;
  const limit = options.batch_limit ?? state.harvest_options.batch_limit ?? 10;
  const previousQueue = state.harvest.backend.batch_flush.queue;
  const previousByAwemeId = new Map(previousQueue.map((item) => [item.aweme_id, item]));
  const latestExtractedByAwemeId = new Map<string, WholeProfileHarvestResult>();

  for (let index = state.harvest.results.length - 1; index >= 0; index -= 1) {
    const result = state.harvest.results[index];
    if (!result || result.status !== "extracted" || !result.aweme_id || latestExtractedByAwemeId.has(result.aweme_id)) continue;
    latestExtractedByAwemeId.set(result.aweme_id, result);
  }

  const queue: WholeProfileHarvestQueueItem[] = [];
  for (const result of latestExtractedByAwemeId.values()) {
    const awemeId = result.aweme_id;
    const previous = previousByAwemeId.get(awemeId);
    const alreadyFlushed = !!result.capture_inbox_item_id;
    const shouldSkipComplete = mode !== "refresh_all" && alreadyFlushed;
    const resumedStatus: WholeProfileHarvestQueueItem["status"] = previous?.status === "failed"
      ? "failed"
      : previous?.status === "skipped"
        ? "skipped"
        : "pending";

    let status: WholeProfileHarvestQueueItem["status"] = shouldSkipComplete ? "skipped" : resumedStatus;
    let lastError = shouldSkipComplete ? null : (previous?.last_error ?? null);
    let captureInboxItemId = shouldSkipComplete ? (result.capture_inbox_item_id ?? previous?.capture_inbox_item_id ?? null) : (previous?.capture_inbox_item_id ?? null);

    if (mode === "refresh_all") {
      status = previous?.status === "failed" ? "failed" : "pending";
      lastError = previous?.status === "failed" ? (previous?.last_error ?? null) : null;
      captureInboxItemId = null;
    }

    queue.push({
      index: queue.length + 1,
      aweme_id: awemeId,
      capture_status: previous?.capture_status ?? "complete",
      status,
      attempts: previous?.attempts ?? 0,
      retry_count: previous?.retry_count ?? previous?.attempts ?? 0,
      checkpoint_sequence: previous?.checkpoint_sequence ?? result.checkpoint_sequence ?? null,
      extraction_result: result.status,
      last_error: lastError,
      last_attempt_at: previous?.last_attempt_at ?? null,
      saved_at: result.completed_at ?? previous?.saved_at ?? null,
      capture_inbox_item_id: captureInboxItemId,
      backend_item_id: previous?.backend_item_id ?? captureInboxItemId,
      metadata_status: previous?.metadata_status ?? null,
      source_url: result.target_url ?? previous?.source_url ?? `https://www.douyin.com/video/${awemeId}`,
      thumbnail_url: previous?.thumbnail_url ?? result.thumbnail_url ?? null,
      caption: previous?.caption ?? result.caption ?? null,
      profile_card_evidence: sanitizeProfileCardEvidenceForBackend(result.profile_card_evidence ?? previous?.profile_card_evidence ?? {}).profile_card_evidence
    });
  }

  return limit === "all" ? queue : queue.slice(0, Math.max(0, limit));
}

export function buildCanonicalHarvestSessionRequest(state: WholeProfileHarvestState, runId: string): CanonicalHarvestSessionRequest {
  if (!state.profile_url) throw new Error("profile_url_required");
  const normalizedProfileUrl = normalizeProfileUrlForSession(state.profile_url);
  return {
    schema_version: "douyin_extension_capture_session.v1",
    source: "whole_profile_harvest",
    profile_url: state.profile_url,
    normalized_profile_url: normalizedProfileUrl,
    profile_sec_uid_or_path: secUidFromProfileUrl(normalizedProfileUrl),
    profile_display_name: null,
    profile_avatar_url: null,
    display_title: buildSessionDisplayTitle(normalizedProfileUrl),
    source_modal_aweme_id: state.source_modal_aweme_id,
    verified_target_count: state.verify.verified_target_count,
    queued_count: state.harvest.queue.length || state.verify.verified_target_count,
    run_id: runId,
    mode: "whole_profile_harvest"
  };
}

export function selectLatestExtractedResultForPayloadPreview(state: WholeProfileHarvestState): WholeProfileHarvestResult | null {
  for (let index = state.harvest.results.length - 1; index >= 0; index -= 1) {
    const result = state.harvest.results[index];
    if (result?.status === "extracted") return result;
  }
  return null;
}

export function sanitizeProfileCardEvidenceForBackend(value: Record<string, unknown> | null | undefined): { profile_card_evidence: Record<string, unknown>; removed_fields: CanonicalPayloadRemovedField[] } {
  const clean: Record<string, unknown> = {};
  const removed_fields: CanonicalPayloadRemovedField[] = [];
  for (const [key, raw] of Object.entries(value ?? {})) {
    if (!PROFILE_CARD_ALLOWLIST.has(key)) {
      removed_fields.push({ path: `$.profile_card_evidence.${key}`, reason: "not_allowlisted" });
      continue;
    }
    if (key === "view_count") {
      const numeric = numberValue(raw);
      if (numeric !== null) clean[key] = numeric;
      continue;
    }
    const text = stringValue(raw);
    if (text !== null) clean[key] = text;
  }
  return { profile_card_evidence: clean, removed_fields };
}

export function buildRawEvidenceSummaryForCanonicalHarvest(result: WholeProfileHarvestResult): CanonicalHarvestPayload["raw_evidence_summary"] {
  const sanitized = sanitizeProfileCardEvidenceForBackend(result.profile_card_evidence);
  return {
    source: "whole_profile_harvest",
    extraction_stage: "phase11a_production_stabilized_calibrated_harvest",
    extractor_version: "whole_profile_modal_extract_only.v1",
    metrics: {
      current_modal_id_before: result.current_modal_id_before,
      current_modal_id_after: result.current_modal_id_after,
      extracted_aweme_id: result.extracted_aweme_id,
      duration_seconds: result.duration_seconds,
      duration_text: result.duration_text,
      duration_raw: result.duration_raw ?? null,
      duration_validation_result: result.duration_validation_result ?? null,
      duration_candidate_list: Array.isArray(result.duration_candidate_list) ? result.duration_candidate_list : [],
      like_count: result.like_count,
      comment_count: result.comment_count,
      favorite_count: result.favorite_count,
      share_count: result.share_count,
      source_used: result.source_used ?? null,
      posted_text_raw: result.posted_text_raw ?? result.posted_text ?? null,
      posted_at: result.posted_at ?? null,
      posted_display: result.posted_display ?? formatDateDdMmYyyy(result.posted_at ?? null),
      posted_source: result.posted_source ?? null,
      posted_parse_confidence: result.posted_parse_confidence ?? null
    },
    profile_card_snapshot: {
      source_url: stringValue(sanitized.profile_card_evidence.source_url),
      title: stringValue(sanitized.profile_card_evidence.title),
      caption: stringValue(sanitized.profile_card_evidence.caption),
      posted_text: stringValue(sanitized.profile_card_evidence.posted_text),
      posted_text_raw: stringValue(sanitized.profile_card_evidence.posted_text_raw),
      posted_display: stringValue(sanitized.profile_card_evidence.posted_display),
      thumbnail_url: stringValue(sanitized.profile_card_evidence.thumbnail_url),
      view_count: numberValue(sanitized.profile_card_evidence.view_count),
      view_text: stringValue(sanitized.profile_card_evidence.view_text)
    }
  };
}

export function buildCanonicalFullModalPayloadPreview(state: WholeProfileHarvestState, extractedResult: WholeProfileHarvestResult): { payload: CanonicalHarvestPayload; removed_fields: CanonicalPayloadRemovedField[] } {
  if (!state.capture_session_id) throw new Error("capture_session_missing");
  if (!state.profile_url) throw new Error("profile_url_required");
  const sanitized = sanitizeProfileCardEvidenceForBackend(extractedResult.profile_card_evidence);
  const evidence = sanitized.profile_card_evidence;
  const payload: CanonicalHarvestPayload = {
    capture_session_id: state.capture_session_id,
    commit_policy: "finalized_only",
    aweme_id: extractedResult.aweme_id,
    target_aweme_id: extractedResult.aweme_id,
    source_video_external_id: extractedResult.aweme_id,
    profile_url: state.profile_url,
    source_url: stringValue(evidence.source_url) ?? extractedResult.target_url ?? null,
    current_modal_id_before: extractedResult.current_modal_id_before,
    current_modal_id_after: extractedResult.current_modal_id_after,
    extracted_aweme_id: extractedResult.extracted_aweme_id,
    duration_seconds: extractedResult.duration_seconds,
    duration_text: extractedResult.duration_text,
    like_count: extractedResult.like_count,
    comment_count: extractedResult.comment_count,
    favorite_count: extractedResult.favorite_count,
    share_count: extractedResult.share_count,
    raw_evidence_summary: buildRawEvidenceSummaryForCanonicalHarvest(extractedResult),
    profile_card_evidence: evidence
  };
  const title = stringValue(evidence.title ?? evidence.caption);
  const caption = stringValue(evidence.caption ?? evidence.title);
  const thumbnailUrl = stringValue(evidence.thumbnail_url);
  const postedText = stringValue(evidence.posted_text);
  const viewCount = numberValue(evidence.view_count);
  if (title) payload.title = title;
  if (caption) payload.caption = caption;
  if (thumbnailUrl) payload.thumbnail_url = thumbnailUrl;
  if (postedText) payload.posted_text = postedText;
  if (viewCount !== null) payload.view_count = viewCount;
  return { payload, removed_fields: sanitized.removed_fields };
}

export function buildCaptureInboxItemPayload(args: {
  capture_session_id: string;
  target: WholeProfileHarvestQueueItem;
  extracted: WholeProfileHarvestMetrics;
  profile_url: string;
  run_id?: string | null;
  source_url?: string | null;
  started_at?: string | null;
}): CaptureInboxItemPayload {
  const { capture_session_id, target, extracted, profile_url } = args;
  const awemeId = target.aweme_id;
  const sourceUrl = args.source_url ?? target.source_url ?? `https://www.douyin.com/video/${awemeId}`;
  const extractedRecord = extracted as WholeProfileHarvestMetrics & Record<string, unknown>;
  const targetEvidence = target.profile_card_evidence ?? {};
  const thumbnail = resolveAwemeThumbnail({ awemeId, target, extracted: extractedRecord });
  const thumbnailUrl = thumbnail.thumbnail_url;
  const extractedPostedText = stringValue(extractedRecord.posted_text);
  const extractedPostedTextRaw = stringValue(extractedRecord.posted_text_raw) ?? extractedPostedText;
  const extractedPostedAt = stringValue(extractedRecord.posted_at);
  const extractedPostedDisplay = stringValue(extractedRecord.posted_display) ?? formatDateDdMmYyyy(extractedPostedAt ?? null);
  const targetPostedText = stringValue(targetEvidence.posted_text);
  const targetPostedTextRaw = stringValue(targetEvidence.posted_text_raw) ?? targetPostedText;
  const targetPostedAt = stringValue(targetEvidence.posted_at);
  const targetPostedDisplay = stringValue(targetEvidence.posted_display) ?? formatDateDdMmYyyy(targetPostedAt ?? null);
  const postedTextRaw = extractedPostedTextRaw ?? targetPostedTextRaw;
  const postedAt = extractedPostedAt ?? targetPostedAt;
  const postedDisplay = extractedPostedDisplay ?? targetPostedDisplay ?? formatDateDdMmYyyy(postedAt ?? null);
  const postedText = postedDisplay ?? extractedPostedText ?? targetPostedText;
  const caption = stringValue(targetEvidence.caption)
    ?? stringValue(targetEvidence.title)
    ?? stringValue(extractedRecord.caption);
  const postedSource = postedTextRaw || postedAt || postedDisplay
    ? extractedPostedAt
      ? stringValue(extractedRecord.posted_source) ?? "aweme_create_time"
      : extractedPostedTextRaw
        ? stringValue(extractedRecord.posted_source) ?? "modal_author_row"
        : (targetPostedTextRaw || targetPostedAt || targetPostedDisplay ? "profile_card" : null)
    : null;
  const postedParseConfidence = stringValue(extractedRecord.posted_parse_confidence)
    ?? stringValue(targetEvidence.posted_parse_confidence)
    ?? (postedAt ? "parsed" : postedTextRaw ? "raw_only" : "none");
  const evidence = sanitizeProfileCardEvidenceForBackend({
    ...targetEvidence,
    source_url: sourceUrl,
    caption,
    thumbnail_url: thumbnailUrl,
    posted_text: postedText,
    posted_text_raw: postedTextRaw,
    posted_at: postedAt,
    posted_display: postedDisplay,
    thumbnail_source: thumbnail.thumbnail_source !== "none" ? thumbnail.thumbnail_source : null,
    posted_source: postedSource,
    posted_parse_confidence: postedParseConfidence,
    posted_parser_pattern_matched: stringValue(extractedRecord.posted_parser_pattern_matched) ?? stringValue(targetEvidence.posted_parser_pattern_matched),
    posted_reference_time: stringValue(extractedRecord.posted_reference_time) ?? stringValue(targetEvidence.posted_reference_time),
    posted_timezone: stringValue(extractedRecord.posted_timezone) ?? stringValue(targetEvidence.posted_timezone)
  }).profile_card_evidence;
  const profileCardEvidence: FullModalHarvestItemPayload["profile_card_evidence"] = {
    aweme_id: awemeId,
    source_url: stringValue(evidence.source_url) ?? sourceUrl,
    title: stringValue(evidence.title),
    caption: stringValue(evidence.caption),
    desc: stringValue(evidence.desc),
    description: stringValue(evidence.description),
    thumbnail_url: stringValue(evidence.thumbnail_url),
    cover_url: stringValue(evidence.cover_url),
    poster_url: stringValue(evidence.poster_url),
    posted_text: stringValue(evidence.posted_text),
    posted_text_raw: stringValue(evidence.posted_text_raw),
    posted_at: stringValue(evidence.posted_at),
    posted_display: stringValue(evidence.posted_display),
    thumbnail_source: stringValue(evidence.thumbnail_source),
    posted_source: stringValue(evidence.posted_source),
    posted_parse_confidence: stringValue(evidence.posted_parse_confidence),
    posted_parser_pattern_matched: stringValue(evidence.posted_parser_pattern_matched),
    posted_reference_time: stringValue(evidence.posted_reference_time),
    posted_timezone: stringValue(evidence.posted_timezone)
  };
  const rawDomDetailMetrics = {
    aweme_id: awemeId,
    target_aweme_id: awemeId,
    duration_seconds: extracted.duration_seconds,
    duration_text: extracted.duration_text,
    selected_duration_source: extracted.source_used ?? "calibrated_point_dom",
    duration_raw: extracted.duration_raw ?? null,
    duration_validation_result: extracted.duration_validation_result ?? null,
    duration_candidate_list: Array.isArray(extracted.duration_candidate_list) ? extracted.duration_candidate_list : [],
    like_count: extracted.like_count,
    comment_count: extracted.comment_count,
    favorite_count: extracted.favorite_count,
    share_count: extracted.share_count,
    posted_text: postedText,
    posted_text_raw: postedTextRaw,
    posted_at: postedAt,
    posted_display: postedDisplay,
    posted_source: postedSource,
    posted_parse_confidence: postedParseConfidence,
    posted_parser_pattern_matched: stringValue(evidence.posted_parser_pattern_matched),
    posted_reference_time: stringValue(evidence.posted_reference_time),
    posted_timezone: stringValue(evidence.posted_timezone),
    thumbnail_url: thumbnailUrl,
    caption,
    extraction_source: "calibrated_point_dom",
    source_used: extracted.source_used ?? "calibrated_point_dom",
    confidence: "high"
  };
  const hasPostedMetadata = Boolean(postedAt || postedTextRaw || postedDisplay || postedText);
  const item: FullModalHarvestItemPayload = {
    aweme_id: awemeId,
    target_aweme_id: awemeId,
    source_video_external_id: awemeId,
    metadata_status: thumbnailUrl && hasPostedMetadata && caption ? "ready" : "needs_metadata",
    review_status: "pending_review",
    source_url: sourceUrl,
    page_url: sourceUrl,
    modal_id: awemeId,
    raw_dom_detail_metrics: rawDomDetailMetrics as FullModalHarvestItemPayload["raw_dom_detail_metrics"],
    raw_evidence_summary: {
      has_network_aweme: false,
      has_detail_aweme: false,
      has_dom_snapshot: false,
      has_dom_detail_metrics: true,
      network_keys: [],
      detail_keys: [],
      dom_detail_metric_keys: [
        "duration_seconds",
        "duration_text",
        ...(extracted.source_used ? ["selected_duration_source"] : []),
        ...(typeof extracted.duration_raw === "number" ? ["duration_raw"] : []),
        ...(extracted.duration_validation_result ? ["duration_validation_result"] : []),
        ...(Array.isArray(extracted.duration_candidate_list) ? ["duration_candidate_list"] : []),
        "like_count",
        "comment_count",
        "favorite_count",
        "share_count",
        ...(postedText ? ["posted_text"] : []),
        ...(postedTextRaw ? ["posted_text_raw"] : []),
        ...(postedAt ? ["posted_at"] : []),
        ...(postedDisplay ? ["posted_display"] : []),
        ...(postedSource ? ["posted_source"] : []),
        ...(postedParseConfidence ? ["posted_parse_confidence"] : []),
        ...(thumbnailUrl ? ["thumbnail_url"] : [])
      ],
      evidence_sources: ["whole_profile_harvest", "one_item_smoke_test", "profile_card_evidence"],
      evidence_collection_version: "phase11a_production_stabilized_calibrated_harvest"
    },
    profile_card_evidence: profileCardEvidence,
    modal_aweme_id_before_extract: extracted.current_modal_id_before ?? awemeId,
    modal_aweme_id_after_extract: extracted.current_modal_id_after ?? awemeId,
    extracted_aweme_id: extracted.extracted_aweme_id ?? awemeId,
    data_integrity_status: "passed",
    data_integrity_reason: null,
    metric_signature: null,
    duplicate_signature_warning: null
  };
  const now = args.started_at ?? new Date().toISOString();
  return {
    schema_version: "douyin_full_modal_harvest.v1",
    capture_session_id,
    run_id: args.run_id ?? null,
    profile_url,
    target_aweme_id: awemeId,
    source_video_external_id: awemeId,
    started_at: now,
    page: { page_type: "video_detail_page", url: sourceUrl, title: null, profile_url, video_link_count: 1 },
    capture_context: { capture_id: args.run_id ?? `one_item_smoke_test_${awemeId}`, page_url: sourceUrl, captured_at: now, profile_url },
    items: [item],
    progress: {
      running: false,
      current_state: "completed",
      phase: "completed",
      target_count: 1,
      current_index: 1,
      current_aweme_id: awemeId,
      harvested_count: 1,
      updated_count: 1,
      pending_count: 0,
      duplicate_count: 0,
      failed_count: 0,
      flushed_count: 1,
      last_error: null,
      stopped_reason: "one_item_smoke_test_completed",
      last_flush_status: "success",
      next_flush_in_items: 0
    },
    commit_policy: "finalized_only"
  };
}

export function buildCleanCaptureInboxItemPayload(input: CaptureInboxItemPayload): { payload: CaptureInboxItemPayload; sanitizer_diagnostics: CaptureInboxPayloadSanitizerDiagnostic[] } {
  const body = input && typeof input === "object" ? input as FullModalHarvestRequestPayload : buildCaptureInboxItemPayload(input as never);
  const item = Array.isArray(body.items) ? body.items[0] : null;
  const metrics = item?.raw_dom_detail_metrics ?? {} as FullModalHarvestItemPayload["raw_dom_detail_metrics"];
  const metricsRecord = metrics as unknown as Record<string, unknown>;
  const preSanitizerDiagnostics: CaptureInboxPayloadSanitizerDiagnostic[] = [];
  for (const rawMetricKey of ["duration", "like_count", "comment_count", "favorite_count", "share_count"] as const) {
    if (Object.prototype.hasOwnProperty.call(metricsRecord, rawMetricKey)) {
      preSanitizerDiagnostics.push({ path: `$.items[0].raw_dom_detail_metrics.${rawMetricKey}`, reason: "forbidden_key" });
    }
  }
  const evidence = (item?.profile_card_evidence ?? {}) as Record<string, unknown>;
  const cleanItem: FullModalHarvestItemPayload = {
    aweme_id: item?.aweme_id ?? body.target_aweme_id ?? body.source_video_external_id ?? "",
    target_aweme_id: item?.target_aweme_id ?? item?.aweme_id ?? body.target_aweme_id ?? "",
    source_video_external_id: item?.source_video_external_id ?? body.source_video_external_id ?? item?.aweme_id ?? "",
    metadata_status: item?.metadata_status ?? "needs_metadata",
    review_status: item?.review_status ?? "pending_review",
    source_url: item?.source_url ?? body.page?.url ?? null,
    page_url: item?.page_url ?? item?.source_url ?? body.page?.url ?? null,
    modal_id: item?.modal_id ?? item?.aweme_id ?? body.target_aweme_id ?? null,
    raw_dom_detail_metrics: {
      aweme_id: metrics.aweme_id ?? item?.aweme_id ?? body.target_aweme_id ?? null,
      target_aweme_id: metrics.target_aweme_id ?? item?.target_aweme_id ?? body.target_aweme_id ?? null,
      duration_seconds: numberValue(metrics.duration_seconds) ?? numberValue(metricsRecord.duration),
      duration_text: stringValue(metrics.duration_text),
      selected_duration_source: stringValue(metricsRecord.selected_duration_source),
      duration_raw: numberValue(metricsRecord.duration_raw),
      duration_validation_result: stringValue(metricsRecord.duration_validation_result),
      duration_candidate_list: Array.isArray(metricsRecord.duration_candidate_list) ? metricsRecord.duration_candidate_list : [],
      like_count: numberValue(metrics.like_count),
      comment_count: numberValue(metrics.comment_count),
      favorite_count: numberValue(metrics.favorite_count),
      share_count: numberValue(metrics.share_count),
      posted_text: stringValue(metricsRecord.posted_text),
      posted_text_raw: stringValue(metricsRecord.posted_text_raw),
      posted_at: stringValue(metricsRecord.posted_at),
      posted_display: stringValue(metricsRecord.posted_display),
      posted_source: stringValue(metricsRecord.posted_source),
      posted_parse_confidence: stringValue(metricsRecord.posted_parse_confidence),
      posted_parser_pattern_matched: stringValue(metricsRecord.posted_parser_pattern_matched),
      posted_reference_time: stringValue(metricsRecord.posted_reference_time),
      posted_timezone: stringValue(metricsRecord.posted_timezone),
      thumbnail_url: stringValue(metricsRecord.thumbnail_url),
      caption: stringValue(metricsRecord.caption),
      extraction_source: stringValue(metricsRecord.extraction_source),
      source_used: stringValue(metricsRecord.source_used),
      confidence: stringValue(metricsRecord.confidence)
    } as FullModalHarvestItemPayload["raw_dom_detail_metrics"],
    raw_evidence_summary: ({
      has_network_aweme: item?.raw_evidence_summary?.has_network_aweme === true,
      has_detail_aweme: item?.raw_evidence_summary?.has_detail_aweme === true,
      has_dom_snapshot: item?.raw_evidence_summary?.has_dom_snapshot === true,
      has_dom_detail_metrics: item?.raw_evidence_summary?.has_dom_detail_metrics !== false,
      network_keys: Array.isArray(item?.raw_evidence_summary?.network_keys) ? item.raw_evidence_summary.network_keys.filter((key) => typeof key === "string") : [],
      detail_keys: Array.isArray(item?.raw_evidence_summary?.detail_keys) ? item.raw_evidence_summary.detail_keys.filter((key) => typeof key === "string") : [],
      dom_detail_metric_keys: Array.isArray(item?.raw_evidence_summary?.dom_detail_metric_keys) ? item.raw_evidence_summary.dom_detail_metric_keys.filter((key) => typeof key === "string") : [],
      evidence_sources: Array.isArray(item?.raw_evidence_summary?.evidence_sources) ? item.raw_evidence_summary.evidence_sources.filter((key) => typeof key === "string") : [],
      evidence_collection_version: stringValue(item?.raw_evidence_summary?.evidence_collection_version) ?? "phase11a_production_stabilized_calibrated_harvest"
    }) as FullModalHarvestItemPayload["raw_evidence_summary"],
    profile_card_evidence: {
      aweme_id: item?.aweme_id ?? body.target_aweme_id ?? body.source_video_external_id ?? "",
      source_url: stringValue(evidence.source_url) ?? item?.source_url ?? null,
      title: stringValue(evidence.title),
      caption: stringValue(evidence.caption),
      desc: stringValue(evidence.desc),
      description: stringValue(evidence.description),
      thumbnail_url: stringValue(evidence.thumbnail_url),
      cover_url: stringValue(evidence.cover_url),
      poster_url: stringValue(evidence.poster_url),
      posted_text: stringValue(evidence.posted_text),
      posted_text_raw: stringValue(evidence.posted_text_raw),
      posted_at: stringValue(evidence.posted_at),
      posted_display: stringValue(evidence.posted_display),
      thumbnail_source: stringValue(evidence.thumbnail_source),
      posted_source: stringValue(evidence.posted_source),
      posted_parse_confidence: stringValue(evidence.posted_parse_confidence),
      posted_parser_pattern_matched: stringValue(evidence.posted_parser_pattern_matched),
      posted_reference_time: stringValue(evidence.posted_reference_time),
      posted_timezone: stringValue(evidence.posted_timezone)
    },
    modal_aweme_id_before_extract: item?.modal_aweme_id_before_extract ?? null,
    modal_aweme_id_after_extract: item?.modal_aweme_id_after_extract ?? null,
    extracted_aweme_id: item?.extracted_aweme_id ?? item?.aweme_id ?? body.target_aweme_id ?? null,
    data_integrity_status: item?.data_integrity_status ?? "passed",
    data_integrity_reason: item?.data_integrity_reason ?? null,
    metric_signature: item?.metric_signature ?? null,
    duplicate_signature_warning: item?.duplicate_signature_warning ?? null
  };
  const clean: CaptureInboxItemPayload = {
    schema_version: "douyin_full_modal_harvest.v1",
    capture_session_id: body.capture_session_id ?? null,
    run_id: body.run_id ?? null,
    profile_url: body.profile_url ?? null,
    target_aweme_id: body.target_aweme_id ?? cleanItem.aweme_id,
    source_video_external_id: body.source_video_external_id ?? cleanItem.source_video_external_id ?? null,
    started_at: body.started_at ?? new Date().toISOString(),
    page: { page_type: body.page?.page_type ?? "video_detail_page", url: body.page?.url ?? cleanItem.source_url ?? "", title: body.page?.title ?? null, profile_url: body.page?.profile_url ?? body.profile_url ?? null, video_link_count: typeof body.page?.video_link_count === "number" ? body.page.video_link_count : 1 },
    capture_context: { capture_id: body.capture_context?.capture_id ?? body.run_id ?? null, page_url: body.capture_context?.page_url ?? cleanItem.source_url ?? null, captured_at: body.capture_context?.captured_at ?? body.started_at, profile_url: body.capture_context?.profile_url ?? body.profile_url ?? null },
    items: [cleanItem],
    progress: { running: false, current_state: "completed", phase: "completed", target_count: 1, current_index: 1, current_aweme_id: cleanItem.aweme_id, harvested_count: 1, updated_count: 1, pending_count: 0, duplicate_count: 0, failed_count: 0, flushed_count: 1, last_error: null, stopped_reason: "one_item_smoke_test_completed", last_flush_status: "success", next_flush_in_items: 0 },
    commit_policy: "finalized_only"
  };
  const sanitized = sanitizeCaptureInboxPayloadValue(clean);
  return { payload: sanitized.value as CaptureInboxItemPayload, sanitizer_diagnostics: [...preSanitizerDiagnostics, ...sanitized.diagnostics] };
}

export function sanitizeCaptureInboxPayloadValue(value: unknown, path = "$", diagnostics: CaptureInboxPayloadSanitizerDiagnostic[] = []): CaptureInboxPayloadSanitizeResult {
  if (value === null || typeof value === "boolean" || typeof value === "string") {
    if (typeof value === "string" && value.length > CAPTURE_INBOX_SANITIZER_MAX_STRING_LENGTH) {
      diagnostics.push({ path, reason: "oversized_string" });
      return { value: value.slice(0, CAPTURE_INBOX_SANITIZER_MAX_STRING_LENGTH), diagnostics };
    }
    return { value, diagnostics };
  }
  if (typeof value === "number") {
    if (!Number.isFinite(value)) {
      diagnostics.push({ path, reason: "non_finite_number" });
      return { value: null, diagnostics };
    }
    return { value, diagnostics };
  }
  if (value instanceof Date) return { value: value.toISOString(), diagnostics };
  if (typeof value === "function" || typeof value === "symbol" || typeof value === "bigint" || typeof value === "undefined") {
    diagnostics.push({ path, reason: "unsupported_value" });
    return { value: null, diagnostics };
  }
  if (Array.isArray(value)) {
    const limited = value.slice(0, CAPTURE_INBOX_SANITIZER_MAX_ARRAY_LENGTH);
    if (limited.length !== value.length) diagnostics.push({ path, reason: "oversized_array" });
    return { value: limited.map((child, index) => sanitizeCaptureInboxPayloadValue(child, `${path}[${index}]`, diagnostics).value), diagnostics };
  }
  if (typeof value === "object") {
    const clean: Record<string, unknown> = {};
    for (const [key, child] of Object.entries(value as Record<string, unknown>)) {
      const childPath = `${path}.${key}`;
      if (isForbiddenSecretDebugKey(key)) {
        diagnostics.push({ path: childPath, reason: "forbidden_key" });
        continue;
      }
      clean[key] = sanitizeCaptureInboxPayloadValue(child, childPath, diagnostics).value;
    }
    return { value: clean, diagnostics };
  }
  diagnostics.push({ path, reason: "unsupported_value" });
  return { value: null, diagnostics };
}

export function guardNoSecretDebugLeakage(payload: unknown): CanonicalPayloadGuardResult {
  const offending_paths = findSecretDebugLeakage(payload, "$", true);
  if (offending_paths.length === 0) return { ok: true, offending_paths: [] };
  return { ok: false, code: "payload_contains_disallowed_field_local", path: offending_paths[0] ?? "$.unknown", offending_paths };
}

export function guardCaptureInboxPayload(payload: unknown): CanonicalPayloadGuardResult {
  const secretDebugGuard = guardNoSecretDebugLeakage(payload);
  if (!secretDebugGuard.ok) return secretDebugGuard;
  const disallowed = guardCanonicalHarvestPayload(payload);
  if (!disallowed.ok) return disallowed;
  if (!payload || typeof payload !== "object") return { ok: false, code: "payload_invalid", path: "$", offending_paths: ["$"] };
  const body = payload as FullModalHarvestRequestPayload;
  const item = Array.isArray(body.items) ? body.items[0] : null;
  const metrics = item?.raw_dom_detail_metrics;
  const missing: string[] = [];
  if (!body.capture_session_id) missing.push("$.capture_session_id");
  if (body.capture_session_source !== undefined && body.capture_session_source !== null) missing.push("$.capture_session_source");
  if (!item?.aweme_id) missing.push("$.items[0].aweme_id");
  if (!item?.source_url && !item?.page_url) missing.push("$.items[0].source_url");
  if (!metrics || (metrics.duration_seconds === null && metrics.duration_text === null)) missing.push("$.items[0].raw_dom_detail_metrics.duration");
  for (const key of ["like_count", "comment_count", "favorite_count", "share_count"] as const) {
    if (!metrics || metrics[key] === null || metrics[key] === undefined) missing.push(`$.items[0].raw_dom_detail_metrics.${key}`);
  }
  if (missing.length > 0) return { ok: false, code: "capture_inbox_payload_missing_required_fields", path: missing[0] ?? "$", offending_paths: missing };
  return { ok: true, offending_paths: [] };
}

export function buildCanonicalHarvestPayload(target: WholeProfileHarvestQueueItem, metrics: WholeProfileHarvestMetrics, state: WholeProfileHarvestState): CanonicalHarvestPayload {
  const extractedResult: WholeProfileHarvestResult = {
    index: target.index,
    aweme_id: target.aweme_id,
    status: "extracted",
    stage: "validate_identity",
    attempts: target.attempts,
    checkpoint_sequence: target.checkpoint_sequence,
    error: null,
    error_code: null,
    error_message: null,
    modal_opened: true,
    modal_id_matched: true,
    metrics_extracted: true,
    payload_built: true,
    backend_called: false,
    backend_status: null,
    backend_error_code: null,
    capture_inbox_item_id: null,
    target_url: target.source_url,
    data_integrity_status: "passed",
    profile_card_evidence: target.profile_card_evidence,
    started_at: state.updated_at ?? new Date(0).toISOString(),
    completed_at: state.updated_at ?? new Date(0).toISOString(),
    duration_seconds: metrics.duration_seconds,
    duration_text: metrics.duration_text,
    like_count: metrics.like_count,
    comment_count: metrics.comment_count,
    favorite_count: metrics.favorite_count,
    share_count: metrics.share_count,
    current_modal_id_before: metrics.current_modal_id_before,
    current_modal_id_after: metrics.current_modal_id_after,
    extracted_aweme_id: metrics.extracted_aweme_id,
    source_used: metrics.source_used ?? null
  };
  return buildCanonicalFullModalPayloadPreview(state, extractedResult).payload;
}

export function guardCanonicalHarvestPayload(payload: unknown): CanonicalPayloadGuardResult {
  const offending_paths = findDisallowed(payload, "$", true);
  if (offending_paths.length === 0) return { ok: true, offending_paths: [] };
  return { ok: false, code: "payload_contains_disallowed_field_local", path: offending_paths[0] ?? "$.unknown", offending_paths };
}

export function summarizeCanonicalHarvestPayload(payload: CanonicalHarvestPayload | FullModalHarvestRequestPayload): Record<string, unknown> {
  if ("items" in payload) {
    const item = payload.items[0] ?? null;
    const metrics = item?.raw_dom_detail_metrics ?? null;
    return {
      schema_version: payload.schema_version,
      aweme_id: item?.aweme_id ?? null,
      capture_session_id: payload.capture_session_id ?? null,
      source_video_external_id: payload.source_video_external_id ?? item?.source_video_external_id ?? null,
      has_metrics: Boolean(metrics && (metrics.duration_seconds !== null || metrics.duration_text !== null || metrics.like_count !== null)),
      profile_url: payload.profile_url ?? null,
      item_count: payload.items.length,
      commit_policy: payload.commit_policy ?? null,
      removed_disallowed_fields: 0,
      profile_card_evidence_keys: item?.profile_card_evidence ? Object.keys(item.profile_card_evidence).sort().join(",") || "none" : "none"
    };
  }
  return {
    aweme_id: payload.aweme_id,
    capture_session_id: payload.capture_session_id,
    source_video_external_id: payload.source_video_external_id,
    has_metrics: payload.duration_seconds !== null || payload.like_count !== null,
    profile_url: payload.profile_url,
    removed_disallowed_fields: 0,
    profile_card_evidence_keys: Object.keys(payload.profile_card_evidence).sort().join(",") || "none"
  };
}

export function canonicalResultFromSuccess(target: WholeProfileHarvestQueueItem, metrics: WholeProfileHarvestMetrics, captureInboxItemId: string, completedAt: string): WholeProfileHarvestResult {
  return {
    index: target.index,
    aweme_id: target.aweme_id,
    status: "extracted",
    stage: "verify_backend_item",
    attempts: target.attempts + 1,
    checkpoint_sequence: target.checkpoint_sequence,
    error: null,
    error_code: null,
    error_message: null,
    modal_opened: true,
    modal_id_matched: true,
    metrics_extracted: true,
    payload_built: true,
    backend_called: true,
    backend_status: 200,
    backend_error_code: null,
    capture_inbox_item_id: captureInboxItemId,
    target_url: target.source_url,
    data_integrity_status: "passed",
    profile_card_evidence: target.profile_card_evidence,
    started_at: completedAt,
    completed_at: completedAt,
    duration_seconds: metrics.duration_seconds,
    duration_text: metrics.duration_text,
    like_count: metrics.like_count,
    comment_count: metrics.comment_count,
    favorite_count: metrics.favorite_count,
    share_count: metrics.share_count,
    current_modal_id_before: metrics.current_modal_id_before,
    current_modal_id_after: metrics.current_modal_id_after,
    extracted_aweme_id: metrics.extracted_aweme_id,
    source_used: metrics.source_used ?? null
  };
}

export function delayPolicyForSpeed(speed: WholeProfileHarvestSpeed, random = Math.random): { delay_between_targets_ms: number; pause_after_every: number; pause_duration_ms: number } {
  const range: [number, number, number, number, number] = speed === "fast" ? [500, 1200, 30, 5000, 15000] : speed === "normal" ? [1200, 2500, 20, 15000, 30000] : [2500, 5000, 10, 30000, 60000];
  const pick = (min: number, max: number) => Math.round(min + (max - min) * random());
  return { delay_between_targets_ms: pick(range[0], range[1]), pause_after_every: range[2], pause_duration_ms: pick(range[3], range[4]) };
}

function findDisallowed(value: unknown, path: string, root: boolean): string[] {
  if (!value || typeof value !== "object") return [];
  const offending: string[] = [];
  for (const [key, child] of Object.entries(value as Record<string, unknown>)) {
    const childPath = `${path}.${key}`;
    if (DISALLOWED_KEYS.has(key.toLowerCase())) offending.push(childPath);
    if (key === "capture_session_id" && !root) offending.push(childPath);
    offending.push(...findDisallowed(child, childPath, false));
  }
  return Array.from(new Set(offending));
}

function isForbiddenSecretDebugKey(key: string): boolean {
  const lowered = key.toLowerCase();
  if (BACKEND_SECRET_ALLOWED_KEYS.has(lowered)) return false;
  if (DISALLOWED_KEYS.has(lowered)) return true;
  return BACKEND_SECRET_KEY_MARKERS.some((marker) => lowered.includes(marker));
}

function findSecretDebugLeakage(value: unknown, path: string, root: boolean): string[] {
  if (!value || typeof value !== "object") return [];
  const offending: string[] = [];
  for (const [key, child] of Object.entries(value as Record<string, unknown>)) {
    const childPath = `${path}.${key}`;
    if (isForbiddenSecretDebugKey(key) || (key === "capture_session_id" && !root)) offending.push(childPath);
    offending.push(...findSecretDebugLeakage(child, childPath, false));
  }
  return Array.from(new Set(offending));
}

function stringValue(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function numberValue(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}
