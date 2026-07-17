# Metadata Hotfix Evidence Version 422 Log

## Scope

This hotfix is limited to extension harvest payload evidence-version compatibility, backend schema acceptance, focused tests, and documentation. It does not change metric extraction, navigation logic, Capture Inbox UI, CDP/debug workflows, or database schema.

## Root Cause Of 422

Smart Capture & Harvest calibrated-point flushes were sending `raw_evidence_summary.evidence_collection_version` as `phase12a_calibrated_five_point_workflow` from the extension evidence summary builder. The backend schema for full-modal harvest accepted only stable production evidence versions and rejected that transition value with a `422 literal_error` at `body.items.0.raw_evidence_summary.evidence_collection_version`.

## Extension Production Evidence Version

The extension now uses a single production constant:

```ts
PRODUCTION_EVIDENCE_COLLECTION_VERSION = "phase11a_production_stabilized_calibrated_harvest"
```

Production calibrated-point Smart Capture / Full Modal Harvest evidence summaries use this constant instead of deriving the value from feature phase names.

The evidence summary still includes the expected sources:

- `calibrated_point_modal_counts`
- `smart_capture_harvest`

## Backend Compatibility Values Added

The backend `DouyinExtensionRawEvidenceSummary` schema now accepts these transition values for older extension builds:

- `phase12a_calibrated_five_point_workflow`
- `phase12c_recovered_four_point_harvest`
- `phase12d_four_point_navigation_loop_fix`

The normal fixed extension sends `phase11a_production_stabilized_calibrated_harvest`.

## Normalizer Compatibility

The existing full-modal harvest normalizer path already treats calibrated-point metrics as normal modal detail evidence when `raw_dom_detail_metrics` contains the calibrated fields and extraction source. It persists:

- `duration_seconds`
- `like_count`
- `comment_count`
- `favorite_count`
- `share_count`
- captured performance and processing-fit statuses

No database schema change was needed.

## Tests Run

- `npm --workspace @reup-douyin/extension-douyin-capture run test`
- `npm --workspace @reup-douyin/extension-douyin-capture run typecheck`
- `npm --workspace @reup-douyin/extension-douyin-capture run build`
- `cd apps/api && python -m unittest tests.test_douyin_extension_capture_service tests.test_capture_metadata_normalizer tests.test_capture_inbox_metadata_status`
- `cd apps/api && python -m compileall src scripts`

## Verification Result

All required extension and API commands passed. The extension sends the backend-accepted stable production version, and the backend accepts the requested legacy/transition values for compatibility.
