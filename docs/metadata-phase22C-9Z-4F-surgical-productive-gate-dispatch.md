# 22C-9Z-4F Surgical Productive Gate Dispatch

## Exact Gate And Dispatch Functions

The runtime legacy-dispatch gate is in:

- `apps/extension-douyin-capture/src/background.ts`
- `dispatchLegacyScannerAfterProductiveProbe(...)`

It is responsible for:

- `scan_post_probe_productive_gate_result`
- `scan_post_probe_before_legacy_dispatch`
- `legacy_route_invoked`
- `legacy_scanner_route_invoked`
- sending `DOUYIN_RUN_LEGACY_PROFILE_SCROLL_SCAN_22C9Z3`

The content-script message send is also in that function.

The visible final failure `productive_probe_legacy_dispatch_missing` can be produced by:

- `completeProfileVerify(...)` in `wholeProfileHarvest/controller.ts`
- `validateScannerState(...)` in `wholeProfileHarvest/state.ts`

## Actual Blocking Cause

The manual log looked like:

- productive gate = `productive`
- before dispatch = `none`
- legacy route invoked = `none`

That was a mixed state.

`validateScannerState(...)` was backfilling:

- `scan_post_probe_productive_gate_result = productive`

while repairing a missing-dispatch invariant. This made the popup look like the active runtime background gate had executed, even when it had not recorded dispatch evidence.

The validator no longer fabricates productive-gate runtime evidence.

## Runtime Dispatch Guarantee

The productive DOM Probe runtime path now dispatches the Z3 legacy scanner directly from the active post-probe hook:

- `runPostPingProfileDomProbe22C9I(...)`
  - receives productive DOM Probe
  - calls `dispatchLegacyScannerAfterProductiveProbe(...)`

This path persists before send:

- `scan_post_probe_before_legacy_dispatch = yes`
- `legacy_route_invoked = yes`
- `legacy_scanner_route_invoked = yes`
- `legacy_scanner_message_type = DOUYIN_RUN_LEGACY_PROFILE_SCROLL_SCAN_22C9Z3`

It then sends the content-script message.

## Non-Blocking State

The regression path proves these do not prevent Scan Profile legacy dispatch:

- calibration missing
- backend session missing
- legacy state loading
- storage audit `legacy_quarantined`

Those are collection-stage concerns, not profile scan handoff conditions.

## Failure Behavior

If the send throws:

- invocation evidence stays `yes`
- `legacy_scanner_invocation_result = failed`
- `scan_no_round_reason = legacy_dispatch_failed:<reason>`

The state must not regress to `productive_probe_legacy_dispatch_missing` when pre-dispatch evidence exists.

## Regression Tests

Added runtime tests cover:

1. Productive DOM Probe invokes the legacy scanner from the same background post-probe path.
2. Missing calibration/backend session plus legacy loading/quarantine state still dispatches.
3. Thrown legacy send preserves invocation evidence and explicit `legacy_dispatch_failed:<reason>`.
4. State repair does not fabricate `productive` runtime evidence.
5. State repair does not create `productive_probe_legacy_dispatch_missing` after pre-dispatch evidence exists.

## Manual Retest Checklist

1. Reload unpacked extension from `apps/extension-douyin-capture/dist`.
2. Refresh the Douyin profile tab.
3. Click `Scan Profile`.
4. Verify:
   - `scan_post_probe_productive_gate_result = productive`
   - `scan_post_probe_before_legacy_dispatch = yes`
   - `legacy_route_invoked = yes`
   - `legacy_scanner_route_invoked = yes`
   - `legacy_scanner_message_type = DOUYIN_RUN_LEGACY_PROFILE_SCROLL_SCAN_22C9Z3`
5. If dispatch fails, verify it reports:
   - `legacy_scanner_invocation_result = failed`
   - `scan_no_round_reason = legacy_dispatch_failed:<reason>`
