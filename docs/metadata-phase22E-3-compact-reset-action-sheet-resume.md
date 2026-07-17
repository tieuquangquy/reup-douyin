# Phase 22E-3 Compact Reset Action Sheet Resume

## Files Changed
- `apps/extension-douyin-capture/public/popup.html`
- `apps/extension-douyin-capture/public/popup.css`
- `apps/extension-douyin-capture/src/popup.ts`
- `apps/extension-douyin-capture/src/wholeProfileHarvest.viewModel.test.ts`
- `docs/metadata-phase22E-3-compact-reset-action-sheet-log.md`
- `docs/metadata-phase22E-3-compact-reset-action-sheet-resume.md`

## Implementation Notes
- Replaced the tall reset option cards with compact action rows.
- Kept the same reset modes: `current_run`, `current_profile_rescan`, `new_profile`.
- Added inline Switch profile confirmation before dispatching `new_profile`.
- Added hidden inline error message and failure handling that keeps the modal open.
- Added recommended badges driven by local diagnostics only.
- Kept backend calls out of the reset rendering path.

## Test Coverage Updated
Source-inspection tests now assert:

- Compact title/subtitle/footer copy.
- New labels: `Fix stuck run`, `Refresh profile`, `Switch profile`.
- Old long card copy is absent.
- Inline Switch profile confirmation exists and dispatches `new_profile` only after confirm.
- Recommended badge hooks exist.
- Running state disables rows and shows `Resetting...`.
- Reset path avoids backend save/delete APIs.
- Capture Inbox and Advanced panel wiring remains intact.

## Manual Retest Steps
1. Open the extension popup and click `Reset`.
2. Confirm the action sheet fits without scrolling and shows the three compact rows.
3. Press Escape and confirm the modal closes.
4. Reopen Reset, click `Fix stuck run`, and verify the current-run reset succeeds.
5. Reopen Reset, click `Refresh profile`, and verify rescan reset succeeds.
6. Reopen Reset, click `Switch profile`, verify the inline confirmation appears, then cancel.
7. Reopen Switch profile confirmation and confirm; verify the success message says `Ready for a new profile. Open a Douyin profile and click Scan Profile.`
8. Open Capture Inbox and Advanced from the popup footer to confirm both still work.

## Validation Commands
Run from repository root:

```sh
npm --workspace @reup-douyin/extension-douyin-capture run test
npm --workspace @reup-douyin/extension-douyin-capture run typecheck
npm --workspace @reup-douyin/extension-douyin-capture run build
```
