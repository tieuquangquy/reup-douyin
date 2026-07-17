# Phase 22B-10 - Thumbnail, Posted, Session Metadata Fix Log

## Scope

Phase 22B-10 improves one-item Capture Inbox metadata quality without changing Capture Inbox frontend UI and without enabling batch processing.

Changed areas:

- aweme-scoped thumbnail selection
- UI chrome thumbnail rejection
- posted text extraction fallback
- one-item payload metadata mapping
- backend item persistence for thumbnail/posted metadata
- backend session preflight metadata
- ready/needs-action count semantics

## Why Thumbnail Was Wrong

The extension modal fallback could choose a generic page image from the modal/body or `og:image`. On Douyin, those candidates can be app-promotion assets such as a red "Get APP" image. The fallback was not sufficiently tied to the current `modal_id`/aweme context and did not reject app/banner/logo/avatar UI chrome.

## Thumbnail Source Priority

The new thumbnail resolver selects only aweme-scoped candidates:

1. profile scan target `thumbnail_url`
2. profile scan target `cover_url`
3. profile scan target `poster_url`
4. modal extractor thumbnail
5. modal video `poster`, only when the current modal id matches the target aweme
6. image near the current modal/card/video context
7. `og:image`, only when modal aweme matches and the image is not UI chrome

## Thumbnail Rejection Rules

Candidates are rejected when they look like Douyin UI chrome:

- text/alt/title/aria/container contains `Get APP`, `下载`, `app`, `logo`, `avatar`, `头像`, `douyin`, or `抖音`
- URL contains app/logo/avatar/icon/download/sprite/favicon/QR markers
- SVG/small icon assets
- button/banner aspect ratios
- not near the current aweme modal/card area

Backend thumbnail parsing also rejects URL markers for app/logo/avatar/icon assets.

## Posted Extraction

The popup fallback extracts visible posted text from the modal page:

- author row examples: `@name · 12小时前`, `12小时前`, `3天前`, `昨天`, `刚刚`
- direct publish text: `发布时间：2026-05-08 06:00`, `发布于 2026-05-08 06:00`

Relative values are preserved as `posted_text`; `posted_at` is only populated when parsing is confident.

## Backend Item Mapping

The finalized modal harvest backend now persists:

- `source_video_external_id`
- `source_url`
- `caption`
- `thumbnail_url` / `preview_url`
- `posted_text`
- `posted_at`
- duration and metric fields
- metadata provenance such as `thumbnail_source` and `posted_source`

`GET /douyin-extension/capture-sessions/{session_id}/items` returns these fields through the existing `CapturedItemResponse`.

## Metadata Status And Counts

An item is complete/ready only when it has:

- source video id
- source URL
- title or caption
- duration
- like/comment/share/favorite metrics
- thumbnail URL
- posted text or posted timestamp

If thumbnail or posted metadata is missing, the item remains saved and captured, but metadata is partial and the session ready count does not increment.

## Session Metadata

Capture session preflight now persists:

- `profile_url`
- `profile_sec_uid_or_path`
- `expected_video_count`
- `queued_count`
- `collection_mode`
- `created_by = douyin_scanner`

Session responses include `needs_action_count` derived from captured minus ready/duplicate/skipped/failed.

## Capture Inbox UI

No Capture Inbox frontend UI files were changed.

## Tests Run

- `npx tsx apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts`
- `python -m unittest tests.test_douyin_extension_capture_service tests.test_capture_inbox_metadata_status`
- `npm --workspace @reup-douyin/extension-douyin-capture run typecheck`
- `npm --workspace @reup-douyin/extension-douyin-capture run test`
- `npm --workspace @reup-douyin/extension-douyin-capture run build`
- `cd apps/api && python -m compileall src scripts`
