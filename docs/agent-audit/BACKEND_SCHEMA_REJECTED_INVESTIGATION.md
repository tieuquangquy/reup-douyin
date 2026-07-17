# Backend Schema Rejected Investigation

Phase: 3A backend schema rejected investigation only.

Date: 2026-05-15.

## Scope and non-goals

This investigation traces the Start Collecting one-item flush path that produced `backend_schema_rejected` in the live extension state.

Runtime behavior was not changed. Scanner, auto-scroll, calibration, queue finalization, backend schema, migrations, payload guard, web UI, and persistence code remain unchanged.

Auto-scroll discovery is treated as already fixed and was not investigated here.

## Source files inspected

- `apps/extension-douyin-capture/src/popup.ts`
- `apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts`
- `apps/extension-douyin-capture/src/wholeProfileHarvest/canonicalHarvest.ts`
- `apps/extension-douyin-capture/src/extensionBackendClient.ts`
- `apps/extension-douyin-capture/src/types.ts`
- `apps/api/src/api/routes/douyin_extension.py`
- `apps/api/src/schemas/douyin_extension.py`
- `apps/api/src/services/douyin_extension_capture_service.py`
- `apps/api/src/services/capture_inbox_service.py`
- `apps/api/src/models/capture_inbox.py`
- `apps/api/tests/test_douyin_extension_routes.py`
- `apps/api/tests/test_douyin_extension_capture_service.py`

## Exact trace

### 1. Start Collecting action

The popup Start Collecting handler is `runWholeProfileHarvestProductFromPopup()` in `apps/extension-douyin-capture/src/popup.ts`.

Observed flow:

1. Stops right-rail calibration mode before collection by sending `REUP_DOUYIN_STOP_RIGHT_RAIL_CALIBRATION`.
2. Reads selected whole-profile options.
3. Persists harvest options through `updateHarvestOptions()`.
4. Converts UI batch selection into a `batch_limit`.
5. Calls `runStartCollectingWorkflow(createWholeProfilePopupRuntime(), ...)` through `runWholeProfileControllerAction()`.

This confirms Start Collecting is not the Scan Profile or auto-scroll path. It enters the whole-profile controller collection workflow.

### 2. One-item collection/extraction output

`runStartCollectingWorkflow()` delegates to `runRealModalExtractionHarvest()` and then to `runOneItemCollectAndSave()` for one-item/safe collection.

The one-item flow:

1. Reconciles the queue and validates Scan Profile, calibration, and backend session readiness.
2. Opens the target modal.
3. Extracts modal metrics using `runExtractionWithTimeout()`.
4. Builds `FinalizedModalMetadata` through `buildItemScopedFinalizedMetadata()`.
5. Builds a full-modal Capture Inbox payload through `buildCaptureInboxItemPayload()`.
6. Sanitizes/normalizes that payload through `buildCleanCaptureInboxItemPayload()`.
7. Runs local secret and Capture Inbox payload guards.
8. Calls `flushOneCanonicalHarvestPayload()`.

The local controller-required metric rule accepts either `duration_seconds` or `duration_text`, plus non-null `like_count`, `comment_count`, `favorite_count`, and `share_count`.

### 3. Payload builder for one item

`buildCaptureInboxItemPayload()` in `apps/extension-douyin-capture/src/wholeProfileHarvest/canonicalHarvest.ts` builds a `FullModalHarvestRequestPayload`, not a legacy single-item body.

Static one-item payload shape:

