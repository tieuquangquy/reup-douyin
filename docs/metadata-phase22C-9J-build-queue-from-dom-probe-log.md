# Phase 22C-9J Build Queue From DOM Probe Log

## Summary
Implemented Phase 22C-9J so a successful post-ping DOM probe can complete Scan Profile even when the legacy content-script profile scan runner exits before starting rounds.

## Audit Findings
- DOM probe result is received by `verifyProfile()` via `runtime.runPostPingProfileDomProbe22C9I()` and persisted into `debug.last_request_summary` / `debug.last_response_summary`.
- After probe success, `completeProfileVerify()` starts `scanWholeProfileTargets()`.
- The background `scanProfile()` reads probe diagnostics but still calls `REUP_DOUYIN_MODAL_TEST_SCAN_PROFILE`.
- DOM probe candidates were not passed into a queue builder.
- Round 1 only started if the legacy content-script scanner produced diagnostics rounds.
- `scanRounds` stayed 0 when the runner failed before rounds.
- Queue persisted only after classification of scanner targets, so probe-only candidates never reached `harvest.queue`.
- `profileScanReady` was only set in the successful scanner/classification finalizer.
- Generic `profile_scan_failed` came from profile scanner failure mapping when the runner returned an unmapped reason.
- `specific_scan_error` and `scan_no_round_reason` stayed none because the failing path did not derive specific probe candidate/queue errors.

## Changes
- Added `normalizeProfileDomProbeCandidates22C9J(probeResult, profileUrl)`.
- Added `buildProfileScanQueueFromCandidates22C9J(candidates, state)`.
- Added DOM-probe fallback finalization in `completeProfileVerify()` for scan runner failure or zero rounds.
- Added specific error codes for candidate normalization, queue persistence, and readiness finalization failures.
- Added tests for candidate extraction priority, dedupe/invalid counts, queue entries, fallback wiring, completed probe status, and readiness guard.

## Validation
- Typecheck was run during implementation and passed.
- Full test/typecheck/build validation is required before final handoff.
