# Scan Profile Auto Scroll Fix

## Root Cause

The confirmed failure was extension-side incomplete discovery. Scan Profile collected only the Douyin profile videos that were already rendered in the DOM. If the user manually scrolled to the bottom first, Douyin rendered more profile cards and the same scanner found more videos.

The backend/API, database, and calibration flow were not the cause. Calibration is still only required before Start Collecting.

## Files Changed

- `apps/extension-douyin-capture/src/contentScript.ts`
  - Hardened the active minimal Scan Profile discovery loop used by `DOUYIN_SCAN_PROFILE_MINIMAL_22C11B`.
  - Added safer scroll container selection, stronger synthetic scrolling, post-scroll render waits, re-extraction after scroll, and richer convergence diagnostics.

## Relevant Files Inspected

- `apps/extension-douyin-capture/src/wholeProfileHarvest/profileScanner.ts`
- `apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts`
- `apps/extension-douyin-capture/src/contentScript.ts`
- `apps/extension-douyin-capture/src/background.ts`
- `apps/extension-douyin-capture/src/wholeProfileHarvest/targetValidation.ts`
- `apps/extension-douyin-capture/src/wholeProfileHarvest/profileResolver.ts`

## Responsible Functions

- Scan rounds: `collectActiveWorksGridTargetsUntilStable22C11B` in `contentScript.ts`.
- Scroll action: `dispatchSyntheticWheelFlick22C11B` in `contentScript.ts`.
- Convergence detection: `collectActiveWorksGridTargetsUntilStable22C11B` in `contentScript.ts`.
- Queue building: `adaptCanonicalVerifiedTargets22C11B` in `background.ts`, fed by `runMinimalActiveTabProfileScan22C11B` in `contentScript.ts`.
- Profile card/aweme extraction: `collectActiveWorksGridTargets22C11B` and `extractModalAwemeId22C11B` in `contentScript.ts`.
- Stop reason `scroll_converged_queue_accepted_22C11B`: `terminalStateFromReconciliation22C11B` in `background.ts`. This is a reconciled success label after queue acceptance, not the low-level scroll loop stop reason.

## Algorithm Before

1. Extract currently visible profile anchors.
2. Stop as soon as bottom is detected after 12 rounds.
3. Stop after 3 no-new rounds after 12 rounds.
4. Dispatch wheel events and wait 1500 ms.
5. Diagnostics recorded count and a small stop reason, but did not prove stable scroll geometry or multiple stable bottom rounds.

This was too optimistic for Douyin lazy loading and could accept a partially rendered grid.

## Algorithm After

1. Extract visible profile anchors before scrolling each round.
2. Scroll both the likely active profile scroll element and window/document fallbacks.
3. Scroll the last visible video/card into view to trigger lazy loading sentinels.
4. Wait 2200 ms after scroll for Douyin to render the next batch.
5. Extract visible profile anchors again after the render wait.
6. Track unique aweme IDs across all rounds.
7. Stop only after safer convergence:
   - at least 12 rounds have run,
   - bottom is stable for 3 rounds,
   - and no new unique videos appeared for 3 bottom-stable rounds; or
   - no new unique videos for 6 rounds with stable scroll geometry; or
   - login/captcha/checkpoint is detected; or
   - max rounds/time cap is reached.
8. Keep hard safety caps: 80 rounds and 120 seconds.

## Diagnostics Added

- `active_works_scroll_scan_version`
- `active_works_scroll_max_rounds`
- `active_works_scroll_max_duration_ms`
- `active_works_scroll_render_wait_ms`
- `active_works_scroll_no_new_patience`
- `active_works_stable_bottom_rounds`
- `active_works_stable_geometry_rounds`
- `active_works_blocked_reason`
- Per-round:
  - `new_count`
  - `total_count`
  - `no_new_scroll_attempts`
  - `stable_bottom_rounds`
  - `stable_geometry_rounds`
  - `scroll_top_before`
  - `scroll_top_after`
  - `scroll_height_before`
  - `scroll_height_after`
  - `scroll_remaining_after`
  - `scroll_geometry_stable`
  - `blocked_reason`
  - synthetic wheel event details

## Validation Commands

Run from the repository root:

```powershell
npm --workspace @reup-douyin/extension-douyin-capture run build
npm --workspace @reup-douyin/extension-douyin-capture run test
npx --workspace @reup-douyin/extension-douyin-capture tsx src/networkCache.test.ts
```

Observed validation:

- Build passed: `npm --workspace @reup-douyin/extension-douyin-capture run build`.
- Focused unrelated smoke test passed: `npx --workspace @reup-douyin/extension-douyin-capture tsx src/networkCache.test.ts`.
- Full extension test suite currently fails before scanner-specific assertions on pre-existing runtime-marker expectations for `22C-12F` while the current source exposes `22C-11B` markers. This failure was not introduced by the auto-scroll change.

## Manual Test Steps

1. Build the extension.
2. Reload the built extension in Chrome.
3. Open a Douyin profile without manually scrolling.
4. Click Scan Profile once.
5. Confirm discovered/queued count is close to the count obtained after manual scrolling.
6. Confirm primary action becomes Start Collecting when calibration is ready.
7. Repeat on a profile that was already manually scrolled and confirm no regression.
8. Test a login/captcha/checkpoint state and confirm the scan stops with clear diagnostics instead of a misleading partial success.

## Remaining Risks

- Douyin may require real human wheel/input cadence for some profiles; synthetic scroll plus scrollIntoView may still not trigger every network pagination case.
- Virtualized grids can remove older DOM nodes, so the scan relies on extracting and preserving IDs every round.
- Very large profiles may hit the 120 second cap before full discovery; increase caps only after observing diagnostics.
- The passive network probe still depends on whether Douyin emits profile post network batches during extension-driven scrolling.
