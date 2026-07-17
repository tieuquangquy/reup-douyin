# Phase 22D-1 — Backend normalized Douyin metadata fields resume

## Phase status

Phase 22D-1 is implemented as response-only backend lazy normalization for Capture Inbox Douyin metadata fields.

## What changed

- Added `apps/api/src/services/douyin_metadata_normalization.py` with focused normalization helpers.
- Extended `CapturedItemResponse` in `apps/api/src/schemas/capture_inbox.py` with normalized duration, posted, estimated views, metrics, engagement, and data quality fields.
- Preserved existing raw/canonical fields and existing Capture Inbox response behavior.
- Added backend tests in `apps/api/tests/test_douyin_metadata_normalization.py`.
- Extended response regression tests in `apps/api/tests/test_capture_inbox_metadata_status.py`.

## Important implementation notes

- No database migration or backfill was added.
- No extension crawler, runner, batch, or frontend code was modified.
- All normalized fields are hydrated in the response mapper from existing row fields, `metadata_json`, and `raw_payload_json`.
- `engagement_rate` remains ratio-based for compatibility with existing backend behavior.
- `posted_source` is assigned before Phase 22D normalized posted hydration so source provenance is preserved.

## Tests already run

From `apps/api`:

```cmd
python -m unittest tests.test_douyin_metadata_normalization tests.test_capture_inbox_metadata_status
```

Result: passed, 23 tests.

## Recommended next validation

Before final handoff or merge, run:

```cmd
python -m unittest tests.test_douyin_metadata_normalization tests.test_capture_inbox_metadata_status tests.test_douyin_extension_capture_service
python -m compileall src scripts
```

## Non-goals still preserved

- No advanced filter UI redesign.
- No frontend Capture Inbox layout changes.
- No Douyin extension crawler/runner changes.
- No database schema change.
- No storage mutation/backfill for old items.
- No fake values for missing metadata.

## Remaining follow-up for future phases

Future Capture Inbox filter work can consume these response fields for Studio/Advanced filter and sort controls. Service-side query filtering over normalized estimated views may require persisted generated columns or explicit query-time extraction in a later backend filter phase.
