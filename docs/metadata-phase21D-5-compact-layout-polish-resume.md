# Phase 21D-5 Compact Layout Polish Resume

## Phase

21D-5 — Compact layout polish for Douyin Scanner popup.

## Completed changes

- Main popup markup now includes Phase 21D-5 `scanner-*` layout classes while retaining existing IDs and compatibility classes.
- Health statuses render inside `scanner-health-inline` as compact chips.
- Primary action renders as one compact `scanner-primary-card` with one primary button.
- Counters render through `scanner-stats-grid` and `scanner-stat`.
- Mode, Batch, and Speed render through `scanner-settings-compact`.
- Bottom actions render through `scanner-bottom-dock`.
- Hidden alert styling prevents the empty brown/orange bar.
- Static main-screen tests guard against duplicate calibration-needed text and forbidden technical elements.

## Logic boundaries

No scanner, backend, collector, calibration, save, API contract, queue, or V2/legacy runtime logic was intentionally changed. Existing handlers and element IDs are preserved.

## Files touched

- `apps/extension-douyin-capture/public/popup.html`
- `apps/extension-douyin-capture/public/popup.css`
- `apps/extension-douyin-capture/src/popup.ts`
- `apps/extension-douyin-capture/src/ui20B1CommandCenterShell.test.ts`
- `apps/extension-douyin-capture/src/ui20C1ActionDeck.test.ts`
- `apps/extension-douyin-capture/src/wholeProfileHarvest.tabs.test.ts`
- `apps/extension-douyin-capture/src/wholeProfileHarvest.viewModel.test.ts`
- `docs/metadata-phase21D-5-compact-layout-polish-log.md`
- `docs/metadata-phase21D-5-compact-layout-polish-resume.md`

## Validation status

Passed on 2026-05-07:

```bash
npm --workspace @reup-douyin/extension-douyin-capture run test
npm --workspace @reup-douyin/extension-douyin-capture run typecheck
npm --workspace @reup-douyin/extension-douyin-capture run build
```

## Manual retest focus

- Open the extension popup on a Douyin profile page.
- Confirm the top health statuses are inline chips, not full-width cards.
- Confirm no empty warning/progress bar appears above the primary button.
- Confirm calibration-needed copy appears only once on initial load.
- Confirm counters, settings, and bottom actions fit compactly without making the popup overly tall.
- Confirm Capture Inbox, Advanced, Reset, and primary action buttons still work.
