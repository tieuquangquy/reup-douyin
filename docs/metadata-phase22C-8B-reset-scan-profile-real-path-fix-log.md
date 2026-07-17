# Phase 22C-8B Reset/Scan Profile Real Path Fix Log

## Scope
- Phase: 22C-8B - Kill false profile_scan_incomplete after Reset and trace real Scan Profile path.
- Workspace: apps/extension-douyin-capture.
- Backend Capture Inbox, Review Board, Reup Score, crawler rewrites, and calibration removal were intentionally out of scope.

## Emitters Found
- `apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts` in `completeProfileVerify` is the only runtime path that can emit `profile_scan_incomplete`.
- `apps/extension-douyin-capture/src/wholeProfileHarvest/errors.ts` defines the code/message only.
- `apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts` contains test references only.

## Root Cause
- Scan Profile routes through `runScanProfileWorkflow` -> `verifyProfile` -> `completeProfileVerify`.
- The previous fix targeted an inline completeness condition but did not provide a central classifier for all post-scan failure cases.
- After Reset, stale scan/expected-count diagnostics could leave the real Scan Profile path reporting `profile_scan_incomplete` even when no scan round had started.
- Reset diagnostics were also incomplete in the visible popup path, so operator diagnostics could show `none` for reset result/storage write.

## Changes Made
- Added Phase 22C-8B runtime markers: `scanner_runtime_version`, build timestamp, scan controller version, reset controller version, and primary action selector version.
- Added `classifyProfileScanFailure(context)` in the controller.
- Enforced the hard rule that `scan_rounds <= 0` never maps to `profile_scan_incomplete`.
- Mapped zero-round failures to more accurate codes such as `profile_grid_not_ready_timeout`, `profile_scan_preflight_failed`, or `profile_scan_no_round_started`.
- Added new error codes/messages for no-round/preflight/stale expected-count outcomes.
- Made reset success diagnostics durable in the controller and added popup click/failure diagnostics for the user-facing Reset path.
- Confirmed the Reset modal calls the canonical controller path: `resetScannerWorkflowState(createWholeProfilePopupRuntime(), ...)`.
- Exposed runtime/reset diagnostics in the scanner view model.
- Added tests for the central classifier, rescan reset diagnostics, and zero-round no-incomplete behavior.

## Notes
- `current_run` reset intentionally preserves profile scan state/queue; rescan/new-profile resets clear profile scan state and expected count.
- Manual acceptance that expects `Reset cleared profile scan state: yes` should use the rescan/new-profile reset mode, not current-run reset.