```json
{
  "schema_version": "douyin_full_modal_harvest.v1",
  "capture_session_id": "<uuid string from backend session>",
  "run_id": "<run id or null>",
  "profile_url": "<profile url>",
  "target_aweme_id": "<aweme id>",
  "source_video_external_id": "<aweme id>",
  "started_at": "<ISO datetime>",
  "page": {
    "page_type": "video_detail_page",
    "url": "https://www.douyin.com/video/<aweme id>",
    "title": null,
    "profile_url": "<profile url>",
    "video_link_count": 1
  },
  "capture_context": {
    "capture_id": "<run id or one_item_smoke_test id>",
    "page_url": "https://www.douyin.com/video/<aweme id>",
    "captured_at": "<ISO datetime>",
    "profile_url": "<profile url>"
  },
  "items": [
    {
      "aweme_id": "<aweme id>",
      "target_aweme_id": "<aweme id>",
      "source_video_external_id": "<aweme id>",
      "metadata_status": "ready or needs_metadata",
      "review_status": "pending_review",
      "source_url": "https://www.douyin.com/video/<aweme id>",
      "page_url": "https://www.douyin.com/video/<aweme id>",
      "modal_id": "<aweme id>",
      "raw_dom_detail_metrics": {
        "aweme_id": "<aweme id>",
        "target_aweme_id": "<aweme id>",
        "duration_seconds": "<number or null>",
        "duration_text": "<string or null>",
        "selected_duration_source": "<string or null>",
        "duration_raw": "<number or null>",
        "duration_validation_result": "<string or null>",
        "duration_candidate_list": [],
        "like_count": "<number>",
        "comment_count": "<number>",
        "favorite_count": "<number>",
        "share_count": "<number>",
        "posted_text": "<string or null>",
        "posted_text_raw": "<string or null>",
        "posted_at": "<string or null>",
        "posted_display": "<string or null>",
        "posted_source": "<string or null>",
        "posted_parse_confidence": "<string or null>",
        "posted_parser_pattern_matched": "<string or null>",
        "posted_reference_time": "<string or null>",
        "posted_timezone": "<string or null>",
        "thumbnail_url": "<string or null>",
        "caption": "<string or null>",
        "extraction_source": "calibrated_point_dom",
        "source_used": "<string or calibrated_point_dom>",
        "confidence": "high"
      },
      "raw_evidence_summary": {
        "has_network_aweme": false,
        "has_detail_aweme": false,
        "has_dom_snapshot": false,
        "has_dom_detail_metrics": true,
        "network_keys": [],
        "detail_keys": [],
        "dom_detail_metric_keys": ["duration_seconds", "duration_text", "like_count", "comment_count", "favorite_count", "share_count"],
        "evidence_sources": ["whole_profile_harvest", "one_item_smoke_test", "profile_card_evidence"],
        "evidence_collection_version": "phase11a_production_stabilized_calibrated_harvest"
      },
      "profile_card_evidence": {
        "aweme_id": "<aweme id>",
        "source_url": "<source url>",
        "title": "<string or null>",
        "caption": "<string or null>",
        "desc": "<string or null>",
        "description": "<string or null>",
        "thumbnail_url": "<string or null>",
        "cover_url": "<string or null>",
        "poster_url": "<string or null>",
        "posted_text": "<string or null>",
        "posted_text_raw": "<string or null>",
        "posted_at": "<string or null>",
        "posted_display": "<string or null>",
        "thumbnail_source": "<string or null>",
        "posted_source": "<string or null>",
        "posted_parse_confidence": "<string or null>"
      },
      "modal_aweme_id_before_extract": "<aweme id>",
      "modal_aweme_id_after_extract": "<aweme id>",
      "extracted_aweme_id": "<aweme id>",
      "data_integrity_status": "passed",
      "data_integrity_reason": null,
      "metric_signature": null,
      "duplicate_signature_warning": null
    }
  ],
  "progress": {
    "running": false,
    "current_state": "completed",
    "phase": "completed",
    "target_count": 1,
    "current_index": 1,
    "current_aweme_id": "<aweme id>",
    "harvested_count": 1,
    "updated_count": 1,
    "pending_count": 0,
    "duplicate_count": 0,
    "failed_count": 0,
    "flushed_count": 1,
    "last_error": null,
    "stopped_reason": "one_item_smoke_test_completed",
    "last_flush_status": "success",
    "next_flush_in_items": 0
  },
  "commit_policy": "finalized_only"
}
```

### 4. Local payload guard

The one-item path runs both local guards before sending:

- `guardNoSecretDebugLeakage(payload)` rejects secret/debug-like fields locally.
- `guardCaptureInboxPayload(payload)` checks allowed shape and required Capture Inbox fields.
- `flushOneCanonicalHarvestPayload()` runs `guardCaptureInboxPayload()` again before the runtime flush.
- `extensionBackendClient.ts` runs `guardFullModalHarvestRequestBody()` immediately before posting the backend request.

