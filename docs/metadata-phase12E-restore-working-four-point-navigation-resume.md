# Phase 12E Restore Working Four-Point Navigation Resume

## Scope completed

Phase 12E restored automatic next-video navigation for the existing four-point Smart Capture & Harvest workflow in `apps/extension-douyin-capture` only.

No backend, web app, CDP/debug workflow, database schema, broad metric extraction, or fake metric changes were made.

## Audit result

The required git commands were attempted first, but the terminal reported that the workspace is not a Git repository. Because `.git` history is unavailable, the recovery used documented phase history and current source.

The decisive documentation trail was:

- Phase 12C restored four-point harvest and documented navigation order as existing modal next-control discovery first, followed by ArrowDown, PageDown, wheel, and focus plus ArrowDown.
- Phase 12D changed production navigation to keyboard-first and pushed next-control discovery to the last fallback.
- The live bug showed keyboard-first retries timed out on the same aweme.

## Root cause

`navigateNextModalAutomatically()` had regressed from the Phase 12C working order. It tried keyboard/wheel first and clicked the next-control heuristic only last. On the live Douyin modal page, that did not trigger the same navigation handlers, so the page stayed on the same aweme until `modal_id_change_timeout`.

## Files changed

- `apps/extension-douyin-capture/src/modalHarvest.ts`
- `apps/extension-douyin-capture/src/modalHarvest.test.ts`
- `docs/metadata-phase12E-restore-working-four-point-navigation-log.md`
- `docs/metadata-phase12E-restore-working-four-point-navigation-resume.md`
- `docs/metadata-phase12E-final-four-point-harvest-operator-guide.md`

## Restored navigation behavior

`navigateNextModalAutomatically()` now attempts:

1. modal next-control discovery/click
2. focus + `ArrowDown`
3. `PageDown`
4. wheel down
5. focus + `ArrowDown` retry

Keyboard and wheel events are broadcast to `window`, `document`, active element, active video, body, and document element so global Douyin modal handlers can receive them.

## Preserved behavior

- Production calibration is four points only.
- `next_video_button` is not required.
- Probe PASS works with four calibrated metric points.
- No normal progress UI row says `Next point: missing`.
- Current item is not counted as duplicate immediately after extraction.
- Posted metadata behavior is unchanged.
- No fake view metrics were introduced.

## Verification

Passed:

```bash
npm --workspace @reup-douyin/extension-douyin-capture run test
npm --workspace @reup-douyin/extension-douyin-capture run typecheck
npm --workspace @reup-douyin/extension-douyin-capture run build
```

## Resume handoff

If additional validation is needed, perform only live retesting with the built extension:

1. Load `apps/extension-douyin-capture/dist`.
2. Open a Douyin `modal_id` page.
3. Use four-point calibration and Probe PASS.
4. Start Smart Capture & Harvest for more than one item.
5. Verify automatic modal advancement and continued extraction for Video 2+.
