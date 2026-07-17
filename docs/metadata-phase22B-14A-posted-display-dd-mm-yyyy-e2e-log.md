# Phase 22B-14A Posted display dd/mm/yyyy E2E Log

## Scope
- Implement Phase 22B-14A only.
- Force Capture Inbox / Tile Gallery posted display to use `dd/mm/yyyy` for both newly ingested and legacy saved items.
- Preserve raw Chinese evidence such as `4天前`, `3天前`, `2天前`, `昨天`, and `刚刚` separately.
- Keep the fix scoped to metadata flow and response hydration; do not redesign Capture Inbox UI.

## Posted Data Flow Audit
- Extension parsing in [`extractDouyinPostedMetadataFromText()`](../apps/extension-douyin-capture/src/wholeProfileHarvest/canonicalHarvest.ts:185) already emits `posted_text_raw`, `posted_at`, `posted_display`, `posted_source`, and `posted_parse_confidence`.
- Backend finalized ingest in [`_apply_modal_harvest_to_item()`](../apps/api/src/services/douyin_extension_capture_service.py:1154) already persists display-ready `posted_text` plus preserved `posted_text_raw` and `posted_display`.
- Backend response hydration in [`hydrate_card_grid_metadata()`](../apps/api/src/schemas/capture_inbox.py:117) was the remaining gap for legacy items that only stored raw relative text.
- Frontend Tile Gallery resolver in [`resolvePosted()`](../apps/web/src/lib/captureInboxCanonical.ts:45) already prefers `posted_at` then `posted_text`, so no UI redesign was required once backend response hydration became display-safe.
- Web contract drift existed because [`CapturedItem`](../apps/web/src/types/capture-inbox.ts:48) did not expose `posted_text_raw` or `posted_display` even though the backend response model already did.

## Changes Applied
- [`CapturedItemResponse`](../apps/api/src/schemas/capture_inbox.py:28) now runs lazy posted normalization during response hydration via [`_lazy_normalize_legacy_posted()`](../apps/api/src/schemas/capture_inbox.py:425).
- Legacy raw relative strings are parsed in [`_parse_relative_douyin_posted()`](../apps/api/src/schemas/capture_inbox.py:493) using item update/create timestamps as reference time.
- Display formatting is centralized in [`_format_posted_display()`](../apps/api/src/schemas/capture_inbox.py:484), returning `dd/mm/yyyy` for hydrated response values.
- [`CapturedItem`](../apps/web/src/types/capture-inbox.ts:48) now includes `posted_text_raw` and `posted_display`, and its source unions now match the backend’s expanded canonical source values.
- [`capture-inbox-canonical.test.ts`](../apps/web/src/test/capture-inbox-canonical.test.ts:18) now models display-ready posted fields instead of assuming raw fallback text for canonical items.

## Lazy Normalization Rules
- If `posted_at` exists and `posted_display` is absent, response hydration derives `posted_display` from the timestamp.
- If `posted_at` and `posted_display` are both absent but raw posted evidence is a parseable relative Douyin token, the response lazily derives:
  - `posted_text_raw`
  - `posted_at`
  - `posted_display`
  - display-ready `posted_text`
- If raw posted text is not confidently parseable, the response preserves the raw text and does not invent a date.

## Validation
- Passed: [`python -m unittest tests.test_capture_inbox_metadata_status`](../apps/api/tests/test_capture_inbox_metadata_status.py)
- Passed: [`npx tsx src/test/capture-inbox-canonical.test.ts`](../apps/web/src/test/capture-inbox-canonical.test.ts)
- Known unrelated failure when using workspace test script: [`npm test`](../apps/web/package.json) still routes through other path-sensitive tests and is not a Phase 22B-14A regression.
