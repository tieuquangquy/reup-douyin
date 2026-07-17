import type { ExtensionBackendPostRequest, ExtensionBackendPostResponse } from "./types.js";

export type FullModalHarvestRequestDiagnostics = Record<string, unknown>;
export type FullModalHarvestResponseDiagnostics = Record<string, unknown>;

export type FullModalHarvestGuardContext = {
  caller: string;
  requireV2?: boolean;
  finalRequestFingerprint?: string | null;
  finalRequestBodyPreview?: Record<string, unknown> | null;
};

export type FullModalHarvestGuardResult = {
  ok: true;
  offending_paths: string[];
};

const FULL_MODAL_HARVEST_PATH = "/douyin-extension/full-modal-harvest";
const FULL_MODAL_ALLOWED_TOP_LEVEL_KEYS = new Set([
  "schema_version",
  "capture_session_id",
  "run_id",
  "profile_url",
  "target_aweme_id",
  "source_video_external_id",
  "started_at",
  "page",
  "capture_context",
  "items",
  "progress",
  "commit_policy"
]);
const FULL_MODAL_ALLOWED_CALLERS = new Set(["whole_profile_staged_harvest_v2_direct", "whole_profile_one_item_collect_save"]);
const FULL_MODAL_DISALLOWED_EXACT_KEYS = new Set([
  "diagnostics",
  "debug",
  "state",
  "runtime",
  "capture_session_source",
  "session_source",
  "source_secret",
  "token",
  "api_key",
  "cookie",
  "authorization",
  "password"
]);
const FULL_MODAL_SECRET_LIKE_KEY = /(token|api[_-]?key|cookie|authorization|password|secret|session_source|capture_session_source)/i;

export type ExtensionBackendErrorCode =
  | "backend_unreachable"
  | "cors_or_permission_blocked"
  | "request_timeout"
  | "capture_session_not_found"
  | "capture_session_profile_mismatch"
  | "http_422_schema_error"
  | "http_500_server_error"
  | "http_4xx_client_error"
  | "auth_required"
  | "network_failed";

export type ExtensionBackendHealthResult = {
  ok: boolean;
  url: string;
  status_code: number | null;
  error_code?: ExtensionBackendErrorCode | null;
  error_message?: string | null;
};

export type ExtensionBackendPostResult = ExtensionBackendPostResponse & {
  error_code?: ExtensionBackendErrorCode | null;
  retryable?: boolean;
};

export const EXTENSION_BACKEND_TIMEOUT_MS = 15_000;

export async function checkBackendHealth(baseUrl: string, timeoutMs = 4_000): Promise<ExtensionBackendHealthResult> {
  const url = buildBackendUrl(baseUrl, "/openapi.json");
  try {
    const response = await withTimeout(fetch(url, { method: "GET" }), timeoutMs);
    if (!response.ok) {
      const classification = classifyFetchError(null, response);
      return { ok: false, url, status_code: response.status, error_code: classification.code, error_message: `Backend health failed: ${response.status}` };
    }
    return { ok: true, url, status_code: response.status, error_code: null, error_message: null };
  } catch (error) {
    const classification = classifyFetchError(error);
    return { ok: false, url, status_code: null, error_code: classification.code, error_message: classification.message };
  }
}

export function guardFullModalHarvestRequestBody(body: unknown, context: FullModalHarvestGuardContext): FullModalHarvestGuardResult {
  const offendingPaths = findFullModalHarvestDisallowedPaths(body);
  const caller = context.caller || "unknown";
  if (context.requireV2 !== false && !FULL_MODAL_ALLOWED_CALLERS.has(caller)) {
    offendingPaths.push(`caller:${caller}`);
  }
  if (!context.finalRequestBodyPreview) {
    offendingPaths.push("final_request_body_preview_missing");
  }
  if (!context.finalRequestFingerprint) {
    offendingPaths.push("final_request_fingerprint_missing");
  }
  if (typeof body !== "object" || body === null || Array.isArray(body)) {
    offendingPaths.push("body");
  } else {
    for (const key of Object.keys(body as Record<string, unknown>)) {
      if (!FULL_MODAL_ALLOWED_TOP_LEVEL_KEYS.has(key)) offendingPaths.push(key);
    }
  }
  if (offendingPaths.length > 0) {
    throw new Error(`payload_contains_disallowed_field_local: ${Array.from(new Set(offendingPaths)).join(",")}`);
  }
  return { ok: true, offending_paths: [] };
}

