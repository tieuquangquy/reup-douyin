# Phase 22E-1 Reset/Profile Switch Log

## Audit

Active popup Reset runs `resetWholeProfileHarvestStateFromPopup` -> `resetScannerWorkflowState` -> `resetHarvest`.

Current reset was hard-coded to `current_run`. It cleared transient run state: `run_id`, workflow locks, collection status, current index/aweme, pause flags/diagnostics, payload preview, one-item flush, batch flush, and last error.

It kept profile/session/planning state: `profile_url`, source URL/modal linkage, page context, `profile_scan`, `target_status`, `classification`, `verify`, `dry_run`, calibration, harvest options, layer readiness, queue, queue preview, results, collect trace, and backend capture-session id.

That is why Reset queue count remained 28: diagnostics used `state.harvest.queue.length` and current-run reset preserved the queue. Session stayed known because `capture_session_id` and nested `harvest.backend.capture_session.session_id` were explicitly preserved. The UI still showed Already collected 28 because the view model prefers `state.classification.counts.complete` when classification is successful, with queue/status fallback.

For a new profile, local profile plan state must be cleared: scan results, classification, target status, verify/dry-run, root and nested capture session ids, queue/preview, harvest counters/checkpoints/results, backend payload/flush state, safety checkpoint/session linkage, workflow locks, and current target fields. Calibration and settings remain preserved by default.

## Implementation

- Added reset modes: `current_run`, `current_profile_rescan`, `new_profile`, and `full_local_reset_dev_only`.
- Kept existing Reset behavior as `current_run` so Batch Next 10 and current profile retry flows keep working.
- Added `current_profile_rescan` and `new_profile` modes that clear local scan/classification/queue/session/counters without deleting backend Capture Inbox data.
- Added profile identity helpers: `detectCurrentDouyinProfileIdentity` and `isDifferentProfile`.
- Added pre-collect profile guard. If the active tab profile differs from scanner state, Start Collecting blocks with `Profile changed. Scan this profile before collecting.` and diagnostics include `pre_collect_profile_match`.
- Updated popup Reset to present explicit choices: Reset current run, Rescan this profile, Start new profile.

## Validation

- `npm --workspace @reup-douyin/extension-douyin-capture run typecheck` passed during implementation.
- Full test/build validation is recorded in the resume doc/final report.
