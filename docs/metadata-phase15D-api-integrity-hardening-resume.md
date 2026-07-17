# Metadata Phase 15D — Resume Notes

## Completed
- Extension-side integrity contract and progress diagnostics were already in place.
- Backend now enforces strict `aweme_id` identity safety before applying modal updates.
- Backend now stores integrity telemetry fields in item metadata for traceability.
- Duplicate signature audit utility is available for offline session diagnostics.
- Full-modal tests include positive exact-match and negative mismatch cases.

## Operational Resume Steps
1. Run API-focused checks:
   - `set PYTHONPATH=apps/api&& python -m unittest apps.api.tests.test_douyin_extension_capture_service.DouyinExtensionCaptureServiceTests.test_full_modal_harvest_updates_existing_item_by_exact_aweme_id apps.api.tests.test_douyin_extension_capture_service.DouyinExtensionCaptureServiceTests.test_full_modal_harvest_rejects_identity_mismatch_and_does_not_update_item`
2. (Optional) Run smoke ingest script on a real session:
   - `python apps/api/scripts/smoke_full_modal_harvest_ingest.py --session-id <uuid> --aweme-id <aweme_id>`
3. Run duplicate signature audit:
   - `python apps/api/scripts/audit_duplicate_modal_metric_signatures.py --session-id <uuid>`

## Expected Behavior
- Mismatched identity payloads are rejected and counted as failed item updates.
- Matched payloads apply updates and preserve integrity metadata in `metadata_json`.
- Duplicate signature groups are reported with grouped item IDs.
