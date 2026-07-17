# Metadata Phase 15D — API Integrity Hardening Log

## Scope
- Harden backend full-modal ingest against `aweme_id` identity drift.
- Persist extension integrity diagnostics fields for forensics.
- Add API-side duplicate metric signature audit script.
- Add regression test for mismatch rejection path.

## Changes
1. Extended full-modal ingest schema with identity and integrity fields:
   - `target_aweme_id`
   - `modal_aweme_id_before_extract`
   - `modal_aweme_id_after_extract`
   - `extracted_aweme_id`
   - `data_integrity_status`
   - `data_integrity_reason`
   - `metric_signature`
   - `duplicate_signature_warning`
2. In ingest flow, reject update when:
   - extension marks `data_integrity_status="mismatch"`, or
   - any identity field value conflicts with payload `aweme_id`.
3. Persist integrity diagnostics on successful item update metadata.
4. Added audit script to detect duplicate modal metric signatures per capture session.
5. Added mismatch rejection unit test and updated success-path test payload to include integrity fields.

## Verification
- Ran targeted unit tests via `unittest` with `PYTHONPATH=apps/api`:
  - `test_full_modal_harvest_updates_existing_item_by_exact_aweme_id`
  - `test_full_modal_harvest_rejects_identity_mismatch_and_does_not_update_item`
- Result: both pass.

## Notes
- Local environment does not have `pytest` module available via `python -m pytest`; verification used `unittest` path.