export async function postBackendJson(request: ExtensionBackendPostRequest, timeoutMs = EXTENSION_BACKEND_TIMEOUT_MS, fullModalGuardContext?: FullModalHarvestGuardContext): Promise<ExtensionBackendPostResult> {
  const url = buildBackendUrl(request.base_url, request.path);
  const method = request.method ?? "POST";
  try {
    if (method === "POST" && request.path.replace(/^\/+/, "/") === FULL_MODAL_HARVEST_PATH) {
      guardFullModalHarvestRequestBody(request.payload, fullModalGuardContext ?? inferFullModalHarvestGuardContext(request.payload, request.headers));
    }
    const init: RequestInit = {
      method,
      headers: method === "POST" ? { "Content-Type": "application/json", ...(request.headers ?? {}) } : { ...(request.headers ?? {}) },
      keepalive: request.keepalive ?? false
    };
    if (method === "POST") init.body = JSON.stringify(request.payload);
    const response = await withTimeout(fetch(url, init), timeoutMs);
    const body = await readJsonBody(response);
    if (!response.ok) {
      const classification = classifyBackendResponseError(response, body);
      return {
        ok: false,
        url,
        status_code: response.status,
        body,
        error_code: classification.code,
        retryable: classification.retryable,
        error_message: extractBackendErrorMessage(response.status, body, classification.code)
      };
    }
    return { ok: true, url, status_code: response.status, body, error_code: null, retryable: false };
  } catch (error) {
    const health = await checkBackendHealth(request.base_url).catch(() => null);
    const classification = classifyFetchError(error, undefined, health?.ok ?? false);
    const code = health && !health.ok ? "backend_unreachable" : classification.code;
    return {
      ok: false,
      url,
      status_code: null,
      error_code: code,
      retryable: true,
      error_message: code === "backend_unreachable" ? "backend_unreachable: backend health check failed before flush response" : classification.message
    };
  }
}

function inferFullModalHarvestGuardContext(payload: unknown, headers: Record<string, string> | undefined): FullModalHarvestGuardContext {
  const flushPath = headers?.["X-Reup-Douyin-Flush-Path"] ?? headers?.["x-reup-douyin-flush-path"] ?? "";
  const caller = flushPath === "canonical-whole-profile-harvest-one-item" || flushPath === "canonical-whole-profile-harvest" || flushPath === "hybrid-network-cache"
    ? "whole_profile_one_item_collect_save"
    : "unknown";
  return {
    caller,
    requireV2: caller === "unknown",
    finalRequestFingerprint: fingerprintPayload(payload),
    finalRequestBodyPreview: previewPayload(payload)
  };
}

function fingerprintPayload(payload: unknown): string | null {
  try {
    const text = JSON.stringify(payload);
    return `${text.length}:${text.slice(0, 80)}`;
  } catch {
    return null;
  }
}

function previewPayload(payload: unknown): Record<string, unknown> | null {
  return summarizeFullModalHarvestRequestForDiagnostics(payload);
}

