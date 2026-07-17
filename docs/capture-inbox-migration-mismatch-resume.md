# Capture Inbox migration mismatch resume

## Current Status
- Audit completed.
- Root cause identified: missing Alembic migration for 8 intake columns on `captured_items`.
- Docs-first requirement satisfied with:
  - `docs/capture-inbox-migration-mismatch-log.md`
  - this file.

## Evidence Summary
- Model contains intake fields in `CapturedItem`.
- Revision `0021_douyin_capture_inbox` creates `captured_items` without those fields.
- No later revision adds those fields.
- Alembic graph is linear to head `0024_reup_export_handoff`.

## Exact Missing Columns
- `intake_evaluation_error`
- `intake_evaluation_status`
- `intake_failed_rules_json`
- `intake_filter_version`
- `intake_missing_requirements_json`
- `intake_preset_name`
- `last_intake_evaluated_at`
- `matches_intake`

## Completed Action
- Added and applied narrow migration: `apps/api/alembic/versions/0025_capture_inbox_intake_columns.py`.
- Effective revision id: `0025_capture_inbox_intake_cols`.

## Verification Outcome
1. `python -m alembic upgrade head` completed.
2. `python -m alembic current` reports `0025_capture_inbox_intake_cols (head)`.
3. Database schema check confirms all 8 required intake columns exist on `captured_items`.
4. Targeted backend test passed:
   - `python -m unittest tests.test_douyin_extension_capture_service.DouyinExtensionCaptureServiceTests.test_capture_current_page_maps_migration_mismatch_to_structured_error`

## Local Command To Apply Fix (exact)
From `apps/api`:
- `python -m alembic upgrade head`
