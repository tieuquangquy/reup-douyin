import assert from "node:assert/strict";

import { guardFullModalHarvestRequestBody, postBackendJson, summarizeFullModalHarvestRequestForDiagnostics, summarizeFullModalHarvestResponseForDiagnostics } from "./extensionBackendClient.js";
import type { FullModalHarvestRequestPayload } from "./types.js";

const basePayload: FullModalHarvestRequestPayload = {
  schema_version: "douyin_full_modal_harvest.v1",
  capture_session_id: "session-phase17ae-fixture",
  run_id: "run-phase17ae-fixture",
  profile_url: "https://www.douyin.com/user/test",
  target_aweme_id: "1234567890",
  source_video_external_id: "1234567890",
  started_at: "2026-05-05T07:00:00.000Z",
  page: {
    page_type: "video_detail_page",
    url: "https://www.douyin.com/user/test?modal_id=1234567890",
    title: null,
    profile_url: "https://www.douyin.com/user/test",
    video_link_count: 1
  },
  capture_context: {
    capture_id: "run-phase17ae-fixture",
    page_url: "https://www.douyin.com/user/test?modal_id=1234567890",
    captured_at: "2026-05-05T07:00:01.000Z",
    profile_url: "https://www.douyin.com/user/test"
  },
  items: [
    {
      aweme_id: "1234567890",
      target_aweme_id: "1234567890",
      source_video_external_id: "1234567890",
      source_url: "https://www.douyin.com/user/test?modal_id=1234567890",
      page_url: "https://www.douyin.com/user/test?modal_id=1234567890",
      modal_id: "1234567890",
      raw_dom_detail_metrics: {
        aweme_id: "1234567890",
        target_aweme_id: "1234567890",
        duration_seconds: 12,
        duration_text: "00:12",
        like_count: 10,
        comment_count: 2,
        favorite_count: 3,
        share_count: 1,
        extraction_source: "calibrated_point_dom",
        source_used: "calibrated_point_dom",
        confidence: "high"
      },
      raw_evidence_summary: {
        has_network_aweme: false,
        has_detail_aweme: false,
        has_dom_snapshot: false,
        has_dom_detail_metrics: true,
        network_keys: [],
        detail_keys: [],
        dom_detail_metric_keys: ["duration_seconds", "like_count", "comment_count", "favorite_count", "share_count"],
        evidence_sources: ["whole_profile_staged_harvest_v2"],
        evidence_collection_version: "phase11a_production_stabilized_calibrated_harvest"
      },
      profile_card_evidence: null,
      modal_aweme_id_before_extract: "1234567890",
      modal_aweme_id_after_extract: "1234567890",
      extracted_aweme_id: "1234567890",
      data_integrity_status: "passed",
      data_integrity_reason: null,
      metric_signature: null,
      duplicate_signature_warning: null
    }
  ],
  progress: {
    running: false,
    current_state: "completed",
    phase: "completed",
    target_count: 1,
    current_index: 1,
    current_aweme_id: "1234567890",
    harvested_count: 1,
    updated_count: 1,
    pending_count: 0,
    duplicate_count: 0,
    failed_count: 0,
    flushed_count: 1,
    last_error: null,
    stopped_reason: "completed",
    last_flush_status: "success",
    next_flush_in_items: 0
  },
  commit_policy: "finalized_only"
};

const validContext = {
  caller: "whole_profile_staged_harvest_v2_direct",
  requireV2: true,
  finalRequestBodyPreview: { schema_version: basePayload.schema_version, items_count: 1 },
  finalRequestFingerprint: "v2fp_fixture"
};

assert.deepEqual(guardFullModalHarvestRequestBody(basePayload, validContext), { ok: true, offending_paths: [] });

const basePayloadItem = basePayload.items[0];
assert.ok(basePayloadItem);
const requestDiagnostics = summarizeFullModalHarvestRequestForDiagnostics({
  ...basePayload,
  cookie: "must_not_be_exposed",
  items: [{ ...basePayloadItem, token: "must_not_be_exposed", raw_dom_detail_metrics: { ...basePayloadItem.raw_dom_detail_metrics, posted_at: "2026-05-05T06:58:00.000Z" } }]
});
assert.equal(requestDiagnostics.schema_version, "douyin_full_modal_harvest.v1");
assert.equal(requestDiagnostics.capture_session_id_valid_uuid, false);
assert.equal(requestDiagnostics.capture_session_id, "session-…ture");
assert.equal(requestDiagnostics.item_count, 1);
assert.equal(requestDiagnostics.first_item_aweme_id_present, true);
assert.equal(requestDiagnostics.duration_seconds_value_category, "positive");
assert.equal(requestDiagnostics.posted_at_parseable, true);
assert.deepEqual(requestDiagnostics.metric_count_fields, {
  like_count: { present: true, type: "number" },
  comment_count: { present: true, type: "number" },
  favorite_count: { present: true, type: "number" },
  share_count: { present: true, type: "number" }
});
assert.equal((requestDiagnostics.first_item_keys as string[]).includes("token"), false);
assert.equal(Object.keys(requestDiagnostics).includes("cookie"), false);

