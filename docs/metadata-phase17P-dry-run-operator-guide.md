# Phase 17P Dry-run Operator Guide

## Purpose

Use Dry-run first N videos to prove whole-profile modal harvesting can open target modals directly, extract detail metrics, and validate aweme-id integrity before any production writes are allowed.

## Steps

1. Open a Douyin modal URL on the target profile.
2. Open the extension popup.
3. Expand Advanced / Beta.
4. Run Test Modal → Whole Profile Harvest in Verify-only mode first.
5. Confirm the result is completed and target count is greater than zero.
6. Switch mode to Dry-run first 3 videos.
7. Click Test Modal → Whole Profile Harvest again.
8. Review Dry-run detail test rows.

## Expected Passing Result

The panel should show:

- Status: `completed`
- Phase: Dry-run completed
- Dry-run detail test: `3 pass / 0 fail / 3 total`
- Backend writes: `No backend writes performed.`
- Can harvest whole profile: yes

Each row should show the target aweme id, duration, likes, comments, favorites, and shares.

## Interpreting Failures

- `dry_run_modal_navigation_failed`: direct modal URL did not settle to the expected `modal_id`.
- `dry_run_modal_metrics_timeout`: calibrated point detail probe did not return a usable metric payload.
- `dry_run_data_integrity_mismatch`: target id, current modal id, or extracted aweme id did not match.
- `dry_run_some_targets_failed`: at least one target passed and at least one failed.
- `dry_run_all_targets_failed`: no target passed.

## Safety

Dry-run is intentionally isolated. It does not call `/douyin-extension/full-modal-harvest`, does not flush backend, does not update Tile Gallery, and does not write production Safe Runner state.
