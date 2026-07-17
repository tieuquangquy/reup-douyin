# Phase 22B-9 - Resume Notes

## What Changed

The one-item Capture Inbox save is now authoritative from backend readback:

- A backend session item response without `ok: true` is treated as a valid readback if it contains an `items` array.
- The extension matches the saved aweme across canonical and fallback backend fields.
- `parseCaptureInboxItemSaveResult()` handles direct, nested item/data/result ids and source ids.
- Verified existing items count as saved even when the save response did not include an item id.
- Saved count only increments after readback finds the aweme.

## Actual Backend Item Shape

The Capture Inbox session item read endpoint returns `CapturedItemResponse` rows with these relevant fields:

- `id`
- `capture_session_id`
- `source_video_external_id`
- `aweme_id` hydrated from `source_video_external_id`
- `source_url`
- `caption` / `title`
- `thumbnail_url`
- `posted_text`
- `posted_at`
- `duration_seconds`
- `duration_text`
- `like_count`
- `comment_count`
- `share_count`
- `metadata_status`
- `status`

## Metadata Pipeline

Thumbnail priority:

1. target/profile card thumbnail
2. target cover/poster
3. modal extractor thumbnail
4. browser modal video poster
5. visible modal image
6. `og:image`

Posted priority:

1. target/profile card posted fields
2. modal extractor posted fields
3. visible modal text fallback

No fake metadata is generated.

## Count Behavior

If verify finds the item:

- `one_item_status = saved_verified`
- `last_scanner_result = one_item_saved_verified`
- `last_scanner_error = null`
- saved count becomes `1`
- failed count remains `0`
- item id is populated from save response or verified item

If verify does not find the item:

- the old `saved_unverified` failure remains
- saved count stays `0`

## Capture Inbox UI

No Capture Inbox frontend files were changed.

## Tests

Focused tests already run:

- `npx tsx apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts`
- `python -m unittest tests.test_douyin_extension_capture_service tests.test_capture_inbox_metadata_status`
- `npm --workspace @reup-douyin/extension-douyin-capture run typecheck`

- `npm --workspace @reup-douyin/extension-douyin-capture run test`
- `npm --workspace @reup-douyin/extension-douyin-capture run build`
- `cd apps/api && python -m compileall src scripts`