Local guard rejection would produce local errors such as `payload_contains_disallowed_field_local`, `backend_secret_guard_rejected`, or `payload_preview_missing`. It does not directly assign `backend_schema_rejected` unless an HTTP 422 is received from the backend and then classified by the controller.

Important local/backend mismatch found: the local guard accepts `duration_text` when `duration_seconds` is null, but backend `finalized_only` creation requires `duration_seconds > 0`. This is not a Pydantic 422 schema mismatch; it is a service-level finalization semantic mismatch. Current service code records a `finalized_metadata_required` failure summary and returns a normal response body rather than raising HTTP 422.

### 5. Request sent by extension backend client

The request path is `/douyin-extension/full-modal-harvest`.

The one-item headers are:

```json
{
  "X-Reup-Douyin-Flush-Path": "canonical-whole-profile-harvest-one-item",
  "X-Reup-Douyin-Run-Id": "<run id>",
  "X-Reup-Douyin-Target-Aweme-Id": "<aweme id>"
}
```

`popup.ts` sends a runtime message `REUP_DOUYIN_POST_BACKEND` with method `POST`, the full-modal payload, and those headers.

`extensionBackendClient.ts` maps raw HTTP status codes as follows:

- HTTP 422 -> `http_422_schema_error`, non-retryable.
- HTTP 5xx -> `http_500_server_error`, retryable.
- Other HTTP 4xx -> `http_4xx_client_error`, non-retryable.
- Network/cors/timeout cases map to network-specific error codes.

The popup runtime then returns `WholeProfileBackendFlushResult` with `status` set from `backendPost.status_code` when present.

### 6. API endpoint `/douyin-extension/full-modal-harvest`

The FastAPI route is `ingest_douyin_extension_full_modal_harvest()` in `apps/api/src/api/routes/douyin_extension.py`.

It accepts `DouyinExtensionFullModalHarvestRequest` and returns `DouyinExtensionFullModalHarvestResponse`.

If request-body Pydantic validation fails, FastAPI returns HTTP 422 before the route function runs. In that case there will be no `full_modal_harvest_received` service log.

If route parsing succeeds and the service raises `DouyinExtensionCaptureError`, the route logs `full_modal_harvest_error` and maps the error to HTTP 422 or HTTP 503 depending on error code.

### 7. Pydantic/schema validation

Backend expected top-level request shape in `DouyinExtensionFullModalHarvestRequest`:

- `schema_version`: literal `douyin_full_modal_harvest.v1`.
- `capture_session_id`: UUID or null.
- `capture_session_source`: optional string.
- `run_id`: optional string.
- `profile_url`: optional string.
- `target_aweme_id`: optional string.
- `source_video_external_id`: optional string.
- `started_at`: datetime, required.
- `page`: `DouyinExtensionPageSnapshot`, required.
- `capture_context`: `DouyinExtensionCaptureContextPayload`, required.
- `items`: list of `DouyinExtensionFullModalHarvestItemPayload`, default empty, max 500.
- `progress`: `DouyinExtensionFullModalHarvestProgress`, required.
- `diagnostics`: dict, default empty.
- `commit_policy`: `legacy_update_existing` or `finalized_only`.

Backend expected item shape includes required:

- `aweme_id`
- `raw_dom_detail_metrics`
- `raw_evidence_summary`

Backend expected raw metric fields include required:

- `extraction_source`: one of `dom_detail_modal`, `video_element_modal`, `calibrated_point_dom`, `calibrated_point_ocr`, `mixed_calibrated_point`.
- `confidence`: literal `high`.

Backend expected evidence version includes `phase11a_production_stabilized_calibrated_harvest`, so the static one-item builder value is accepted.

Backend expected `profile_card_evidence.aweme_id` is required if `profile_card_evidence` is present. The one-item builder supplies it.

