# Phase 17U Whole Profile Staged Production Harvest Log

## Purpose

Phase 17U promotes the verified Modal Whole Profile beta flow into a staged production harvest mode that writes finalized backend items only after safe per-target detail extraction succeeds.

This phase is intentionally limited to the verified Modal Whole Profile path. It does not add a crawler, a profile scanner replacement, a queue backend, auto-publishing, or new video-processing behavior.

## Production entrypoint

The extension popup now exposes a dedicated advanced action:

- Run Staged Harvest

The action starts mode `whole_profile_staged_harvest` behavior through `startWholeProfileStagedHarvest(options)` in the popup orchestration layer.

The operator must first create and validate a verified queue with the existing Modal Whole Profile beta flow:

1. Open any modal URL for the target profile.
2. Click Verify only.
3. Click Dry-run random 3.
4. Click Run Staged Harvest.

If the verified queue is missing or empty, the staged harvest stops before backend classification with:

```text
Run Verify only first.
```

## Verified queue contract

The staged harvest reads the Phase 17S Modal Whole Profile test run from extension storage and requires:

- `verified_targets`
- `verified_target_details`
- `verified_profile_url` or `resolved_profile_url`

The staged flow does not auto-scan the profile page when a verified queue exists. The harvest-plan payload is built from the verified target details and their profile-card evidence.

The current tab profile context must match the verified profile. A stale verified queue from another profile is rejected with the same operator-safe message:

```text
Run Verify only first.
```

## Calibration gate

Before classification or production harvesting, the staged flow validates the stored right-rail calibration. Missing or invalid calibration stops the run with:

```text
calibration_missing
```

This keeps production writes bound to the calibrated detail-metric extractor.

## Harvest-plan classification

The staged flow submits the verified targets to `/douyin-extension/harvest-plan` using schema:

```text
douyin_extension_harvest_plan.v1
```

The request uses the selected harvest mode:

- `new_and_incomplete` by default
- `refresh_all` when selected in the popup harvest mode UI

The backend classification result determines which verified targets enter the production runner.

## Complete item skip policy

The default Phase 17U policy is:

```text
skip_existing_complete = true
```

Complete aweme IDs reported by the harvest-plan response are skipped before the safe runner starts. Incomplete or new planned targets remain eligible.

If classification leaves no eligible targets, the run stops with:

```text
skipped_existing_complete
```

## Safe runner behavior

The staged flow reuses Safe Harvest V2 rather than adding a separate long-running implementation.

Runtime options include:

- `target_aweme_ids` from the classified verified queue
- `profile_card_evidence_by_aweme_id`
- `flush_every_n_items = 5` by default
- `capture_session_id` and `capture_id` from harvest-plan/backend context
- `stop_on_captcha = true`
- `stop_on_no_next = true`
- `allow_probe_warnings = false`

Each target is opened by direct modal URL mutation with `modal_id`, then the content script waits for calibrated modal metrics for the expected aweme ID.

## Finalized backend write behavior

Only finalized detail items are flushed to `/douyin-extension/full-modal-harvest`.

The staged payload uses:

```text
schema_version = douyin_full_modal_harvest.v1
commit_policy = finalized_only
evidence_collection_version = phase17a_finalized_only_harvest
extension_source = whole_profile_staged_harvest
```

The finalized payload includes calibrated detail metrics when available:

- duration
- like count
- comment count
- favorite count
- share count

Profile-card evidence is attached before flush when available.

## Backend schema rejection handling

If the backend rejects a finalized flush with HTTP 422, the run is paused and surfaced as:

```text
backend_schema_rejected
```

The run does not continue producing additional bad writes after schema rejection. The backend response body remains available through the backend post error context surfaced by the existing extension backend client path.

## UI update policy

Phase 17U keeps the existing production safety rule: Capture Inbox and Tile Gallery state should be considered updated only after backend success. The extension queues finalized items and marks progress through the safe runner; durable app-visible capture records are backend-owned.

## Tests run during implementation

The extension test suite includes source-inspection assertions that verify:

- Run Staged Harvest button is present and separately wired.
- `startWholeProfileStagedHarvest(options)` exists.
- verified queue is required.
- stale verified profile context is rejected.
- calibration is required.
- harvest-plan classification is built from verified cards.
- complete items are skipped by default.
- profile-card evidence is passed to the safe runner.
- batch flush defaults to five.
- target IDs are passed directly to the runner.
- staged evidence carries candidate validation, target index, and source URL evidence.
- finalized backend payload identifies `whole_profile_staged_harvest`.
- finalized backend payload uses `phase17a_finalized_only_harvest`.
- finalized writes use `finalized_only` commit policy.
- backend 422 is classified as `backend_schema_rejected`.
- direct `modal_id` navigation and calibrated metric extraction remain in the content script.

## Non-goals

Phase 17U does not implement:

- crawler behavior,
- video downloading,
- video processing,
- scoring/filtering,
- publishing,
- distributed queues,
- database schema changes,
- new backend endpoints,
- automatic profile rescanning when the verified queue is absent.
