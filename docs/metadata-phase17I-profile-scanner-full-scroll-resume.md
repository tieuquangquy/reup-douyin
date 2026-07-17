# Phase 17I profile scanner full-scroll resume

## Completed

- Updated the isolated Modal Whole Profile Test scanner to target full profile collection rather than the first visible batch.
- Added scroll-container scoring and diagnostics.
- Added a stable collection loop with per-round extraction, selected-container scrolling, lazy-load waits, stable-round stopping, bottom detection, max-round/time limits, and scroll-failure reporting.
- Preserved virtualized-grid results by accumulating cards in a persistent aweme ID map.
- Added suspicious low-count warning output (`profile_scan_low_count`) without blocking `can_harvest_whole_profile` when cards are found.
- Kept verify-only behavior isolated to `douyinModalWholeProfileTestRun`.

## Files changed

- `apps/extension-douyin-capture/src/modalWholeProfileTest.ts`
- `apps/extension-douyin-capture/src/popup.ts`
- `apps/extension-douyin-capture/src/modalWholeProfileTest.test.ts`
- `docs/metadata-phase17I-profile-scanner-full-scroll-log.md`
- `docs/metadata-phase17I-profile-scanner-full-scroll-resume.md`

## Live retest steps

1. Run the extension build.
2. Reload the unpacked extension in the browser.
3. Open a Douyin modal URL for the target profile.
4. In the popup, open Advanced/Beta.
5. Use Verify only and click Test Modal → Whole Profile Harvest.
6. Inspect the beta panel JSON:
   - `total_found` should be close to the actual profile video count when Douyin loads all cards.
   - `diagnostics.scan_rounds` should show scrolling rounds and new IDs collected across rounds.
   - `diagnostics.selected_scroll_container` should describe the internal scroll container if one is selected.
   - `diagnostics.stop_reason` should explain why collection stopped.
   - `reason` may be `profile_scan_low_count` if the count is still under 10.

## Non-goals preserved

- No backend-wide changes.
- No Tile Gallery changes.
- No modal metric extraction changes.
- No calibration changes.
- No CDP/debug workflow reintroduction.
- No Capture Inbox visible item creation in verify-only.
- No full-modal-harvest start or flush in verify-only.
