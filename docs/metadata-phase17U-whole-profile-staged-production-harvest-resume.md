# Phase 17U Whole Profile Staged Production Harvest Resume

## Current status

Phase 17U adds a staged production path for the Modal Whole Profile verified queue. The implementation is scoped to the extension and documentation. The API was not changed.

The staged path is available from the extension popup advanced Modal Whole Profile area as:

```text
Run Staged Harvest
```

## Resume prerequisites

Before running staged harvest, the operator must have:

1. A Douyin modal URL open for the intended profile.
2. A completed Modal Whole Profile Verify-only run for that profile.
3. A successful Dry-run random 3 result from the verified queue.
4. Valid right-rail calibration stored in the extension.
5. Backend API reachable at the configured extension base URL.

If the verified queue is missing or stale, use Verify only again before resuming production harvest.

## Runtime state

The staged flow starts Safe Harvest V2 with classified verified targets. Safe Harvest V2 keeps durable state in extension storage and supports operator stop/resume through the existing popup controls.

Important state fields:

- run id
- phase
- target aweme IDs
- per-target statuses
- harvested count
- committed count
- pending flush count
- failed items
- transition log
- profile-card evidence map
- capture session id
- capture id

## Resume behavior

Resume uses the existing Safe Harvest V2 resume path. It continues from persisted target statuses instead of restarting the whole verified queue.

Expected behavior:

- completed targets stay completed,
- failed/partial targets remain visible in progress state,
- pending finalized items can be flushed safely,
- unprocessed targets continue in order,
- direct `modal_id` navigation is reused for each remaining target,
- profile-card evidence remains keyed by aweme ID.

## Stop behavior

Operator Stop uses the existing safe harvest stop path. It should pause the run without clearing the verified queue or deleting already committed backend items.

After stop:

1. Confirm the progress panel shows a stopped/paused state.
2. Keep the same Douyin profile context open if possible.
3. Use Resume Harvest to continue.

If the tab was navigated away or the verified profile context is no longer valid, return to a modal URL for the same profile before resuming.

## Backend failure behavior

A finalized flush failure pauses the safe runtime. The staged flow should not keep writing after a backend schema rejection.

HTTP 422 schema rejection is classified as:

```text
backend_schema_rejected
```

Operator recovery:

1. Stop or leave the paused run as-is.
2. Inspect the backend error body from extension/backend diagnostics.
3. Fix the schema mismatch in code or backend contract.
4. Re-run tests.
5. Resume only after the payload is accepted.

## Duplicate and idempotency behavior

The staged flow has two layers of duplicate protection:

1. Harvest-plan classification skips backend-complete targets by default.
2. Safe Harvest V2 tracks per-run target statuses so already processed targets are not repeated during normal resume.

Default policy:

```text
skip_existing_complete = true
commit_policy = finalized_only
```

The `refresh_all` harvest mode can intentionally include already known items at classification time, but the staged implementation still honors the explicit skip-existing-complete option unless changed by code.

## When to restart from Verify only

Run Verify only again when:

- storage no longer has `verified_targets`,
- the current profile does not match the verified profile,
- the verified queue came from a different profile,
- target evidence looks stale or inconsistent,
- Douyin page layout changed enough to invalidate the target list,
- dry-run random 3 no longer passes.

## Safe retest checklist after resume changes

1. Open a modal URL for the target profile.
2. Run Verify only.
3. Run Dry-run random 3.
4. Run Staged Harvest.
5. Stop after one item is harvested or queued.
6. Confirm progress shows stopped/paused state.
7. Click Resume Harvest.
8. Confirm the next remaining direct `modal_id` target is opened.
9. Confirm already completed targets are not duplicated.
10. Confirm backend committed count increases only after finalized flush success.

## Known boundaries

Phase 17U does not add backend queue persistence, database migrations, or cross-device resume. Resume is local extension runtime resume for the Phase 1 Windows operator workflow.
