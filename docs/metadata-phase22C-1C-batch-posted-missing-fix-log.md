# Phase 22C-1C Batch Posted Missing Fix Log

## Scope
- Implement Phase 22C-1C only.
- Fix Posted metadata missing in Batch Next 3 saved items.
- Keep the existing batch save, queue, session reuse, and verification flow.

## Where Posted Was Lost
- Batch already reused `runOneItemCollectAndSave()`.
- Backend persistence and GET session item mapping already supported:
  - `posted_text`
  - `posted_text_raw`
  - `posted_at`
  - `posted_display`
- The loss point was the extension runtime producer in [`apps/extension-douyin-capture/src/popup.ts`](apps/extension-douyin-capture/src/popup.ts):
  - `extractModalMetrics()` parsed Posted from modal/body/script fallback
  - but only returned partial fields
  - `posted_text_raw` was dropped
  - `posted_display` was dropped
  - parsed `posted_at` from `extractDouyinPostedMetadataFromText()` was not propagated
- Result: batch payloads frequently reached backend with no authoritative Posted metadata even though parseable evidence existed in-page.

## Fix Applied
- `popup.ts` now returns the canonical Posted fields from the batch modal extraction path:
  - `posted_text`
  - `posted_text_raw`
  - `posted_at`
  - `posted_display`
  - `posted_source`
  - `posted_parse_confidence`
- Batch continues to reuse the same canonical one-item payload builder.
- Added explicit batch diagnostics proving canonical posted reuse:
  - `batch_uses_canonical_posted_pipeline`
  - `batch_item_payload_posted_text_raw`
  - `batch_item_payload_posted_display`
  - `batch_item_payload_posted_at`
  - `batch_item_payload_posted_source`

## Parser Behavior
- Shared posted parsing already supported raw relative and absolute values.
- Batch producer regex now also captures Chinese relative forms for modal/body extraction, including:
  - `刚刚`
  - `昨天`
  - `1天前`
  - `1周前`
  - `一周前`
  - `两周前`
  - `1星期前`

## Backend Mapping
- Backend response path remains unchanged in shape:
  - `posted_text = posted_display` when available
  - `posted_text_raw` preserved separately
  - `posted_at` and `posted_display` returned from session items
- Capture Inbox frontend did not require changes.

## Verification Behavior
- Added one-item and batch diagnostics for backend-returned Posted fields:
  - `verify_item_posted_text_raw`
  - `verify_item_posted_display`
  - `verify_item_posted_at`
  - `verify_item_posted_source`
  - `verify_item_posted_present`
- Added mapping warning diagnostics when payload had Posted but backend verify item did not:
  - `metadata_mapping_warning = posted_lost_in_backend`
  - `posted_lost_in_backend = true`

## Batch Summary
- Added batch-level Posted counters:
  - `batch_posted_extracted_count`
  - `batch_posted_missing_count`
  - `batch_posted_backend_verified_count`
  - `batch_posted_lost_in_backend_count`

## Tests Run
- `npx tsx apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts`
- `npm --workspace @reup-douyin/extension-douyin-capture run test`
- `npm --workspace @reup-douyin/extension-douyin-capture run typecheck`
- `npm --workspace @reup-douyin/extension-douyin-capture run build`
- `cd apps/api && python -m unittest tests.test_douyin_extension_capture_service tests.test_capture_inbox_metadata_status`
- `cd apps/api && python -m compileall src scripts`
