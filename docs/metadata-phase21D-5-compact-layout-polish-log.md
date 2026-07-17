# Phase 21D-5 Compact Layout Polish Log

## Scope

Implemented Phase 21D-5 for the Douyin Scanner popup main screen only. This phase is UI/layout/CSS focused and does not change scanner, backend, collector, calibration, save, or API contract logic.

## Layout problems fixed

- Converted the active health status area into inline `scanner-health-inline` chips.
- Kept Profile, API, calibration, and safety status as compact chips instead of full-width status rows.
- Added the Phase 21D-5 `scanner-*` layout classes while preserving existing `scp-*` compatibility classes and all existing element IDs.
- Made the primary action area a compact `scanner-primary-card` focused on the next operator action.
- Made counters render through `scanner-stats-grid` and `scanner-stat` classes.
- Made Mode, Batch, and Speed render through compact `scanner-settings-compact` styling.
- Made bottom actions render as a compact `scanner-bottom-dock`.

## Full-width health rows removed

The main health area is now guarded by tests that require `scanner-health-inline` in the hero. The old separate TAB/API/CALIB/SAFETY card pattern remains forbidden on the main screen.

## Empty bar removed

The hidden alert keeps explicit hidden CSS through `.scanner-alert[hidden]` and `.scp-alert[hidden]`, so the calibration-needed state does not show an empty brown/orange progress-like bar.

## Duplicate alert removed

The static main screen keeps `Cal needed` only once in the health chip. The primary action description remains operator-facing and does not duplicate the calibration-needed warning.

## Main-screen focus

The main screen continues to exclude Queue Preview, Debug Details, Payload Guard, Flush Batch, and dry-run test actions. Those details remain outside the main flow in Results or Advanced panels where applicable.

## Tests run

Passed on 2026-05-07:

```bash
npm --workspace @reup-douyin/extension-douyin-capture run test
npm --workspace @reup-douyin/extension-douyin-capture run typecheck
npm --workspace @reup-douyin/extension-douyin-capture run build
```

The workspace test command also runs the extension build as part of its scripted test chain; the explicit build command was run again after typecheck for the requested Phase 21D-5 validation.
