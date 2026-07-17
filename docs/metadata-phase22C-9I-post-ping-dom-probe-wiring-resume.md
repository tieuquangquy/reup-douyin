# Phase 22C-9I Post-Ping DOM Probe Wiring Resume

## Phase
22C-9I - Wire post-ping Scan Profile to DOM Probe, no early generic failure.

## Current status
Implemented and validated locally for the extension package.

## Files changed
- `apps/extension-douyin-capture/src/background.ts`
- `apps/extension-douyin-capture/src/contentScript.ts`
- `apps/extension-douyin-capture/src/types.ts`
- `apps/extension-douyin-capture/src/popup.ts`
- `apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts`
- `apps/extension-douyin-capture/src/wholeProfileHarvest/errors.ts`
- `apps/extension-douyin-capture/src/wholeProfileHarvest/profileScanner.ts`
- `apps/extension-douyin-capture/src/modalWholeProfileTest.test.ts`
- `apps/extension-douyin-capture/src/wholeProfileHarvest.viewModel.test.ts`
- `docs/metadata-phase22C-9I-post-ping-dom-probe-wiring-log.md`
- `docs/metadata-phase22C-9I-post-ping-dom-probe-wiring-resume.md`

## Audit finding
The exact branch was `verifyProfile()` in `apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts`. After `runtime.ensureContentScriptReady(...)` returned `ready.ok`, the controller persisted ensure diagnostics and went through modal/navigation checks before calling `completeProfileVerify(...)`. It did not call or await a DOM probe in that post-ping branch.

The previous DOM probe lived later in the background runtime `scanProfile()` transport. Any early failure/finalization between ping success and scan transport left `profile_dom_probe_message` and `profile_dom_probe_started_at` unset.

## Implementation details
`runPostPingProfileDomProbe22C9I(context)` now runs immediately after ping success. It persists `probing_dom`, marks message sending, sends `DOUYIN_PROFILE_DOM_PROBE_22C9I`, awaits a bounded response, attempts fallback for handler-missing responses, normalizes diagnostics, and returns a structured result to the Scan Profile controller.

The background scan transport now consumes already-persisted probe diagnostics instead of owning the first probe attempt. It refuses to continue scan rounds if the post-ping probe was never invoked or if probe diagnostics contain a specific failure.

## Error classifications
- Receiving-end/message-port failures: `scan_dom_probe_message_failed`
- Unknown/unsupported type: `scan_dom_probe_handler_missing`
- Timeout: `scan_dom_probe_timeout`
- Malformed response: `scan_dom_probe_malformed_response`
- Fallback execution failure: `scan_dom_probe_execute_script_failed`
- Ping ok but probe never started: `scan_dom_probe_not_invoked`

## Finalizer invariant
Failed finalization with `content_script_ping_result = ok` and no `profile_dom_probe_started_at` forces:

- `specific_scan_error = scan_dom_probe_not_invoked`
- `scan_failure_stage = post_ping_before_dom_probe`
- `lastScannerError = scan_dom_probe_not_invoked`
- `state_invariant_violation = ping_ok_but_dom_probe_not_invoked`

This is implemented in both the controller finalizer and background finalizer.

## Message compatibility
Supported probe messages:

- `DOUYIN_PROFILE_DOM_PROBE`
- `DOUYIN_PROFILE_DOM_PROBE_22C9H`
- `DOUYIN_PROFILE_DOM_PROBE_22C9I`

`types.ts` includes both the 22C-9H and 22C-9I literals so compatibility checks typecheck.

## Validation
Already run:

- `npm --workspace @reup-douyin/extension-douyin-capture run typecheck`
- `npm --workspace @reup-douyin/extension-douyin-capture run test`

The test script also ran `npm run build` for the extension package.

## Manual retest
Reload the unpacked extension from `apps/extension-douyin-capture/dist`, open a Douyin profile page, click Scan Profile, then inspect `douyinWholeProfileHarvestState.debug.last_request_summary`. With ping ok, DOM probe fields should no longer remain all unset; failures should report specific DOM probe errors.
