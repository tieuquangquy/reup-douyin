# Phase 22C-8B Reset/Scan Profile Real Path Fix Resume

## Current State
- Phase 22C-8B implementation is in progress in `apps/extension-douyin-capture`.
- Modified code files:
  - `src/wholeProfileHarvest/controller.ts`
  - `src/wholeProfileHarvest/errors.ts`
  - `src/wholeProfileHarvest/viewModel.ts`
  - `src/popup.ts`
  - `src/wholeProfileHarvest.test.ts`
- Added docs:
  - `docs/metadata-phase22C-8B-reset-scan-profile-real-path-fix-log.md`
  - `docs/metadata-phase22C-8B-reset-scan-profile-real-path-fix-resume.md`

## Implemented
- Runtime marker `scanner_runtime_version = "22C-8B"` and related version diagnostics.
- Central `classifyProfileScanFailure(context)` helper.
- Zero-round scan guard: `scan_rounds <= 0` cannot emit `profile_scan_incomplete`.
- Reset success diagnostics in controller for current-run, current-profile-rescan, and new-profile reset modes.
- Popup Reset clicked/failure diagnostics with Phase 22C-8B runtime markers.
- View model rows for runtime/build/controller/reset diagnostics.
- Tests for classifier, reset diagnostics, and zero-round failure behavior.

## Remaining Validation
- Run extension tests, typecheck, and build:
  - `npm --workspace @reup-douyin/extension-douyin-capture run test`
  - `npm --workspace @reup-douyin/extension-douyin-capture run typecheck`
  - `npm --workspace @reup-douyin/extension-douyin-capture run build`
- If tests fail, first inspect:
  - `wholeProfileHarvest.test.ts` zero-round expected error message.
  - TypeScript import list in `wholeProfileHarvest.test.ts`.
  - Popup constants duplicated with controller constants.

## Manual Retest
1. Load the rebuilt extension.
2. Open a Douyin profile page.
3. Open Advanced diagnostics and confirm `Scanner runtime version` is `22C-8B`.
4. Use Reset -> rescan current profile.
5. Confirm diagnostics show reset result/storage write success and `Reset cleared profile scan state: yes`.
6. Click Scan Profile.
7. Confirm a zero-round/preflight/grid failure is not reported as `profile_scan_incomplete`.
8. If the profile grid is ready, confirm scan rounds start and Start Collecting remains available after a successful scan.
