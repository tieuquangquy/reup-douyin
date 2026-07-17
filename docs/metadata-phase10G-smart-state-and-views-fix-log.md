# Phase 10G Smart State And Views Fix Log

## Root cause of stale `viewport_changed_significantly` state

The popup was rendering and reusing persisted `smartState` directly from storage even when the current calibration/viewport data no longer justified that blocking state.

That left these fields stale:

- `current_state = calibration_required`
- `last_error = viewport_changed_significantly`
- `next_required_action = recalibrate`

even when:

- calibration existed
- calibrated viewport matched current viewport
- last probe was already `PASS`

## Corrected Smart Capture state rules

- viewport warning is computed from current calibration + current viewport only
- if viewport is within threshold:
  - stale `viewport_changed_significantly` is cleared
  - `current_state` is reconciled away from `calibration_required`
  - `next_required_action` becomes workflow-appropriate again
- if calibration is missing:
  - `current_state = calibration_required`
  - next action = start calibration
- if viewport actually changed significantly:
  - `current_state = calibration_required`
  - next action = recalibrate

## Root cause of `Views 0`

The first Tile Gallery metric could still treat `view_count = 0` as a real value when provenance did not prove the value was captured.

That suppressed estimated-view rendering and left cards showing misleading `Views 0`.

## Real vs estimated view rendering rules

- real views:
  - use only when provenance/raw stats indicate the count is truly known
- estimated views:
  - only when real views are unknown and `like_count > 0`
  - low = `likes * 20`
  - base = `likes * 33`
  - high = `likes * 100`
- unknown views:
  - render `Views —`

## Files changed

- `apps/extension-douyin-capture/src/popupWorkflow.ts`
- `apps/extension-douyin-capture/src/popup.ts`
- `apps/extension-douyin-capture/src/popupWorkflow.test.ts`
- `apps/web/src/lib/captureInboxCanonical.ts`
- `apps/web/src/components/capture-inbox/CaptureInboxPage.tsx`
- `apps/web/src/test/capture-inbox.test.ts`
- `apps/web/src/test/capture-inbox-canonical.test.ts`

## Tests run

- `npm --workspace @reup-douyin/extension-douyin-capture run test`
- `npm --workspace @reup-douyin/extension-douyin-capture run typecheck`
- `npm --workspace @reup-douyin/extension-douyin-capture run build`
- `npx tsx apps/web/src/test/capture-inbox.test.ts`
- `npm --workspace @reup-douyin/web run typecheck`

## Verification result

- Extension tests passed
- Extension typecheck passed
- Extension build passed
- Web Capture Inbox test passed
- Web typecheck passed
