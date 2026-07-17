# Douyin Thumbnail Mapping Fix Resume

## Current Status

Implementation and focused verification are complete. The thumbnail path now has canonical extraction, validation, staging, API exposure, and frontend rendering behavior based on `thumbnail_url`.

## Audit Summary

The thumbnail path was audited end-to-end:

1. Extension extraction and payload typing.
2. Backend extension request schema.
3. Capture Inbox staging normalization and persistence.
4. Capture Inbox API response schema.
5. Web response typing and API client.
6. Capture Inbox card/detail resolver.

## Root Cause

Thumbnails are primarily lost before they reach the backend:

- The extension does not extract nearby image/poster fields from captured cards.
- The extension payload type does not expose thumbnail-capable fields.
- The backend request schema accepts only a narrow subset of possible thumbnail fields, so broader raw image fields are not a reliable path through validation.

The Capture Inbox API and frontend already have a canonical `thumbnail_url` field, but the data path feeding that field is incomplete.

## Completed Changes

1. Updated extension payload type and extractor to carry truthful image sources.
2. Updated backend request schema aliases and deterministic resolver behavior.
3. Kept `CapturedItem.thumbnail_url` / `CapturedItemResponse.thumbnail_url` as the canonical field.
4. Updated frontend resolver priority and shared card/drawer usage.
5. Added focused source tests across extension, backend, and web.
6. Ran verification commands.

## Verification

Passed:

- `npm --workspace @reup-douyin/extension-douyin-capture run typecheck`
- `npm --workspace @reup-douyin/extension-douyin-capture exec -- tsx src/extractor.test.ts`
- `npm run typecheck --workspace apps/web`
- `npx tsx apps/web/src/test/capture-inbox.test.ts`
- `python -m unittest tests.test_douyin_extension_capture_service` from `apps/api`

## Remaining Limitations

If Douyin does not expose any usable image URL in the visible DOM, extension payload, raw staged payload, metadata, or preview field, Capture Inbox will still show the honest `No thumbnail available` placeholder. This task did not add screenshot generation, crawling, downloading, or a full media processing pipeline.
