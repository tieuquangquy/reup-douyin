# Phase 22B-9 - Item Verify, Posted, Thumbnail Fix Log

## Scope

Phase 22B-9 fixed the remaining one-item Capture Inbox handoff issues only:

- Extension verification now matches the actual item returned by `GET /douyin-extension/capture-sessions/{session_id}/items`.
- The backend item id is recorded when the item exists.
- The one-item payload preserves `source_video_external_id`.
- Thumbnail and posted metadata are carried from profile target evidence first, then modal extraction fallback.
- Metadata status only reaches `complete` when the item has time, performance, processing-fit, and thumbnail metadata.

Capture Inbox frontend UI was not modified.

## Root Cause

The backend session-items endpoint returns the Capture Inbox shape:

```json
{
  "session_id": "...",
  "items_count": 1,
  "items": [
    {
      "id": "...",
      "capture_session_id": "...",
      "source_video_external_id": "...",
      "aweme_id": "...",
      "source_url": "...",
      "thumbnail_url": "...",
      "posted_text": "...",
      "posted_at": null,
      "metadata_status": "partial|complete"
    }
  ],
  "counts": { "captured": 1, "ready": 0 }
}
```

The extension verifier expected `ok: true` on this response. Because the real readback response has no `ok` field, the verifier could classify a visible backend item as `not_found`.

## Verify Matching

`matchesCaptureInboxItemAweme(item, awemeId)` now accepts the actual backend item shape and matches by:

- `source_video_external_id`
- `aweme_id`
- `video_id`
- `external_id`
- `source.video_external_id`
- `source_url`
- `video_url`
- `canonical_url`
- `raw.aweme_id`
- `raw_payload_json.aweme_id`

If readback finds the item, the final extension state becomes `one_item_saved_verified`, clears `saved_unverified`, stores the item id, and increments saved count.

## Thumbnail Fallback

Thumbnail is selected in this order:

1. Profile target `thumbnail_url`
2. Profile target `cover_url`
3. Profile target `poster_url`
4. Modal extractor `thumbnail_url`
5. Browser modal fallback from `video[poster]`
6. Visible modal image
7. `og:image`

The payload includes `profile_card_evidence.thumbnail_url` when a real thumbnail is found. No placeholder or fake thumbnail is generated.

## Posted Extraction

Posted metadata is selected in this order:

1. Profile target `posted_text` / `posted_at`
2. Modal extractor `posted_text` / `posted_at`
3. Browser modal fallback matching visible text like `12小时前`, `刚刚`, `昨天`, or `发布时间：2026-05-08 06:00`

Relative time is stored as `posted_text`. `posted_at` remains null unless a confident timestamp is available.

## Metadata Status And Counts

Backend item response hydration now treats thumbnail as part of complete metadata. An item is `complete` only when it has:

- aweme/source id
- source URL
- duration
- performance metrics
- posted text or posted timestamp
- thumbnail URL

If the item exists but posted/thumbnail is missing, extension still reports `saved_verified`, with a metadata note that the saved item needs metadata. It no longer reports collection failure just because the item is incomplete.

## Tests Run

- `npx tsx apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts`
- `python -m unittest tests.test_douyin_extension_capture_service tests.test_capture_inbox_metadata_status`
- `npm --workspace @reup-douyin/extension-douyin-capture run typecheck`
- `npm --workspace @reup-douyin/extension-douyin-capture run test`
- `npm --workspace @reup-douyin/extension-douyin-capture run build`
- `cd apps/api && python -m compileall src scripts`
