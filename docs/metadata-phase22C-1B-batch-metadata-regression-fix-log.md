# Phase 22C-1B Batch Metadata Regression Fix Log

## Scope
- Implement Phase 22C-1B only.
- Keep the existing Next 3 safe batch runner.
- Fix batch metadata regression so batch uses the same canonical one-item duration and posted pipeline.
- Add week-relative posted parser support and regression tests.

## Audit Result
- The canonical one-item path remains:
  - `runOneItemCollectAndSave()`
  - `buildCaptureInboxItemPayload()`
  - `guardCaptureInboxPayload()`
  - `flushOneCanonicalHarvestPayload()`
  - `verifyCaptureInboxItemCreated()`
- The batch path remains:
  - `runBatchCollectNext3SafeMode()`
  - per-item delegation into `runOneItemCollectAndSave()`
- The regression was not a separate batch extractor. Batch already reused the one-item runner.
- The actual divergence was shared metadata normalization:
  - extension posted parser did not parse `周前` / `星期前`
  - backend lazy posted normalization did not parse those values either
  - batch regression coverage did not explicitly assert canonical posted and duration fields

## Changes
- Extended extension posted parsing in `canonicalHarvest.ts` to support:
  - `1周前`
  - `2周前`
  - `一周前`
  - `两周前`
  - `1星期前`
- Extended backend lazy posted normalization in `capture_inbox.py` with the same week-relative support.
- Kept batch orchestration on the canonical one-item path and added an explicit controller comment documenting that requirement.
- Added canonical payload diagnostics so batch summaries preserve:
  - `batch_item_payload_posted_display`
  - `batch_item_payload_posted_text_raw`
  - `batch_item_payload_duration_source`
  - `batch_item_payload_duration_seconds`
- Added verify diagnostics for backend-returned normalized metadata:
  - `verify_item_posted_display`
  - `verify_item_posted_text_raw`
  - `verify_item_posted_at`
  - `verify_item_duration_seconds`
  - `verify_item_duration_text`
  - `verify_item_duration_source`
- Added `selected_duration_source` to the one-item canonical payload detail metrics so duration provenance is preserved end to end.

## Duration Validation
- Batch still uses the same aweme-scoped one-item extraction result.
- No batch-only duration extraction path remains active.
- Batch payload now preserves the canonical duration source from the one-item extractor.

## Backend Mapping
- Capture Inbox response continues to prioritize:
  1. `posted_display`
  2. formatted `posted_at`
  3. `posted_text_raw`
- Week-relative posted text now reaches `dd/mm/yyyy` end to end when parsing is confident.

## Tests Added
- Extension tests now cover:
  - week-relative posted parser behavior
  - raw posted text preservation
  - batch payload preserving `posted_display`, `posted_text_raw`, `selected_duration_source`, and `duration_seconds`
  - batch verify diagnostics preserving normalized posted and duration fields
- Backend tests now cover:
  - lazy week-relative posted normalization in Capture Inbox response

## Tests Run
- `npx tsx apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts`
- `npm --workspace @reup-douyin/extension-douyin-capture run test`
- `npm --workspace @reup-douyin/extension-douyin-capture run typecheck`
- `npm --workspace @reup-douyin/extension-douyin-capture run build`
- `cd apps/api && python -m unittest tests.test_capture_inbox_metadata_status tests.test_douyin_extension_capture_service`
- `cd apps/api && python -m compileall src scripts`