export function summarizeFullModalHarvestRequestForDiagnostics(payload: unknown): FullModalHarvestRequestDiagnostics {
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) return { request_shape: "invalid_or_non_object" };
  const body = payload as Record<string, unknown>;
  const items = Array.isArray(body.items) ? body.items : [];
  const firstItem = items.length > 0 && items[0] && typeof items[0] === "object" && !Array.isArray(items[0]) ? items[0] as Record<string, unknown> : null;
  const rawMetrics = firstItem?.raw_dom_detail_metrics && typeof firstItem.raw_dom_detail_metrics === "object" && !Array.isArray(firstItem.raw_dom_detail_metrics) ? firstItem.raw_dom_detail_metrics as Record<string, unknown> : null;
  const captureSessionId = typeof body.capture_session_id === "string" ? body.capture_session_id : null;
  const durationSeconds = rawMetrics?.duration_seconds;
  return {
    schema_version: body.schema_version ?? null,
    capture_session_id_valid_uuid: typeof captureSessionId === "string" ? /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(captureSessionId) : false,
    capture_session_id: captureSessionId ? `${captureSessionId.slice(0, 8)}…${captureSessionId.slice(-4)}` : null,
    item_count: items.length,
    first_item_keys: firstItem ? Object.keys(firstItem).filter((key) => !isSecretLikeDiagnosticKey(key)).sort() : [],
    first_item_aweme_id_present: Boolean(typeof firstItem?.aweme_id === "string" && firstItem.aweme_id.trim()),
    first_item_source_video_external_id_present: Boolean(typeof firstItem?.source_video_external_id === "string" && firstItem.source_video_external_id.trim()),
    duration_seconds_present: durationSeconds !== undefined && durationSeconds !== null,
    duration_seconds_type: durationSeconds === null ? "null" : typeof durationSeconds,
    duration_seconds_value_category: typeof durationSeconds === "number" ? (durationSeconds > 0 ? "positive" : durationSeconds === 0 ? "zero" : "negative") : "non_numeric",
    source_url_present: Boolean(typeof firstItem?.source_url === "string" && firstItem.source_url.trim()),
    posted_at_present: Boolean(typeof rawMetrics?.posted_at === "string" && rawMetrics.posted_at.trim()),
    posted_at_type: rawMetrics?.posted_at === null ? "null" : typeof rawMetrics?.posted_at,
    posted_at_parseable: Boolean(typeof rawMetrics?.posted_at === "string" && !Number.isNaN(Date.parse(rawMetrics.posted_at))),
    metric_count_fields: {
      like_count: fieldPresenceType(rawMetrics, "like_count"),
      comment_count: fieldPresenceType(rawMetrics, "comment_count"),
      favorite_count: fieldPresenceType(rawMetrics, "favorite_count"),
      share_count: fieldPresenceType(rawMetrics, "share_count")
    },
    commit_policy: body.commit_policy ?? null,
    target_aweme_id_present: Boolean(typeof body.target_aweme_id === "string" && body.target_aweme_id.trim()),
    source_video_external_id_present: Boolean(typeof body.source_video_external_id === "string" && body.source_video_external_id.trim()),
    request_shape: "full_modal_harvest_v1"
  };
}

export function summarizeFullModalHarvestResponseForDiagnostics(response: ExtensionBackendPostResult | null | undefined): FullModalHarvestResponseDiagnostics {
  if (!response) return { response_summary_status: "missing" };
  const body = response.body;
  const bodyRecord = body && typeof body === "object" && !Array.isArray(body) ? body as Record<string, unknown> : null;
  const detailValue = bodyRecord?.detail;
  const detailRecord = detailValue && typeof detailValue === "object" && !Array.isArray(detailValue) ? detailValue as Record<string, unknown> : null;
  const validationErrors = Array.isArray(detailValue)
    ? detailValue.filter((entry): entry is Record<string, unknown> => Boolean(entry) && typeof entry === "object" && !Array.isArray(entry))
    : [];
  return {
    response_summary_status: response.ok ? "ok" : "error",
    http_status: response.status_code,
    backend_code: typeof detailRecord?.code === "string" ? detailRecord.code : typeof bodyRecord?.code === "string" ? bodyRecord.code : response.error_code ?? null,
    backend_stage: typeof detailRecord?.stage === "string" ? detailRecord.stage : typeof bodyRecord?.stage === "string" ? bodyRecord.stage : null,
    backend_message: typeof detailRecord?.message === "string" ? detailRecord.message : typeof bodyRecord?.message === "string" ? bodyRecord.message : typeof detailValue === "string" ? detailValue : response.error_message ?? null,
    backend_detail: typeof detailValue === "string" ? detailValue : null,
    validation_error_paths: validationErrors.map((entry) => entry.loc).filter((loc): loc is unknown => typeof loc !== "undefined"),
    response_json_parse_status: body ? "json_parsed" : response.status_code === null ? "no_response" : "json_unavailable_or_invalid",
    response_text_parse_status: "not_read_to_avoid_raw_body_storage",
    error_code: response.error_code ?? null,
    retryable: response.retryable ?? null,
    response_body_keys: bodyRecord ? Object.keys(bodyRecord).filter((key) => !isSecretLikeDiagnosticKey(key)).sort() : []
  };
}

function fieldPresenceType(value: Record<string, unknown> | null, key: string): { present: boolean; type: string } {
  if (!value || typeof value[key] === "undefined") return { present: false, type: "undefined" };
  return { present: true, type: value[key] === null ? "null" : typeof value[key] };
}

function isSecretLikeDiagnosticKey(key: string): boolean {
  return /cookie|authorization|auth|token|csrf|password|credential|secret|api[_-]?key|headers|raw_html|raw_dom/i.test(key);
}

