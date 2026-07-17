# Phase 21D-3 Visual Polish Compact Control Panel Log

## Scope

Implemented Phase 21D-3 only for the Douyin Capture extension popup main screen. This pass was limited to popup layout, CSS, display formatting, tests, and documentation.

## UI problems fixed

- Reworked the dark debug-like `scp-*` shell into a premium light control panel.
- Moved the health statuses into the hero so they read as compact inline chips instead of separate full-width rows.
- Converted the hero into a blue gradient product header with title, subtitle, video count badge, and inline health chips.
- Reduced the visual height of Mode, Batch, and Speed settings.
- Kept the primary action card focused on title, description, and primary button.
- Made bottom actions compact and aligned in a single row.

## Health chip changes

- Preserved the existing chip IDs and renderer wiring:
  - `scannerChipTab`
  - `scannerChipApi`
  - `scannerChipCalibration`
  - `scannerChipSafety`
- Moved the health row into the `scp-topbar` hero.
- Changed `.scp-health-row` from a four-column grid to inline flex chips.

## Primary action cleanup

- Kept the existing primary action title, helper text, and button IDs.
- Did not change the primary action handler or view-model logic.
- Updated card styling to a compact white card with subtle blue border and soft shadow.

## Duplicate alert removed

- The alert placeholder remains available for real disabled-action messages.
- Added an explicit `.scp-alert[hidden] { display: none; }` guard so the hidden alert cannot render as an empty brown/orange progress-like bar.
- The calibration-needed static copy remains once in the health chip row, with action guidance in the primary card description.

## Tests run

Passed:

```bash
npm --workspace @reup-douyin/extension-douyin-capture run test
npm --workspace @reup-douyin/extension-douyin-capture run typecheck
npm --workspace @reup-douyin/extension-douyin-capture run build
```

## Files changed

- `apps/extension-douyin-capture/public/popup.html`
- `apps/extension-douyin-capture/public/popup.css`
- `apps/extension-douyin-capture/src/ui20C1ActionDeck.test.ts`
- `apps/extension-douyin-capture/src/wholeProfileHarvest.tabs.test.ts`
- `docs/metadata-phase21D-3-visual-polish-control-panel-log.md`
- `docs/metadata-phase21D-3-visual-polish-control-panel-resume.md`