Pydantic extra-field behavior: no custom `model_config` was found on these Douyin extension schemas. With Pydantic v2 default behavior, extra fields are ignored. Therefore extension-only `progress` extras such as `current_state`, `phase`, `current_index`, `pending_count`, `last_flush_status`, and `next_flush_in_items` should not cause a 422 unless project/global behavior differs outside these models.

### 8. Service validation/persistence

After Pydantic validation, `DouyinExtensionCaptureService.ingest_full_modal_harvest()`:

1. Dumps the request and rejects secret-like fields through `_reject_secret_payload()`.
2. Logs `full_modal_harvest_received`.
3. Resolves the capture session.
4. Iterates `request.items`.
5. Checks identity alignment across payload/item/raw metrics/modal ids.
6. For `finalized_only`, creates a missing Capture Inbox item only if `_is_finalized_modal_payload()` passes.
7. Applies modal harvest metrics to the item.
8. Returns a summary response.

Service-level `finalized_only` requirement for new/missing items:

- non-empty `payload.aweme_id`
- `payload.source_url` or `profile_card_evidence.source_url`
- `metrics.duration_seconds is not None and > 0`
- `metrics.like_count >= 0`
- `metrics.comment_count >= 0`
- `metrics.favorite_count >= 0`
- `metrics.share_count >= 0`

If this finalization check fails, the service adds `finalized_metadata_required` to `failure_summaries` and continues; it does not raise HTTP 422 in the inspected code.

Service errors that can become HTTP 422 include `DouyinExtensionCaptureError` codes not listed as HTTP 503. Examples from inspected source include secret payload rejection and explicit session/profile validation errors. Service errors will be visible as route log `full_modal_harvest_error` with `error_code`, `stage`, `diagnostics_id`, and `capture_session_id`.

### 9. Error classification into `backend_schema_rejected`

`backend_schema_rejected` is assigned in `apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts`.

One-item classification:

```ts
function classifyOneItemFlushError(response: WholeProfileBackendFlushResult): WholeProfileHarvestError {
  if (response.status === 404 || response.error_code === "capture_session_not_found") return wholeProfileHarvestError("capture_session_not_found", response);
  if (response.status === 422 && response.error_code === "extension_payload_contains_secret_field") return wholeProfileHarvestError("backend_secret_guard_rejected", response);
  if (response.status === 422 && response.error_code === "finalized_metadata_required") return wholeProfileHarvestError("backend_finalized_metadata_required", response);
  if (response.status === 422) return wholeProfileHarvestError("backend_schema_rejected", response);
  return wholeProfileHarvestError("backend_flush_failed", response);
}
```

Batch classification has the same general behavior: status 422 maps to `backend_schema_rejected` except known secret/finalized metadata cases.

This means live `backend_schema_rejected x 2` proves the extension believed the backend flush result had `status === 422` and did not have one of these explicit exception `error_code` values:

- `extension_payload_contains_secret_field`
- `finalized_metadata_required`

## Required alignment answers

### Where is `backend_schema_rejected` assigned?

In `classifyOneItemFlushError()` and `classifyBackendFlushError()` / batch classification in `apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts` when the flush result status is HTTP 422 and not one of the explicitly handled 422 cases.

### Which HTTP statuses/response bodies map to it?

HTTP 422 maps to `backend_schema_rejected` unless the response error code is recognized as:

- `extension_payload_contains_secret_field` -> `backend_secret_guard_rejected`
- `finalized_metadata_required` -> `backend_finalized_metadata_required`

HTTP 404 or `capture_session_not_found` maps to `capture_session_not_found`.

Other statuses map to `backend_flush_failed` or lower-level backend client error codes before classification.

### Exact extension one-item payload shape

The extension sends a `douyin_full_modal_harvest.v1` request with top-level `items: [item]`, `progress`, `page`, `capture_context`, `capture_session_id`, IDs, and `commit_policy: finalized_only`. The detailed static shape is shown above.

### Exact backend endpoint expected shape

The backend expects `DouyinExtensionFullModalHarvestRequest`, including required `started_at`, `page`, `capture_context`, `items` list, and `progress`. Each item requires `aweme_id`, `raw_dom_detail_metrics`, and `raw_evidence_summary`.

### Required fields alignment

Static source alignment is mostly correct:

