# Phase 21D-6 State Binding + Compact Settings Log

## Phase

21D-6 — Fix scanner state binding + compact empty state + collapsible settings

## Scope

Implemented display-only scanner popup polish for the active compact Douyin Scanner main screen. This phase stayed inside popup view model, markup, renderer, CSS, tests, and docs.

## Changes

- Added scanner control panel view-model fields for:
  - `profileScanned`
  - `headerStatus`
  - `emptyState`
  - settings summary text
- Updated scanner display binding so the compact popup no longer shows `0 videos` before profile scan.
- Broadened profile detection for display health to include profile page context, profile URLs, source URLs, and Douyin `/user/` URLs already present in state.
- Broadened calibration readiness display so calibrated state and point count cannot be overwritten by stale missing readiness fields.
- Added API display mapping for ready, idle, and offline states from existing persisted backend status and errors.
- Updated best-available profile count fallback to use scan/verify targets, target details, backend queue total, queue preview, and planned total.
- Added compact empty state behavior:
  - Before profile scan: `Scan profile to build collection plan.`
  - After scan with no eligible videos: `No eligible videos found.`
- Hid stats grid before profile scan and retained New / Incomplete / Already collected / Queue after scan.
- Added collapsed collection settings UI by default:
  - `Collection settings`
  - `New + incomplete · Next 10 · Safe`
  - `Edit` button
- Added settings expansion state using the existing popup UI preferences mechanism.
- Preserved existing Mode / Batch / Speed selects and existing change handlers.
- Preserved existing primary, pause/resume, Capture Inbox, Advanced, and Reset handlers.

## Files Changed

- `apps/extension-douyin-capture/src/wholeProfileHarvest/viewModel.ts`
- `apps/extension-douyin-capture/src/popup.ts`
- `apps/extension-douyin-capture/public/popup.html`
- `apps/extension-douyin-capture/public/popup.css`
- `apps/extension-douyin-capture/src/wholeProfileHarvest.viewModel.test.ts`
- `apps/extension-douyin-capture/src/ui20C1ActionDeck.test.ts`
- `docs/metadata-phase21D-6-state-binding-compact-settings-log.md`
- `docs/metadata-phase21D-6-state-binding-compact-settings-resume.md`

## Validation

Ran:

```bash
npm --workspace @reup-douyin/extension-douyin-capture run test
```

Result: passed. This workspace test script also ran the extension build and dist module resolution check.

## Notes

No scanner, backend, collector, calibration, save, API contract, or V2/legacy runtime behavior was changed.
