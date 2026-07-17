# Capture Inbox migration mismatch log

## Scope
- Task: fix **only** backend DB migration mismatch for intake fields on `captured_items`.
- Non-goals: no UI changes, no feature redesign, no unrelated migrations.

## Reported Runtime Failure
- Error code: `migration_mismatch`
- Missing columns on `captured_items`:
  - `intake_evaluation_error`
  - `intake_evaluation_status`
  - `intake_failed_rules_json`
  - `intake_filter_version`
  - `intake_missing_requirements_json`
  - `intake_preset_name`
  - `last_intake_evaluated_at`
  - `matches_intake`

## Audit Notes (chronological)
1. Confirmed model expects intake fields in `CapturedItem`.
2. Inspected migration table creation in revision `0021_douyin_capture_inbox` and verified those 8 columns are not created there.
3. Searched all Alembic revision files for the 8 intake column names and found no migration that adds them.
4. Verified migration graph head and lineage:
   - Head: `0024_reup_export_handoff`
   - Current DB revision (local): `0021_douyin_capture_inbox`
   - Chain is linear (`0021 -> 0022 -> 0023 -> 0024`), no branch conflict.

## Root Cause Classification
- Primary root cause: **missing migration** for intake fields on `captured_items`.
- Not the root cause:
  - Not a wrong migration target/branch head.
  - Not an unapplied existing intake migration (none exists in repo).
  - Not a malformed existing intake migration (none exists).

## Safety Constraints for Fix
- Preserve existing `captured_items` rows.
- Add columns as nullable except status with safe server default during migration.
- Create index for `intake_evaluation_status` and `last_intake_evaluated_at` to match model intent.
- Remove temporary server default after backfill-safe DDL, keeping application-level default behavior.

## Implemented Fix
- Added Alembic revision: `apps/api/alembic/versions/0025_capture_inbox_intake_columns.py`
- Final revision id used in file: `0025_capture_inbox_intake_cols` (32-char safe for `alembic_version.version_num`).
- Migration actions:
  1. Create enum type `intake_evaluation_status` (checkfirst).
  2. Add 8 missing columns to `captured_items`.
  3. Add indexes:
     - `ix_captured_items_intake_evaluation_status`
     - `ix_captured_items_last_intake_evaluated_at`
  4. Remove temporary server default from `intake_evaluation_status`.

## Verification Results
- `python -m alembic upgrade head` succeeded after revision-id correction.
- `python -m alembic current` => `0025_capture_inbox_intake_cols (head)`.
- Schema check returned all required columns:
  - `intake_evaluation_error`
  - `intake_evaluation_status`
  - `intake_failed_rules_json`
  - `intake_filter_version`
  - `intake_missing_requirements_json`
  - `intake_preset_name`
  - `last_intake_evaluated_at`
  - `matches_intake`
- Targeted backend verification passed:
  - `python -m unittest tests.test_douyin_extension_capture_service.DouyinExtensionCaptureServiceTests.test_capture_current_page_maps_migration_mismatch_to_structured_error`

## Notable Issue Encountered
- Initial revision id `0025_capture_inbox_intake_columns` exceeded `alembic_version.version_num` length in DB, causing:
  - `psycopg.errors.StringDataRightTruncation: value too long for type character varying(32)`
- Resolved by shortening revision id to `0025_capture_inbox_intake_cols` while keeping filename unchanged.
