# Phase 22C-2C — Posted Date Format Capture Resume

## Current Status

Phase 22C-2C implementation is complete pending final validation commands.

## Files Changed

- `apps/extension-douyin-capture/src/wholeProfileHarvest/canonicalHarvest.ts`
- `apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts`
- `apps/extension-douyin-capture/src/popup.ts`
- `apps/extension-douyin-capture/src/types.ts`
- `apps/api/src/schemas/capture_inbox.py`
- `apps/api/tests/test_capture_inbox_metadata_status.py`
- `docs/metadata-phase22C-2C-posted-all-date-formats-log.md`
- `docs/metadata-phase22C-2C-posted-all-date-formats-resume.md`

## Behavior Summary

The canonical extension parser now normalizes raw Posted strings before parsing, including leading separator removal and author-prefix removal. Month/day dates without a year use the configured reference time. If the inferred date is more than seven days in the future, the parser selects the previous year.

The active modal fallback extractor now recognizes `4月28日` and `@作者 · 4月28日` as Posted candidates and passes them to the canonical parser. Backend response hydration lazily normalizes legacy raw Posted values using equivalent format support so existing saved raw values can display as `dd/mm/yyyy` when parseable.

## Validation To Run

- `npm --workspace @reup-douyin/extension-douyin-capture run test`
- `npm --workspace @reup-douyin/extension-douyin-capture run typecheck`
- `npm --workspace @reup-douyin/extension-douyin-capture run build`
- Focused backend test: `python -m pytest apps/api/tests/test_capture_inbox_metadata_status.py`

## Manual Retest

1. Rebuild/reload the extension.
2. Open a Douyin profile with modal rows showing `· 4月28日` or `@作者 · 4月28日`.
3. Run Start Collecting for one item and safe batch.
4. Confirm payload/debug values include raw Posted text, parsed `posted_at`, `posted_display` as `28/04/<year>`, and parser diagnostics.
5. Confirm Capture Inbox card shows `Posted: 28/04/<year>` instead of `Not captured`.
6. Confirm an unparseable raw Posted string remains raw-only and does not create a fake date.
