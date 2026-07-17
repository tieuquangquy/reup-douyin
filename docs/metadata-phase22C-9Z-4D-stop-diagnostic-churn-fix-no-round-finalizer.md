# 22C-9Z-4D Stop Diagnostic Churn And Fix No-Round Finalizer

## Root Cause

The runtime failure signature was real:

- DOM Probe had already completed productively.
- `profile_grid_ready = true`
- `aweme_id_count > 0`
- the final visible state still stayed on `profile_scan_no_round_started`
- `legacy_route_invoked` and `scan_no_round_reason` remained empty.

The final state validator only repaired generic zero-round failures when canonical probe trace was missing. It did not repair the stronger invariant violation where the probe trace existed and was productive, but no legacy dispatch was recorded. That allowed the popup-visible state to keep the stale generic error.

## Choke Point Fixed

`apps/extension-douyin-capture/src/wholeProfileHarvest/state.ts`

`validateScannerState(...)` now converts this exact final state:

- productive DOM Probe
- zero rounds
- `profile_scan_no_round_started`
- no legacy dispatch evidence

into:

- `productive_probe_legacy_dispatch_missing`
- `scan_no_round_reason = invariant_violation_productive_probe_without_legacy_dispatch`
- `scan_failure_stage = post_probe_legacy_dispatch`
- `scan_post_probe_productive_gate_result = productive` when absent.

This prevents the UI/runtime state from silently falling back to the old generic no-round failure.

## Why 4C Checkpoints Could Still Stay Empty

The active background handoff was still reading probe diagnostics back from storage before dispatch. A productive DOM Probe could be persisted correctly while the dispatch decision read stale or incomplete state. That explains why the build witness was visible, but the post-probe branch fields stayed empty.

`apps/extension-douyin-capture/src/background.ts` now keeps the current run DOM Probe diagnostics in memory and uses that exact object for the productive-gate dispatch decision, with storage as fallback only.

## Regression Added

The new runtime reproduction test builds the same final state seen in manual logs:

- completed productive probe
- no dispatch evidence
- no `scan_no_round_reason`
- generic `profile_scan_no_round_started`

It failed before the fix and passes after the validator change.

Additional source-level guards assert:

- productive probe dispatch reads the current probe object
- `legacy_route_invoked = yes` is written before the legacy message send
- dispatch failures retain `legacy_dispatch_failed:<reason>`.

## Files Changed

- `apps/extension-douyin-capture/src/background.ts`
- `apps/extension-douyin-capture/src/wholeProfileHarvest/state.ts`
- `apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts`
- `apps/extension-douyin-capture/src/modalWholeProfileTest.test.ts`

## Manual Retest Checklist

1. Reload unpacked extension from `apps/extension-douyin-capture/dist`.
2. Refresh the Douyin profile tab.
3. Click `Scan Profile`.
4. Confirm the old invalid combo no longer exists:
   - productive DOM Probe
   - `legacy_route_invoked = none`
   - `scan_no_round_reason = none`
   - `profile_scan_no_round_started`
5. Accept either:
   - success path with legacy dispatch and queue build, or
   - controlled failure:
     `productive_probe_legacy_dispatch_missing`
     plus
     `invariant_violation_productive_probe_without_legacy_dispatch`.

## Remaining Risk

If Chrome still reaches the controlled invariant failure, the remaining bug is specifically inside the background legacy dispatch execution path after a productive in-memory probe object. The generic finalizer masking is now removed, so follow-up diagnosis will be precise instead of ambiguous.
