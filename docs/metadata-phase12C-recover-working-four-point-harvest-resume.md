# Phase 12C Recover Working Four-Point Harvest Resume

## Current state

Phase 12C implementation is complete and verified for the extension.

The restored production workflow is:

1. Smart Capture & Harvest captures the profile and stores explicit capture session binding.
2. Right Rail Calibration requires four clicks only:
   - like
   - comment
   - favorite
   - share
3. Probe Current Modal Metrics reads four calibrated metric points and active video duration.
4. PASS probe allows Smart Capture & Harvest to start.
5. Harvest extracts each modal item, queues/flushed backend updates, and automatically navigates to the next video without requiring a calibrated next-video point.
6. Progress UI continues to show current video, phase, aweme, metrics, counts, ETA, navigation diagnostics, and recent items.

## Files changed

- `apps/extension-douyin-capture/src/types.ts`
  - Added `calibrated_four_point_workflow` calibration version.
  - Added `page_down_fallback` navigation result.

- `apps/extension-douyin-capture/src/contentScript.ts`
  - Restored four-click calibration overlay.
  - Saves `calibrated_four_point_workflow`.
  - Accepts the new four-point version.
  - Removed harvest start/resume hard blocks for missing `next_video_button`.

- `apps/extension-douyin-capture/src/popupWorkflow.ts`
  - Requires only four metric points for valid calibration.
  - Replaced five-point/next-point message with four-point incomplete message.
  - Smart Capture guard no longer blocks on missing next point.

- `apps/extension-douyin-capture/src/popup.ts`
  - Removed production next-point messaging.
  - Show Calibration displays `4/4` point count.
  - Accepts `calibrated_four_point_workflow`.

- `apps/extension-douyin-capture/src/modalHarvest.ts`
  - Navigation no longer returns `no_next_point_calibrated` before trying automatic next.
  - Automatic navigation now tries legacy calibrated point if present, DOM next control, ArrowDown, PageDown, wheel, and focus+ArrowDown before timing out.

- `apps/extension-douyin-capture/public/popup.html`
  - Calibration helper text now documents four points only.

- `apps/extension-douyin-capture/src/popupProgress.ts`
  - Removed five-point recalibration guidance from progress error copy.

- Tests updated:
  - `apps/extension-douyin-capture/src/popupWorkflow.test.ts`
  - `apps/extension-douyin-capture/src/modalHarvest.test.ts`
  - `apps/extension-douyin-capture/src/popupProgress.test.ts`

- Docs added:
  - `docs/metadata-phase12C-recover-working-four-point-harvest-log.md`
  - `docs/metadata-phase12C-recover-working-four-point-harvest-resume.md`
  - `docs/metadata-phase12C-final-four-point-operator-guide.md`

## Audit note

Git history was requested, but unavailable in this workspace: `git` reported “fatal: not a git repository”. Exact regression points were identified from the current source and regression tests instead.

## Verification already passed

```bash
npm --workspace @reup-douyin/extension-douyin-capture run test
npm --workspace @reup-douyin/extension-douyin-capture run typecheck
npm --workspace @reup-douyin/extension-douyin-capture run build
```

## Non-goals preserved

- No backend changes.
- No broad web changes.
- No new extraction strategy.
- No CDP/debug buttons reintroduced as normal UI.
- No manual next click required for every video.
- No five-point production calibration requirement.