const responseDiagnostics = summarizeFullModalHarvestResponseForDiagnostics({
  ok: false,
  url: "http://127.0.0.1:8000/douyin-extension/full-modal-harvest",
  status_code: 422,
  body: { detail: [{ loc: ["body", "items", 0, "raw_dom_detail_metrics", "duration_seconds"], msg: "Input should be a valid number", type: "float_parsing" }] },
  error_code: "http_422_schema_error",
  retryable: false,
  error_message: "http_422_schema_error"
});
assert.equal(responseDiagnostics.http_status, 422);
assert.equal(responseDiagnostics.backend_code, "http_422_schema_error");
assert.deepEqual(responseDiagnostics.validation_error_paths, [["body", "items", 0, "raw_dom_detail_metrics", "duration_seconds"]]);
assert.equal(responseDiagnostics.response_json_parse_status, "json_parsed");
assert.equal(JSON.stringify(responseDiagnostics).includes("Input should be a valid number"), false, "response diagnostics must not store raw validation messages");

const semanticSessionDiagnostics = summarizeFullModalHarvestResponseForDiagnostics({
  ok: false,
  url: "http://127.0.0.1:8000/douyin-extension/full-modal-harvest",
  status_code: 422,
  body: {
    detail: {
      code: "capture_session_not_found",
      stage: "resolve_capture_session",
      message: "Explicit Capture Inbox session profile does not match the full modal harvest payload."
    }
  },
  error_code: "capture_session_not_found",
  retryable: false,
  error_message: "capture_session_not_found"
});
assert.equal(semanticSessionDiagnostics.http_status, 422);
assert.equal(semanticSessionDiagnostics.backend_code, "capture_session_not_found");
assert.equal(semanticSessionDiagnostics.backend_stage, "resolve_capture_session");
assert.equal(semanticSessionDiagnostics.error_code, "capture_session_not_found");
assert.deepEqual(semanticSessionDiagnostics.validation_error_paths, []);
assert.equal(JSON.stringify(semanticSessionDiagnostics).includes("Explicit Capture Inbox session profile does not match"), true, "semantic backend message should be visible without storing raw response bodies");

assert.throws(
  () => guardFullModalHarvestRequestBody({ ...basePayload, diagnostics: { leaked: true } }, validContext),
  /payload_contains_disallowed_field_local: diagnostics/,
  "guard must block diagnostics at top level"
);

assert.throws(
  () => guardFullModalHarvestRequestBody({ ...basePayload, items: [{ ...basePayload.items[0], debug: { leaked: true } }] }, validContext),
  /items\[0\]\.debug/,
  "guard must block nested debug fields"
);

assert.throws(
  () => guardFullModalHarvestRequestBody(basePayload, { ...validContext, caller: "content_script_runtime_flush" }),
  /caller:content_script_runtime_flush/,
  "guard must block non-V2 full-modal callers"
);

assert.throws(
  () => guardFullModalHarvestRequestBody(basePayload, { ...validContext, finalRequestBodyPreview: null }),
  /final_request_body_preview_missing/,
  "guard must require final request body preview"
);

assert.throws(
  () => guardFullModalHarvestRequestBody(basePayload, { ...validContext, finalRequestFingerprint: null }),
  /final_request_fingerprint_missing/,
  "guard must require final request fingerprint"
);

const originalFetch = globalThis.fetch;
let lastFetchInit: RequestInit | undefined;
globalThis.fetch = (async (_input: RequestInfo | URL, init?: RequestInit) => {
  lastFetchInit = init;
  return new Response(JSON.stringify({ ok: true }), { status: 200, headers: { "Content-Type": "application/json" } });
}) as typeof fetch;
try {
  const getResult = await postBackendJson({ base_url: "http://127.0.0.1:8000", path: "/douyin-extension/capture-sessions/session_1/items", method: "GET" });
  assert.equal(getResult.ok, true);
  assert.equal(lastFetchInit?.method, "GET", "session item verification must use GET through the backend bridge");
  assert.equal("body" in (lastFetchInit ?? {}), false, "GET verification requests must not send a JSON body");
} finally {
  globalThis.fetch = originalFetch;
}

globalThis.fetch = (async () => new Response(JSON.stringify({
  detail: {
    code: "capture_session_not_found",
    stage: "resolve_capture_session",
    message: "Explicit Capture Inbox session profile does not match the full modal harvest payload."
  }
}), { status: 422, headers: { "Content-Type": "application/json" } })) as typeof fetch;
try {
  const semanticResult = await postBackendJson({ base_url: "http://127.0.0.1:8000", path: "/douyin-extension/full-modal-harvest", method: "POST", payload: basePayload }, 4_000, validContext);
  assert.equal(semanticResult.ok, false);
  assert.equal(semanticResult.status_code, 422);
  assert.equal(semanticResult.error_code, "capture_session_not_found", "semantic capture-session 422 must not be collapsed into schema rejection");
  const semanticResultDiagnostics = summarizeFullModalHarvestResponseForDiagnostics(semanticResult);
  assert.equal(semanticResultDiagnostics.backend_code, "capture_session_not_found");
  assert.equal(semanticResultDiagnostics.backend_stage, "resolve_capture_session");
} finally {
  globalThis.fetch = originalFetch;
}

globalThis.fetch = (async () => new Response(JSON.stringify({ detail: [{ loc: ["body", "items", 0, "raw_dom_detail_metrics", "duration_seconds"], msg: "Input should be a valid number", type: "float_parsing" }] }), { status: 422, headers: { "Content-Type": "application/json" } })) as typeof fetch;
try {
  const schemaResult = await postBackendJson({ base_url: "http://127.0.0.1:8000", path: "/douyin-extension/full-modal-harvest", method: "POST", payload: basePayload }, 4_000, validContext);
  assert.equal(schemaResult.ok, false);
  assert.equal(schemaResult.error_code, "http_422_schema_error", "Pydantic validation-array 422 should remain a schema rejection");
} finally {
  globalThis.fetch = originalFetch;
}

console.log("extension backend full-modal guard tests passed");
