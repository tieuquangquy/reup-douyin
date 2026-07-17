# Phase 22E-1 Reset/Profile Switch Resume

Status: implemented, pending final validation pass.

## Changed Files

- `apps/extension-douyin-capture/src/wholeProfileHarvest/profileResolver.ts`
- `apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts`
- `apps/extension-douyin-capture/src/popup.ts`
- `apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts`
- `apps/extension-douyin-capture/src/wholeProfileHarvest.viewModel.test.ts`
- `docs/metadata-phase22E-1-reset-profile-switch-log.md`
- `docs/metadata-phase22E-1-reset-profile-switch-resume.md`
- `docs/douyin-extension-reset-and-profile-switch-guide.md`

## Behavior

Reset now has explicit semantics:

- Reset current run: keeps current profile plan, queue, session, settings, and calibration.
- Rescan this profile: clears local scan/classification/queue/session/counters for the same profile; keeps settings and calibration.
- Start new profile: clears old profile local plan/session/queue/counters and stores the detected active profile as the next profile to scan.
- Full local reset dev only: clears local scanner state and calibration.

Start Collecting now checks active tab profile identity against scanner state and blocks mismatches before session reuse or queue collection.

## Notes

No crawler extraction logic, backend item save logic, backend Capture Inbox data deletion, Batch Next 10 runner, or legacy runner path was changed.
