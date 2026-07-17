# Phase 22B-10 - Resume Notes

## What Changed

The one-item Capture Inbox save now feeds higher-quality item/session metadata:

- thumbnail selection is aweme-scoped
- Get APP/logo/avatar/sidebar assets are rejected
- posted text is extracted from modal visible text
- payload carries `thumbnail_url`, `posted_text`, `posted_at`, source id, and metadata status
- backend persists thumbnail/posted fields to the existing Capture Inbox item store
- ready count is reserved for complete metadata

## Thumbnail Behavior

The extension prefers profile scan thumbnail evidence by aweme id. If that is missing, it considers modal-scoped candidates only when the current URL `modal_id` matches the target aweme. Generic page images are not trusted.

Rejected examples:

- Get APP image
- logo
- avatar
- app/download banner
- small SVG/icon assets
- non-aweme page image

## Posted Behavior

The extension stores posted text when visible, even when `posted_at` cannot be safely parsed.

Examples:

- `12小时前` -> `posted_text = "12小时前"`
- `@地球之旅 · 12小时前` -> `posted_text = "12小时前"`
- `发布时间：2026-05-08 06:00` -> direct publish source, parsed timestamp when safe

## Backend Behavior

Backend finalized modal ingest persists:

- identity fields
- source URL
- caption/title
- thumbnail URL / preview URL
- posted text/timestamp
- duration and metrics

Backend session preflight stores expected/queued counts and scanner source metadata for richer session summaries.

## Count Behavior

- Captured increments when the item exists.
- Ready increments only when metadata is complete.
- Missing thumbnail or posted data keeps the saved item as partial/needs action.

## Capture Inbox UI

Capture Inbox frontend was not changed.

## Tests

Focused tests passed:

- `npx tsx apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts`
- `python -m unittest tests.test_douyin_extension_capture_service tests.test_capture_inbox_metadata_status`
- `npm --workspace @reup-douyin/extension-douyin-capture run typecheck`

- `npm --workspace @reup-douyin/extension-douyin-capture run test`
- `npm --workspace @reup-douyin/extension-douyin-capture run build`
- `cd apps/api && python -m compileall src scripts`
