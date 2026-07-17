# Phase 6H Performance Fix Log

## Why this fix is needed

- Phase 6H full modal harvest is already able to detect `aweme_id`, extract duration, flush to backend, and persist one item.
- The remaining blocker is performance coverage, not transport or persistence.
- Live evidence shows `duration_seconds` is usable, while `like_count` and `comment_count` are still missing often enough that `performance_status` remains missing.
- The profile grid already exposes a trustworthy per-video like count on the anchor for the same `aweme_id`, so that fallback should be used when modal like extraction is not confident.

## Confirmed pre-fix issues

1. Modal side-action extraction still misses like/comment on some real Douyin modal layouts.
2. There is no exact-`aweme_id` fallback from the visible profile grid card for `like_count`.
3. Performance can stay missing even when a high-confidence grid like count exists.
4. Existing duration logic is already acceptable and should remain unchanged.

## Scope

- `apps/extension-douyin-capture`
- tiny backend source-label alignment only if needed
- focused tests/docs only

## Non-goals

- no fake `view_count`
- no backend browser crawling
- no captcha bypass
- no harvest architecture rewrite

## Planned fix

1. Add exact-`aweme_id` profile-card fallback for `like_count`.
2. Keep modal side-action extraction as the preferred source when it is confidently identified.
3. Leave `comment_count` / `share_count` null when the modal block is ambiguous.
4. Emit explicit source/diagnostic fields in `raw_dom_detail_metrics`.
5. Preserve current duration conflict handling.

## Files expected

- `apps/extension-douyin-capture/src/modalHarvest.ts`
- `apps/extension-douyin-capture/src/modalHarvest.test.ts`
- `apps/extension-douyin-capture/src/types.ts`
- `apps/extension-douyin-capture/src/popup.ts`
- `apps/api/src/services/capture_metadata_normalizer.py`
- `apps/api/src/schemas/douyin_extension.py`
- `apps/api/src/schemas/capture_inbox.py`
- `apps/api/tests/test_capture_metadata_normalizer.py`
- `docs/metadata-phase6H-performance-fix-log.md`
- `docs/metadata-phase6H-performance-fix-resume.md`

## Implemented fix

1. Full Modal Harvest now falls back to the visible profile-grid anchor for `like_count` when modal like extraction is missing.
2. The fallback is keyed by exact `aweme_id` through `a[href*="/video/{aweme_id}"]`.
3. Only the first non-empty anchor text line is considered for profile-card fallback, and decimal/rating-like text is rejected.
4. Modal action-block extraction remains the preferred source for modal like/comment/share when the block is confidently identified.
5. Per-field source diagnostics are now carried in `raw_dom_detail_metrics`.
6. A narrow backend normalizer alignment preserves `dom_profile_card_fallback` as the canonical `like_count_source`.

## Files changed

- `apps/extension-douyin-capture/src/modalHarvest.ts`
- `apps/extension-douyin-capture/src/modalHarvest.test.ts`
- `apps/extension-douyin-capture/src/types.ts`
- `apps/api/src/services/capture_metadata_normalizer.py`
- `apps/api/src/schemas/douyin_extension.py`
- `apps/api/src/schemas/capture_inbox.py`
- `apps/api/tests/test_capture_metadata_normalizer.py`
- `docs/metadata-phase6H-performance-fix-log.md`
- `docs/metadata-phase6H-performance-fix-resume.md`

## Tests run

- `cd apps/extension-douyin-capture && npm run typecheck`
- `cd apps/extension-douyin-capture && npm test`
- `cd apps/api && python -m unittest tests.test_capture_metadata_normalizer`
- `cd apps/api && python -m unittest tests.test_douyin_extension_capture_service tests.test_capture_metadata_normalizer`
- `cd apps/api && python -m compileall src`

## Verification result

- extension typecheck passed
- extension test suite passed
- backend focused normalizer/ingest tests passed
- backend compile check passed

## Status

- implementation complete
