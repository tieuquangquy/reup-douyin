# 22C-9Z-4E Fix Missing Dispatch After Productive Gate

## Root Cause

The productive DOM Probe branch and the legacy scanner dispatch were separated across two background runtime steps:

1. `runPostPingProfileDomProbe22C9I(...)` completed the productive probe.
2. The actual legacy scanner dispatch was deferred until the later `scanProfile(...)` transport call.

That created a real gap. The run could finalize after a productive probe but before the later transport call dispatched:

- `scan_post_probe_productive_gate_result = productive`
- `scan_post_probe_before_legacy_dispatch = none`
- `legacy_route_invoked = none`

The 22C-9Z-4D finalizer then reported the correct invariant failure, but the actual dispatch gap still remained.

## Productive Gate Location

The productive gate is handled in:

- `apps/extension-douyin-capture/src/background.ts`

The logic now lives in the background helper:

- `dispatchLegacyScannerAfterProductiveProbe(...)`

It owns:

- productive probe evaluation
- pre-dispatch diagnostics
- `DOUYIN_RUN_LEGACY_PROFILE_SCROLL_SCAN_22C9Z3`
- post-dispatch diagnostics
- explicit dispatch failure mapping

## Fix

When the DOM Probe hook returns:

- `profile_dom_probe_status = completed`
- `profile_grid_ready = true`
- `aweme_id_count > 0`

the background route now immediately dispatches the legacy scanner from the same post-probe path.

It persists before send:

- `scan_post_probe_productive_gate_result = productive`
- `scan_post_probe_before_legacy_dispatch = yes`
- `legacy_route_invoked = yes`
- `legacy_scanner_route_invoked = yes`
- `legacy_scanner_message_type = DOUYIN_RUN_LEGACY_PROFILE_SCROLL_SCAN_22C9Z3`

After send it persists:

- `scan_post_probe_after_legacy_dispatch = yes`

The later `scanProfile(...)` transport no longer creates a new timing window. It reuses the cached legacy scanner result already produced by the post-probe path.

## Why Other State Must Not Block Dispatch

The following states are unrelated to Scan Profile queue discovery and must not block this handoff:

- calibration missing
- canonical calibration missing
- legacy state loading
- storage audit `legacy_quarantined`
- backend session missing
- extraction readiness
- payload guard state

Those belong to later collection phases, not profile discovery.

## Failure Behavior

If the content-script message throws, the route still preserves invocation evidence:

- `legacy_route_invoked = yes`
- `legacy_scanner_route_invoked = yes`
- `legacy_scanner_invocation_result = failed`
- `scan_no_round_reason = legacy_dispatch_failed:<reason>`
- `last scanner error = legacy_dispatch_failed`

## Tests

Updated tests cover:

- productive probe dispatch starts from the post-probe background path
- pre-dispatch evidence is written before the content-script send
- later scanner transport reuses the already dispatched result
- failed dispatch keeps explicit `legacy_dispatch_failed:<reason>`
- 22C-9Z-4D invariant protection remains intact

## Manual Retest Checklist

1. Reload unpacked extension from `apps/extension-douyin-capture/dist`.
2. Refresh the target Douyin profile tab.
3. Click `Scan Profile`.
4. Confirm this invalid combo is gone:
   - `scan_post_probe_productive_gate_result = productive`
   - `scan_post_probe_before_legacy_dispatch = none`
   - `legacy_route_invoked = none`
5. Expected success path:
   - `scan_post_probe_before_legacy_dispatch = yes`
   - `legacy_route_invoked = yes`
   - `legacy_scanner_route_invoked = yes`
   - `legacy_scanner_message_type = DOUYIN_RUN_LEGACY_PROFILE_SCROLL_SCAN_22C9Z3`
6. If dispatch fails, expected controlled failure:
   - `legacy_scanner_invocation_result = failed`
   - `scan_no_round_reason = legacy_dispatch_failed:<reason>`
