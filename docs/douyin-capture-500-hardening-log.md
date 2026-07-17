# Douyin Capture 500 Hardening Log

## Purpose

Track the hardening of `POST /douyin-extension/capture-current-page` so malformed or partially incomplete active-tab payloads no longer produce generic HTTP 500 responses.

## Scope

- `apps/api`: route exception mapping, capture service response contract, Capture Inbox staging and per-item diagnostics.
- `apps/web`: Douyin Extension Manager error/status projection and capture summary display.
- `apps/extension-douyin-capture`: popup backend error projection and capture summary display.
- Tests and verification for ordinary malformed item payloads, partial success, and true system failures.

## Non-goals

- No crawler implementation.
- No video processing implementation.
- No direct promotion to Review Board from raw extension captures.
- No database model rewrite unless a narrowly scoped field is required.
- No dependency additions.

## Initial audit notes

### Backend route

`POST /douyin-extension/capture-current-page` currently catches `ValueError` and translates `DouyinExtensionCaptureError` into HTTP 422. Unexpected exceptions from `_to_filter_config`, staging, item normalization, DB flush, reconciliation, or response serialization can still escape as generic HTTP 500.

### Backend service

`DouyinExtensionCaptureService.capture_current_page` validates secret-like payloads, classifies page, resolves profile URL, then calls `CaptureInboxService.stage_extension_capture`. It assumes staging succeeds atomically. Ordinary item-level malformed data can become a request-level crash if the staging service raises.

### Capture Inbox staging

`CaptureInboxService.stage_extension_capture` creates a session before looping items, but the item loop is not isolated. `_build_item`, `_enrich_item`, `db.add`, and `db.flush` run without per-item exception handling. A single bad item can roll back the whole session and produce an opaque 500.

Crash-prone stages:

1. `request_validation_failed`: Pydantic request validation and filter config parsing.
2. `capture_session_created`: workspace/session creation and initial DB flush.
3. `item_normalization_partial_failure`: `_build_item` type conversion, timestamp conversion, URL/id extraction, statistics merging.
4. `item_persist_partial_failure`: item `add`/`flush`, JSON serialization, constraints.
5. `enrichment_partial_failure`: duplicate lookup, canonical SourceVideo lookup, readiness state generation.
6. `promotion_partial_failure`: not expected during capture after Capture Inbox pivot, but kept as a diagnostic stage for future promotion actions.
7. `system_failure`: DB outage, migration mismatch, programming errors, or other infrastructure failures.

## Planned response model additions

Add structured fields to the capture response while preserving existing count fields:

- `stage`
- `error_code`
- `warning_codes`
- `failure_summaries`
- `visible_captured_count`
- `submitted_count`
- `staged_count`
- `deduped_count`
- `skipped_count`
- `failed_count`

## Implementation log

- 2026-04-27: Created hardening docs before implementation and completed initial audit of route/service/staging/popup/manager paths.
- 2026-04-27: Hardened Capture Inbox staging so `CaptureSession` is committed before item processing and item normalization/persist failures are recorded as failed item diagnostics where possible.
- 2026-04-27: Added structured capture response fields for stage, warning codes, failure summaries, submitted/staged/deduped/skipped/failed counts, and visible captured count.
- 2026-04-27: Updated route validation mapping so non-domain `ValueError` failures return structured request-validation details instead of sparse errors.
- 2026-04-27: Updated web manager and extension popup summaries to show submitted, staged, ready, duplicate, skipped, failed, warning, stage, and diagnostics values.
- 2026-04-27: Added API, web, and extension tests for partial malformed captures, true system failures, and UI/backend diagnostic projection.

## Verification

- `python -m unittest tests.test_douyin_extension_capture_service` from `apps/api`: passed, 8 tests.
- `npm --workspace @reup-douyin/web run typecheck`: passed.
- `npm --workspace @reup-douyin/extension-douyin-capture run typecheck`: passed.
- `npx tsx src/test/douyin-extension-manager-ux.test.ts` from `apps/web`: passed.
- `npx tsx src/popupActions.test.ts` from `apps/extension-douyin-capture`: passed.
- `npm --workspace @reup-douyin/web test`: passed.
- `npm --workspace @reup-douyin/extension-douyin-capture test`: passed.

Note: `python -m unittest apps.api.tests.test_douyin_extension_capture_service` from the repository root failed because the API tests expect `apps/api` as the working directory for `src` imports. The corrected command above passed.