- `schema_version` aligns.
- `capture_session_id` is required locally and accepted as UUID/null by backend.
- `started_at` is supplied.
- `page` is supplied.
- `capture_context` is supplied.
- `items` array is supplied.
- item `aweme_id` is supplied.
- `raw_dom_detail_metrics` is supplied.
- `raw_evidence_summary` is supplied.
- `profile_card_evidence.aweme_id` is supplied when profile card evidence is present.

Potential live-data validation risks that source inspection cannot rule out:

- `capture_session_id` in live Details is not a valid UUID string.
- `posted_at` inside `profile_card_evidence` is not parseable as backend datetime.
- `started_at` or `capture_context.captured_at` is malformed.
- actual live payload differs from the static builder because of stored state, sanitizer output, or stale extension build.

### Metric fields alignment

Static source alignment is correct for schema-level metrics:

- `duration_seconds` and `duration_text` are allowed nullable backend fields.
- `like_count`, `comment_count`, `favorite_count`, and `share_count` are allowed nullable backend fields.
- `extraction_source: calibrated_point_dom` is accepted by backend schema.
- `confidence: high` is accepted by backend schema.

Semantic mismatch found:

- Extension local guard allows `duration_text` if `duration_seconds` is null.
- Backend `finalized_only` item creation requires `duration_seconds > 0` for missing/new Capture Inbox items.
- This semantic mismatch should produce a non-success service response/failure summary, not a Pydantic 422, based on inspected service code.

### ID alignment

Static one-item builder aligns all primary IDs to the target aweme id:

- top-level `target_aweme_id`
- top-level `source_video_external_id`
- item `aweme_id`
- item `target_aweme_id`
- item `source_video_external_id`
- item `modal_id`
- item `modal_aweme_id_before_extract`
- item `modal_aweme_id_after_extract`
- item `extracted_aweme_id`
- raw metrics `aweme_id`
- raw metrics `target_aweme_id`
- `profile_card_evidence.aweme_id`

The backend service explicitly treats mismatches across these fields as `data_integrity_mismatch` failure summaries, not HTTP 422, unless another validation error occurs first.

### Duration requirement/availability

Extension local commit guard requires either `duration_seconds` or `duration_text`.

Backend finalized creation requires `duration_seconds > 0` when no existing Capture Inbox row is matched and `commit_policy` is `finalized_only`.

Therefore the next live Details payload must confirm whether `items[0].raw_dom_detail_metrics.duration_seconds` is a positive number.

### Whether backend requires `items` array or extension sends single item differently

Backend requires/accepts an `items` list. The extension sends `items: [item]`. There is no static mismatch here.

### Whether `finalized_only` rejects partial/in-progress items

`finalized_only` rejects non-finalized new/missing items at service logic by adding `finalized_metadata_required` to `failure_summaries` and not creating the item. In inspected code, this does not raise HTTP 422 by itself.

### Whether rejection is FastAPI/Pydantic or service layer

Source inspection cannot determine the live rejection layer without the actual response body or API logs.

Decision rule:

- If API logs do not show `full_modal_harvest_received`, the rejection is FastAPI/Pydantic validation before service entry.
- If API logs show `full_modal_harvest_received` followed by `full_modal_harvest_error`, the rejection is service-layer `DouyinExtensionCaptureError` mapped by the route.
- If API logs show `full_modal_harvest_received` and `douyin_extension_full_modal_harvest_ingested`, the backend accepted the schema; the extension may be classifying another HTTP 422 from a different/older request or the visible Details summary may be stale/incomplete.

### Whether API logging is enough

Current API logging is enough to distinguish Pydantic-vs-service only if logs are visible:

- Pydantic 422: access log 422, no `full_modal_harvest_received`.
- Service 422: `full_modal_harvest_error` with structured detail.
- Accepted schema: `full_modal_harvest_received` and `douyin_extension_full_modal_harvest_ingested`.

API logging is not enough to identify exact Pydantic field paths unless the HTTP 422 response body is copied. FastAPI validation errors include `detail[*].loc`, `detail[*].msg`, and `detail[*].type`; those are required for the exact schema field failure.

