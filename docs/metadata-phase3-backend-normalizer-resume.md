# Metadata Phase 3 Backend Normalizer Resume

## Current Phase

Phase 3 backend canonical normalizer implementation from Phase 2 raw evidence.

## Completed So Far

1. Audit performed for:
   - raw evidence acceptance in [`douyin_extension.py`](../apps/api/src/schemas/douyin_extension.py)
   - raw evidence persistence in [`CaptureInboxService._build_item()`](../apps/api/src/services/capture_inbox_service.py:703)
   - existing response hydration/status logic in [`capture_inbox.py`](../apps/api/src/schemas/capture_inbox.py)
   - current model storage boundaries in [`models/capture_inbox.py`](../apps/api/src/models/capture_inbox.py)
2. Docs-first started:
   - [`metadata-phase3-backend-normalizer-log.md`](./metadata-phase3-backend-normalizer-log.md)
   - [`metadata-phase3-backend-normalizer-architecture.md`](./metadata-phase3-backend-normalizer-architecture.md)

## Confirmed Gaps

- Canonical fields in `_build_item` currently derive from top-level payload + merged stats, not deterministic raw-evidence normalization contract.
- Group statuses/missing reasons are currently inferred in response schema and are not authored by an explicit normalizer output.
- Raw evidence summary is preserved but not explicitly normalized as compact response contract field.

## Final Implementation Summary

Completed:

1. Added [`CaptureMetadataNormalizer`](../apps/api/src/services/capture_metadata_normalizer.py:59) with deterministic normalization for time, duration, performance, engagement, provenance, statuses, and missing reasons.
2. Wired normalization into [`CaptureInboxService._build_item()`](../apps/api/src/services/capture_inbox_service.py:704), persisting canonical metadata and explicit status/source/reason fields into `metadata_json` while preserving Phase 2 raw evidence fields.
3. Updated [`CapturedItemResponse`](../apps/api/src/schemas/capture_inbox.py:27) source literal compatibility and raw evidence summary hydration.
4. Added/updated tests:
   - [`test_capture_metadata_normalizer.py`](../apps/api/tests/test_capture_metadata_normalizer.py)
   - [`test_douyin_extension_capture_service.py`](../apps/api/tests/test_douyin_extension_capture_service.py)
   - [`test_capture_inbox_metadata_status.py`](../apps/api/tests/test_capture_inbox_metadata_status.py)

## Verification Commands and Results

Executed from [`apps/api`](../apps/api):

- `python -m unittest tests.test_capture_metadata_normalizer tests.test_douyin_extension_capture_service tests.test_capture_inbox_metadata_status -v`

Result:

- `Ran 47 tests in 0.143s`
- `OK`

## Scope Guardrails

- Do not edit extension code in this phase.
- Do not redesign UI.
- Do not implement hydration job/queue/review flow.
- Preserve raw evidence fields for audit/debug.
