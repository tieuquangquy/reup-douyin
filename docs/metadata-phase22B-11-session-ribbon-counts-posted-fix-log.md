# Phase 22B-11 Session Ribbon Counts and Posted Fix

## Problem

One-item collection was already creating a verified Capture Inbox item, but the Session Ribbon still showed `0 captured / 0 ready` while the session items endpoint returned the item. The item also still rendered `Posted: Not captured`.

## Root Causes

1. Session Ribbon counts came from `/capture-inbox/sessions`, which returned `CaptureSession` rows with stale counter fields.
2. `CaptureInboxService.list_sessions()` did not eager-load items or recompute counters from the actual session item store.
3. `CaptureInboxService.get_session()` loaded items, but still returned the persisted session counters without recomputing them for the response.
4. Posted extraction was still too narrow in the extension modal fallback path and missed some visible author-row or embedded publish-time evidence.

## Session Count Aggregation Fix

- `CaptureInboxService.list_sessions()` now loads `CaptureSession.items` and recomputes live counts before returning sessions.
- `CaptureInboxService.get_session()` now recomputes live counts from loaded items before returning the session.
- `_reconcile_session()` now falls back to querying `CapturedItem` rows by `capture_session_id` if the relationship is stale or empty.
- Finalized harvest item creation now pushes the new `CapturedItem` onto `session.items` when possible so the in-memory relationship stays coherent inside the same transaction.

## Session Ribbon Response Fields

Session Ribbon still reads the existing top-level session fields:

- `captured_item_count`
- `ready_item_count`
- `duplicate_item_count`
- `failed_item_count`

Backend now also fills compatibility aliases on `CaptureSessionResponse`:

- `captured_count`
- `ready_count`
- `duplicate_count`
- `failed_count`
- `needs_action_count`

The per-session items endpoint counts object now includes `needs_action`.

## Posted Extraction Strategy

Extension modal fallback now tries, in order:

1. visible body text for direct publish-time strings
2. visible body text for relative author-row strings like `12小时前`, `刚刚`, `3天前`
3. embedded script text near the current `aweme_id` for `createTime`, `publishTime`, `publish_time`, or `create_time_str`

The extension keeps `posted_text` even when `posted_at` cannot be safely parsed.

## Backend Posted Mapping

- Raw DOM detail metrics schema now accepts `posted_at`, `posted_source`, and `posted_parse_confidence`.
- Capture Inbox item response accepts and rehydrates posted-source values including `modal_author_row`, `direct_publish_time`, `embedded_aweme_json`, and `profile_card`.
- Capture Inbox item response continues to resolve posted display from `posted_at` first, then `posted_text`.

## Metadata Status Policy

Ready/complete metadata still requires:

- source id
- source URL
- duration
- metrics
- thumbnail
- posted metadata (`posted_at` or reliable `posted_text`)

If posted is missing, the item stays partial/needs action instead of silently looking complete.

## Capture Inbox UI Scope

Capture Inbox frontend UI was not modified. The fix is in backend aggregation/response mapping and extension extraction/payload wiring.

## Tests Run

- `npx tsx apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts`
- `python -m unittest tests.test_capture_inbox_metadata_status`
- `python -m unittest tests.test_douyin_extension_capture_service`
- `npm --workspace @reup-douyin/extension-douyin-capture run test`
- `npm --workspace @reup-douyin/extension-douyin-capture run typecheck`
- `npm --workspace @reup-douyin/extension-douyin-capture run build`
- `python -m unittest tests.test_douyin_extension_capture_service tests.test_capture_inbox_metadata_status`
- `python -m compileall src scripts`
