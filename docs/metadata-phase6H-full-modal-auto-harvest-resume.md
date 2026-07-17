# Phase 6H Full Modal Auto-Harvest Resume

## Current step

- complete

## Done

- audited extension popup/content-script transport
- audited backend extension API and capture persistence path
- chose modal auto-harvest architecture
- created Phase 6H docs
- implemented extension modal harvester controls and background loop
- implemented backend full-modal evidence ingest endpoint/service
- aligned `CaptureMetadataNormalizer` for `raw_dom_detail_metrics`
- added focused extension and backend tests
- ran verification

## In progress

- none

## Next exact task

- run the documented live modal-harvest workflow on a real Douyin profile session

## Key files

- `apps/extension-douyin-capture/src/contentScript.ts`
- `apps/extension-douyin-capture/src/popup.ts`
- `apps/extension-douyin-capture/src/popupTransport.ts`
- `apps/extension-douyin-capture/src/types.ts`
- `apps/api/src/api/routes/douyin_extension.py`
- `apps/api/src/services/douyin_extension_capture_service.py`
- `apps/api/src/services/capture_metadata_normalizer.py`