## Most likely cause candidates from source inspection

No definitive static schema mismatch was found in the current one-item builder versus backend schema.

Strong candidates requiring live Details/API logs:

1. Live `capture_session_id` is missing or not a UUID string. Local guard only checks presence; backend parses it as UUID.
2. Live `profile_card_evidence.posted_at` is present but not parseable as Python datetime. Extension type allows arbitrary string; backend schema parses it as `datetime | None`.
3. Live `started_at`, `page`, or `capture_context` contains a malformed or null value after stale-state/sanitizer effects.
4. Live payload is from a stale extension build or legacy path and differs from `buildCaptureInboxItemPayload()` output inspected here.
5. Service-layer `DouyinExtensionCaptureError` returns 422 with an unrecognized error code; controller collapses that to `backend_schema_rejected` because only two 422 error codes are special-cased.

The previously suspected `evidence_collection_version` mismatch is not supported by current backend schema; `phase11a_production_stabilized_calibrated_harvest` is accepted.

The extra `progress` fields are unlikely to be the cause under Pydantic v2 defaults because these models do not configure `extra="forbid"`.

## Exact Details/API logs to copy next

Copy only redacted payloads. Do not include cookies, tokens, authorization headers, private local paths, or raw browser storage dumps.

From popup Details, copy these fields for one failed item:

- `debug.last_request_summary.stage`
- `debug.last_request_summary.url`
- `debug.last_request_summary.headers` with secret-like values removed
- `debug.last_request_summary.body_preview`
- `debug.last_request_summary.payload_aweme`
- `debug.last_request_summary.payload_required_fields`
- `debug.last_request_summary.current_aweme`
- `debug.last_request_summary.selected_aweme`
- `debug.last_response_summary.backend_response_status`
- `debug.last_response_summary.backend_response_short`
- `debug.last_response_summary.last_flush_response`
- `debug.last_response_summary.backend_error_code`
- full redacted `last_flush_request` body if Details exposes it, especially:
  - `capture_session_id`
  - `started_at`
  - `page`
  - `capture_context`
  - `items[0].aweme_id`
  - `items[0].source_url`
  - `items[0].raw_dom_detail_metrics.duration_seconds`
  - `items[0].raw_dom_detail_metrics.duration_text`
  - `items[0].raw_dom_detail_metrics.like_count`
  - `items[0].raw_dom_detail_metrics.comment_count`
  - `items[0].raw_dom_detail_metrics.favorite_count`
  - `items[0].raw_dom_detail_metrics.share_count`
  - `items[0].raw_dom_detail_metrics.extraction_source`
  - `items[0].raw_dom_detail_metrics.confidence`
  - `items[0].raw_evidence_summary.evidence_collection_version`
  - `items[0].profile_card_evidence.aweme_id`
  - `items[0].profile_card_evidence.posted_at`
  - `commit_policy`

From the browser/background/backend POST response, copy:

- HTTP status.
- Full response body for POST `/douyin-extension/full-modal-harvest`.
- If FastAPI validation, copy `detail[*].loc`, `detail[*].msg`, and `detail[*].type`.

From API logs, copy the lines around the failed POST:

- Uvicorn access line for `POST /douyin-extension/full-modal-harvest`.
- Presence or absence of `full_modal_harvest_received`.
- `full_modal_harvest_error` with `error_code`, `stage`, `diagnostics_id`, and `capture_session_id` if present.
- `douyin_extension_full_modal_harvest_ingested` if present.

## Recommended next fix phase after evidence

Do not change runtime yet. Once the live response body identifies the exact failure:

- If Pydantic `posted_at` parsing fails, either normalize extension `profile_card_evidence.posted_at` to backend-parseable ISO/null or widen backend schema intentionally.
- If `capture_session_id` is invalid, fix session handoff/runtime state and add a guard that validates UUID format before POST.
- If service returns an unrecognized 422 code, update controller classification and/or service response semantics in a targeted phase.
- If duration seconds is null but duration text exists, align local finalized guard with backend `duration_seconds > 0` requirement or update backend semantics intentionally.

No runtime change is recommended until the failed POST response body or API logs are copied.