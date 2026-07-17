# Phase 17S Dry-Run Reuse Verified Targets Log

## Scope

Phase 17S is limited to the Modal Whole Profile beta test inside the Douyin capture extension. It fixes dry-run modes so they reuse the verified target queue created by Verify Only instead of restarting the profile scanner when a valid queue already exists.

## Root Cause

Dry-run modes were coupled to the verify/profile-scan entrypoint. When the operator selected a dry-run mode, the popup could fall back into profile scanning unless the old completed-run shape matched narrowly. That made dry-runs fail with `profile_scan_start_failed` even when Verify Only had already produced usable profile targets. The persisted state also used the full test mode as `dry_run_sampling_mode`, allowing stale mismatches such as `mode = dry_run_first_n` with `dry_run_sampling_mode = verify_only`.

## Implemented Behavior

- Verify Only runs the profile scan and harvest-plan verification pipeline.
- Successful verification persists `verified_profile_url`, `verified_at`, `verified_targets`, `verified_target_details`, `verified_target_count`, and `verified_scan_diagnostics` in `douyinModalWholeProfileTestRun`.
- Dry-run modes enter a dedicated dry-run entrypoint.
- If a verified queue exists and matches the current profile context, dry-run sets `phase = dry_run_sampling` and reuses that queue without scanning the profile again.
- If no valid verified queue exists, dry-run sets `phase = verifying_before_dry_run`, runs the same working verify pipeline, and then continues into dry-run detail extraction.
- Dry-run detail extraction opens direct modal URLs and probes details without backend writes.

## Guardrails

- No backend full-modal-harvest call is introduced for dry-run.
- No Capture Inbox items are created by dry-run.
- Production Smart Capture flow remains separate from the Modal Whole Profile beta runtime.
- Dry-run state remains isolated to `douyinModalWholeProfileTestRun`.
