# Phase 17V Isolated Staged Harvest V2 Resume

## Current state

Phase 17V is implemented in the Douyin capture extension as a separate `Whole Profile Staged Harvest V2` path.

## Resume checklist

1. Open a Douyin profile/modal and run `Verify only` in the modal whole-profile beta panel.
2. Confirm `Verified target count` is greater than zero.
3. Run `Calibrate 4 Points` if calibration is missing or stale.
4. Choose `Limit first N writes`; default is `first 3`.
5. Click `Run Staged Harvest V2`.
6. Watch the `Whole Profile Staged Harvest V2` panel for status, phase, current target, current aweme, updated/skipped/failed/flushed counts, backend response, and last error.
7. Refresh Capture Inbox after backend success if the UI does not auto-refresh.

## Recovery behavior

- Missing verified queue stops before writing with `Run Verify only first.`
- Missing calibration stops before writing with `Calibrate 4 Points first.`
- Backend schema rejection stops the whole V2 run with `backend_schema_rejected` and preserves the backend error text.
- Backend network/flush failure pauses the V2 run with `backend_flush_failed` and preserves target status/error.
- Reset Modal Test preserves V2 state.
- Reset Harvest State asks for `legacy`, `v2`, or `all` before clearing runtime state.

## Isolation guarantees

The V2 path uses only `douyinWholeProfileStagedHarvestV2` for production V2 state and does not depend on legacy Smart Capture state, old Harvest progress, capture sessions, Safe Harvest start messages, or old pending flush queues.
