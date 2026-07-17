# Douyin Serial Factor Fix Resume

## Current Rule

Proceed factor by factor only. Do not advance until the active factor has a documented passing verification gate.

## Status

- [x] Read `AGENTS.md`.
- [x] Create serial factor docs first.
- [x] Factor 1 — Identity / aweme_id mapping.
- [x] Factor 2 — Thumbnail extraction and binding.
- [x] Factor 3 — Duration + posted.
- [x] Factor 4 — Views / likes / comments.
- [x] Factor 5 — Preview / source link / media asset statuses.
- [x] Factor 6 — Backend persistence + API response correctness.
- [x] Factor 7 — Frontend rendering correctness and stale reuse prevention.
- [-] Final report.

## Active Factor

Final report only. Factor 1, Factor 2, Factor 3, Factor 4, Factor 5, Factor 6, and Factor 7 passed their verification gates.

## Evidence Available at Start

- Current repository code and tests.
- Previously created debugging docs in `docs`.
- No attached screenshots, HAR files, real request payloads, API responses, or logs are available in this task context.

## Factor 1 Result

Factor 1 passed after adding a behavioral identity gate in `apps/extension-douyin-capture/src/extractor.identity.test.ts` and wiring it into `apps/extension-douyin-capture/package.json`.

Verification passed:

- `npm --prefix apps/extension-douyin-capture run typecheck && npx --prefix apps/extension-douyin-capture tsx apps/extension-douyin-capture/src/extractor.identity.test.ts`
- `npm --prefix apps/extension-douyin-capture test`

## Factor 2 Result

Factor 2 passed after extending `apps/extension-douyin-capture/src/extractor.identity.test.ts` to prove thumbnail binding by matching `aweme_id`, DOM fallback when matched network metadata has no thumbnail, and no unmatched or missing-ID thumbnail fan-out.

Verification passed:

- `npm --prefix apps/extension-douyin-capture run typecheck && npx --prefix apps/extension-douyin-capture tsx apps/extension-douyin-capture/src/extractor.identity.test.ts`
- `npm --prefix apps/extension-douyin-capture test`
- `npm --prefix apps/web run typecheck && npx --prefix apps/web tsx apps/web/src/test/capture-inbox-canonical.test.ts`

## Factor 3 Result

Factor 3 passed after extending `apps/extension-douyin-capture/src/extractor.identity.test.ts` to prove duration and posted binding by matching `aweme_id`, rejecting default midnight network posted timestamps, using same-item DOM fallback, and preventing unmatched or missing-ID duration/posted fan-out.

Verification passed:

- `npm --prefix apps/extension-douyin-capture run typecheck && npx --prefix apps/extension-douyin-capture tsx apps/extension-douyin-capture/src/extractor.identity.test.ts`
- `npm --prefix apps/extension-douyin-capture test`
- `npm --prefix apps/web run typecheck && npx --prefix apps/web tsx apps/web/src/test/capture-inbox-canonical.test.ts`

## Factor 4 Result

Factor 4 passed after extending `apps/extension-douyin-capture/src/extractor.identity.test.ts` to prove view/like/comment binding by matching `aweme_id`, same-item DOM metric fallback when matched network metadata has no stats, nested `statistics` consistency, and no unmatched or missing-ID stats fan-out.

Verification passed:

- `npm --prefix apps/extension-douyin-capture run typecheck && npx --prefix apps/extension-douyin-capture tsx apps/extension-douyin-capture/src/extractor.identity.test.ts`
- `npm --prefix apps/extension-douyin-capture test`
- `npm --prefix apps/web run typecheck && npx --prefix apps/web tsx apps/web/src/test/capture-inbox-canonical.test.ts`

## Factor 5 Result

Factor 5 passed after narrowing backend media asset status derivation so extension capture cannot mark media assets `ready` without generated asset evidence. Preview and source-link derivation were already evidence-based; the backend regression test now proves absent assets yield `preview_status = missing`, `source_link_status = missing`, `media_asset_status = not_generated`, and `media_status = missing` even when the incoming payload requests `ready`.

Verification passed:

- `python -m unittest tests.test_douyin_extension_capture_service.DouyinExtensionCaptureServiceTests.test_build_item_keeps_preview_and_media_missing_when_assets_are_absent` from `apps/api`.
- `python -m unittest tests.test_douyin_extension_capture_service` from `apps/api`.
- `npm --prefix apps/extension-douyin-capture test`
- `npm --prefix apps/web run typecheck && npx --prefix apps/web tsx apps/web/src/test/capture-inbox-canonical.test.ts`

One initial verification command failed because it was run from the repository root without the API import path; the corrected command passed from `apps/api`.

## Factor 6 Result

Factor 6 passed after narrowing backend fallback semantics for canonical numeric fields. Backend persistence now preserves legitimate zero duration and zero view/like/comment counts instead of treating `0` as missing, item construction sets readiness booleans for API response validation, and promotion adapter stats projection uses explicit presence fallback.

Verification passed:

- `python -m unittest tests.test_douyin_extension_capture_service.DouyinExtensionCaptureServiceTests.test_build_item_and_response_preserve_zero_canonical_stats` from `apps/api`.
- `python -m unittest tests.test_douyin_extension_capture_service.DouyinExtensionCaptureServiceTests.test_build_item_persists_canonical_thumbnail_url` from `apps/api`.
- `python -m unittest tests.test_douyin_extension_capture_service` from `apps/api`.
- `npm --prefix apps/extension-douyin-capture test`
- `npm --prefix apps/web run typecheck && npx --prefix apps/web tsx apps/web/src/test/capture-inbox-canonical.test.ts`

## Factor 7 Result

Factor 7 passed after auditing the Capture Inbox frontend rendering path and making one narrow resolver fix. Gallery tiles use stable captured item IDs, tile/inspector metadata is resolved from the current item object, active item state is invalidated by item ID, inspector expanded text resets on item changes, and action raw/source diagnostics are cleared before each new action. The only frontend defect found was metric fallback precedence: raw nested alternate aliases (`play_count`, `digg_count`) could win over canonical nested `statistics.view_count` / `statistics.like_count` if direct response fields and `metadata_json` were absent. The resolver now prefers canonical nested keys before legacy aliases.

Verification passed:

- `npm --prefix apps/web run typecheck && npx --prefix apps/web tsx apps/web/src/test/capture-inbox-canonical.test.ts`.

One initial Factor 7 verification run failed because the new status scoping fixture placed status values inside `metadata_json` instead of direct API response fields. The fixture was corrected to represent the actual API contract, then verification passed.

## Next Required Step

Prepare the final factor-by-factor report. No further factor work is active.
