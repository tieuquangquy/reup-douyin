# Metadata Hotfix Evidence Version 422 Resume

## Status

The 422 evidence-version hotfix is complete and verified.

## Root Cause

The extension generated full-modal harvest payloads with `raw_evidence_summary.evidence_collection_version = "phase12a_calibrated_five_point_workflow"`. The backend full-modal harvest schema did not accept that transition value, so flush failed with a `422 literal_error` before normalization or persistence.

## Extension Fix

`apps/extension-douyin-capture/src/modalHarvest.ts` now exports and uses:

```ts
PRODUCTION_EVIDENCE_COLLECTION_VERSION = "phase11a_production_stabilized_calibrated_harvest"
```

`buildDomDetailEvidenceSummary()` uses this constant for production calibrated-point Smart Capture & Harvest payloads.

## Backend Fix

`apps/api/src/schemas/douyin_extension.py` now accepts compatibility values for old extension builds:

- `phase12a_calibrated_five_point_workflow`
- `phase12c_recovered_four_point_harvest`
- `phase12d_four_point_navigation_loop_fix`

Existing stable values remain accepted, including `phase11a_production_stabilized_calibrated_harvest`.

## Tests Added / Updated

- Extension regression verifies production evidence summary uses `phase11a_production_stabilized_calibrated_harvest`.
- Extension regression verifies production summary does not send `phase12a_calibrated_five_point_workflow`.
- Extension regression verifies evidence sources still include `calibrated_point_modal_counts` and `smart_capture_harvest`.
- API schema regression verifies phase12 transition evidence versions are accepted.
- Existing API full-modal harvest tests verify calibrated-point payload updates existing items, persists duration/like/comment/favorite/share, and repeated flush remains idempotent.

## Verification Commands

All passed:

```bash
npm --workspace @reup-douyin/extension-douyin-capture run test
npm --workspace @reup-douyin/extension-douyin-capture run typecheck
npm --workspace @reup-douyin/extension-douyin-capture run build
cd apps/api && python -m unittest tests.test_douyin_extension_capture_service tests.test_capture_metadata_normalizer tests.test_capture_inbox_metadata_status
cd apps/api && python -m compileall src scripts
```

## Live Retest

1. Rebuild/reload `apps/extension-douyin-capture/dist`.
2. Start backend API with the updated schema.
3. Open Douyin modal and run Smart Capture & Harvest.
4. Confirm metrics extract and pending flush occurs.
5. Confirm backend no longer returns `422 literal_error` for `raw_evidence_summary.evidence_collection_version`.
6. Confirm flushed item updates duration, like, comment, favorite, and share metadata.
