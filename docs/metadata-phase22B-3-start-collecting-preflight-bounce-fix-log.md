# Phase 22B-3 — Start Collecting preflight bounce fix log

## Scope

Implemented only the Start Collecting silent preflight bounce fix for the Douyin capture extension.

## Changes

- Marked the active visible Start Collecting button in `apps/extension-douyin-capture/src/popup.ts`.
- Added event cancellation for the active scanner primary action click path.
- Removed Start Collecting calibration sync before dispatch so preflight no longer mutates calibration into a transient Calibrate state.
- Added explicit Start Collecting clicked/preflight/opening/blocked/failed diagnostics.
- Added ordered one-item preflight checks for queue, target, calibration, backend session proof, modal URL, and runner availability.
- Added `opening_target` collection status and UI wording for Opening first video.
- Kept modal-first detail URL behavior and avoided direct `/video` fallback for profile-modal collection.

## Validation

- `npm --workspace @reup-douyin/extension-douyin-capture run test` passed.
- `npm --workspace @reup-douyin/extension-douyin-capture run typecheck` passed.
- `npm --workspace @reup-douyin/extension-douyin-capture run build` passed.