function classifyBackendResponseError(response: Response, body: Record<string, unknown> | null): { code: ExtensionBackendErrorCode; retryable: boolean; message: string } {
  const detail = body?.detail;
  const detailRecord = detail && typeof detail === "object" && !Array.isArray(detail) ? detail as Record<string, unknown> : null;
  const backendCode = typeof detailRecord?.code === "string" ? detailRecord.code : typeof body?.code === "string" ? body.code : null;
  if (response.status === 422 && backendCode === "capture_session_not_found") return { code: "capture_session_not_found", retryable: false, message: "capture_session_not_found" };
  if (response.status === 422 && backendCode === "capture_session_profile_mismatch") return { code: "capture_session_profile_mismatch", retryable: false, message: "capture_session_profile_mismatch" };
  return classifyFetchError(null, response);
}

export function classifyFetchError(error: unknown, response?: Response | null, healthOk = false): { code: ExtensionBackendErrorCode; retryable: boolean; message: string } {
  if (response) {
    // 401/403 means the operator's session is missing or expired. Long-running flows must pause and re-auth instead of
    // silently producing false "not found" results, so emit a dedicated auth_required code that callers can surface
    // explicitly. Not retryable without operator action.
    if (response.status === 401 || response.status === 403) return { code: "auth_required", retryable: false, message: `auth_required: http_${response.status}` };
    if (response.status === 422) return { code: "http_422_schema_error", retryable: false, message: "http_422_schema_error" };
    if (response.status >= 500) return { code: "http_500_server_error", retryable: true, message: "http_500_server_error" };
    if (response.status >= 400) return { code: "http_4xx_client_error", retryable: false, message: "http_4xx_client_error" };
  }
  if (error instanceof DOMException && error.name === "AbortError") return { code: "request_timeout", retryable: true, message: "request_timeout" };
  const message = error instanceof Error ? error.message : String(error ?? "network_failed");
  if (/permission|host permission|access to fetch|cors/i.test(message)) return { code: "cors_or_permission_blocked", retryable: true, message: `cors_or_permission_blocked: ${message}` };
  if (healthOk && /failed to fetch|network/i.test(message)) return { code: "cors_or_permission_blocked", retryable: true, message: `cors_or_permission_blocked: ${message}` };
  if (/failed to fetch|network/i.test(message)) return { code: "network_failed", retryable: true, message: `network_failed: ${message}` };
  return { code: "network_failed", retryable: true, message };
}

export async function withTimeout<T>(operation: Promise<T>, timeoutMs: number): Promise<T> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await Promise.race([
      operation,
      new Promise<T>((_, reject) => {
        controller.signal.addEventListener("abort", () => reject(new DOMException("Request timed out", "AbortError")), { once: true });
      })
    ]);
  } finally {
    clearTimeout(timeout);
  }
}

export function buildBackendUrl(baseUrl: string, path: string): string {
  const base = baseUrl.replace(/\/+$/, "");
  const normalizedPath = path.startsWith("/") ? path : `/${path}`;
  return `${base}${normalizedPath}`;
}

function findFullModalHarvestDisallowedPaths(value: unknown, basePath = ""): string[] {
  const out: string[] = [];
  if (Array.isArray(value)) {
    value.forEach((entry, index) => out.push(...findFullModalHarvestDisallowedPaths(entry, `${basePath}[${index}]`)));
    return out;
  }
  if (!value || typeof value !== "object") return out;
  for (const [key, child] of Object.entries(value as Record<string, unknown>)) {
    const path = basePath ? `${basePath}.${key}` : key;
    if (FULL_MODAL_DISALLOWED_EXACT_KEYS.has(key) || FULL_MODAL_SECRET_LIKE_KEY.test(key)) {
      out.push(path);
      continue;
    }
    out.push(...findFullModalHarvestDisallowedPaths(child, path));
  }
  return out;
}

async function readJsonBody(response: Response): Promise<Record<string, unknown> | null> {
  try {
    return (await response.json()) as Record<string, unknown>;
  } catch {
    return null;
  }
}

function extractBackendErrorMessage(status: number, body: Record<string, unknown> | null, code: ExtensionBackendErrorCode): string {
  const suffix = body ? `; body: ${JSON.stringify(body)}` : "";
  return `${code}: Backend request failed: ${status}${suffix}`;
}
