# Phase 22C-9 - Extension Scanner State Machine Hardening Log

## Why Scan Profile Broke After Reset Refactor
Reset UX split into current-run reset, current-profile rescan, and new-profile switching. That made transient collection state, durable profile-scan state, calibration state, and backend session state overlap in storage. The bad visible state was `scanRounds=0` with `profile_scan_incomplete`, which is impossible because incomplete scans require at least one started scan round.

## Correct Scanner State Machine
Profile Scan discovers cards and builds the queue. Calibration only gates modal extraction and Start Collecting. Collection owns current item, pause/resume, and extraction progress. Backend Session owns Capture Inbox session readiness. Reset chooses which state groups are preserved or cleared.

## State Groups And Ownership
- Profile scan: `profile_scan`, `verify`, `classification`, `target_status`, queue planning.
- Calibration: `calibration` and canonical four-point readiness.
- Collection: `workflow.collection`, `harvest.current_*`, pause/resume, results, counters.
- Backend session: `capture_session_id`, `harvest.backend.capture_session`, flush previews/results.
- UI/action: `workflow.active_task`, `workflow.action_lock`, `debug.last_action_*`.
- Reset/legacy: `debug.last_request_summary`, `debug.last_response_summary`, `debug.legacy_state_summary.storage_state_audit`.

## Primary Action Selector Order
Pause and resume outrank idle actions. Scan/classify busy keeps Scan Profile visible. Missing profile scan or classification returns Scan Profile before any calibration action. A queued profile with missing calibration returns Calibrate 4 Points. A queued profile with calibration ready returns Start Collecting.

## Scan Profile Independence From Calibration
`getCanonicalScannerPrimaryAction` now records 22C-9 decision traces and keeps Scan Profile enabled before calibration. Scan Profile does not read calibration as a preflight requirement.

## Expected Count Safety
Scan diagnostics now include `scan_run_id` and `expected_count_scan_run_id` so expected-count metadata can be tied to the current profile scan run instead of surviving as anonymous stale state after reset.

## Legacy State Quarantine
Normalized scanner state records `storage_state_audit` under `debug.legacy_state_summary`. Canonical state wins; legacy state is marked quarantined instead of being allowed to drive primary action decisions.

## State Validator Invariants
`validateScannerState` repairs `scanRounds=0 + profile_scan_incomplete` to `profile_scan_no_round_started`, records `scan_error_normalizer_applied=yes`, and exposes validator diagnostics.

## Diagnostics Added
- `scanner_runtime_version=22C-9`
- `state_machine_version=22C-9`
- `scan_controller_version=22C-9-scan-controller`
- `reset_controller_version=22C-9-reset-controller`
- `primary_action_selector_version=22C-9-primary-action-selector`
- Primary action snake_case decision trace fields
- Profile scan, calibration, collection, backend, reset, and storage audit summaries in advanced diagnostics

## Tests Run
Typecheck was run after the initial implementation slice and passed.

## Manual Retest Checklist
1. Open a fresh Douyin profile with no calibration and confirm the primary action is Scan Profile.
2. Click Scan Profile and confirm no calibration prompt blocks profile grid scanning.
3. After scan queue is built, confirm missing calibration changes the primary action to Calibrate 4 Points.
4. Complete four-point calibration and confirm the primary action becomes Start Collecting.
5. Use current-run reset and confirm queue/profile scan state remain while transient collection state clears.
6. Use current-profile rescan and confirm scan queue and expected-count state clear.
7. Switch to a new profile and confirm old profile/session/queue state does not drive the new profile.
8. Confirm Advanced diagnostics show 22C-9 versions and no `profile_scan_incomplete` when scan rounds are zero.
