# Douyin Capture 500 Hardening Architecture

## Decision

The extension capture endpoint remains a staging endpoint. It must create a Capture Inbox session first, tolerate item-level defects, and return structured partial-success diagnostics. Canonical downstream storage remains unchanged and is only reached through explicit Capture Inbox promotion.

## Request lifecycle

1. HTTP boundary receives `POST /douyin-extension/capture-current-page`.
2. Request schema validation rejects structurally invalid requests as domain/validation errors.
3. Capture service creates a diagnostics id and rejects secret-like payloads before persistence.
4. Page classification and profile URL resolution decide whether the page is capturable.
5. Capture Inbox service creates and flushes `CaptureSession` before item processing.
6. Each submitted video payload is processed independently:
   - normalize raw fields,
   - build `CapturedItem`,
   - enrich readiness/dedupe state,
   - persist the item or a failed/skipped representation,
   - append safe failure summaries.
7. Session reconciliation aggregates counts and diagnostics.
8. Endpoint returns a structured response with staged counts, warnings, and failure summaries.

## Failure taxonomy

### Domain/validation failures

These are expected request states and should not become generic 500s:

- `request_validation_failed`
- `classify_extension_page`
- `resolve_profile_url`
- `secret_payload_rejected`

They return structured HTTP 4xx when capture cannot start.

### Partial item failures

These are ordinary capture defects and should return HTTP 200 with partial-success diagnostics when a session can be created:

- malformed item URLs,
- missing video ids,
- missing thumbnails/previews,
- bad timestamps,
- unsupported statistics shapes,
- duplicate visible items,
- per-item enrichment lookup failures that can be isolated.

### System failures

These may still return HTTP 500 because they indicate infrastructure or programming failure:

- database unavailable,
- migration/schema mismatch,
- session creation cannot flush,
- transaction cannot commit,
- unhandled programming error outside item isolation.

## Response contract

Existing fields remain for compatibility. New diagnostic fields add explicit status:

```json
{
  "success": true,
  "stage": "item_normalization_partial_failure",
  "error_code": null,
  "warning_codes": ["partial_item_failures"],
  "failure_summaries": [
    {
      "stage": "item_normalization_partial_failure",
      "item_index": 2,
      "code": "item_missing_video_identity",
      "message": "Captured item is missing both video URL and external id."
    }
  ],
  "visible_captured_count": 4,
  "submitted_count": 4,
  "staged_count": 3,
  "deduped_count": 1,
  "skipped_count": 0,
  "failed_count": 1
}
```

## Observability

- Logs include `diagnostics_id`, `capture_session_id`, `capture_id`, counts, and stage.
- Session `metadata_json`, `diagnostics_json`, and `result_summary_json` include safe diagnostics only.
- No raw credentials, cookies, tokens, or private paths are logged.

## UI projection

- Popup shows submitted, staged, ready, duplicate, skipped, failed counts and diagnostics id.
- Popup backend errors include backend code/stage/diagnostics when available.
- Web manager shows the same partial-success summary and failure summaries.

## Review Board boundary

The Review Board continues to see only canonical `VideoCandidate` records produced by Capture Inbox promotion. Raw extension captures and failed captured items remain in Capture Inbox and never appear in Review Board directly.
