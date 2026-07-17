# Phase 22E-2 Reset Modal UX Resume

## Status

Phase 22E-2 is implemented and validated.

## Files Changed

- `apps/extension-douyin-capture/public/popup.html`
- `apps/extension-douyin-capture/public/popup.css`
- `apps/extension-douyin-capture/src/popup.ts`
- `apps/extension-douyin-capture/src/wholeProfileHarvest.viewModel.test.ts`
- `docs/metadata-phase22E-2-reset-modal-ux-log.md`
- `docs/metadata-phase22E-2-reset-modal-ux-resume.md`

## Implementation Notes

- Reset button now opens the custom `#scannerResetModal` dialog.
- Option cards dispatch existing reset modes via `data-reset-mode`:
  - `current_run`
  - `current_profile_rescan`
  - `new_profile`
- The modal closes on Cancel, Escape, backdrop click, or successful reset completion.
- Reset options are disabled and expose `aria-busy` while a reset is running.
- The old native reset-options prompt has been removed from the scanner reset path.
- Backend delete APIs are not called by the reset modal flow.

## Validation Commands

- `npm --workspace @reup-douyin/extension-douyin-capture run typecheck`
- `npm --workspace @reup-douyin/extension-douyin-capture run test`

## Manual Retest

1. Load the rebuilt extension popup.
2. Click footer Reset and verify the Reset scanner modal opens.
3. Click Cancel and verify the modal closes.
4. Reopen the modal and press Escape; verify it closes.
5. Reopen and select Reset current run; verify the success message says queue/session were kept.
6. Reopen and select Start new profile; verify the local profile state cleared message appears.
7. Confirm Capture Inbox, Advanced, and Batch Next 10 flows still work.
