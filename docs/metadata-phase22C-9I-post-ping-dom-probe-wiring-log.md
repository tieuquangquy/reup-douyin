# Phase 22C-9I Post-Ping DOM Probe Wiring Log

## Scope
Implemented Phase 22C-9I only for the background-owned Scan Profile path. No Start Collecting, pause/resume, reset, backend API, Capture Inbox, Review Board, Reup Score, payload, or flush logic was changed.

## Exact post-ping branch found
The post-ping branch is in `apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts` inside `verifyProfile()` after `runtime.ensureContentScriptReady(resolvedContext.tab_id)` returns.

Before 22C-9I, the next statements after ping success were:

1. Persist ensure-content-script diagnostics.
2. Throw if `!ready.ok`.
3. Throw for modal/navigation-required context.
4. Move the state to `preparing_profile_page`.
5. Call `completeProfileVerify(...)`.

The DOM probe was not called in that immediate post-ping branch. The existing 22C-9H DOM probe lived later in the background runtime `scanProfile()` transport, after the controller had already advanced toward scan completion.

## Why DOM probe was not invoked
Diagnostics could show `content_script_ping_result = ok` while all DOM probe fields remained absent because the controller did not send or await the DOM probe immediately after ping. If the controller failed, returned, or finalized before reaching `transport.scanProfile()`, the later 22C-9H probe path never ran.

The failure finalizer also allowed the missing probe state to surface as generic `profile_scan_failed`, because no invariant converted ping-ok/probe-missing into a specific post-ping failure.

## Implementation
Added `runPostPingProfileDomProbe22C9I(context)` with this context shape:

```ts
{
  scanRunId,
  tabId,
  tabUrl,
  traceVersion: "22C-9I"
}
```

The hook now:

1. Persists `phase = probing_dom`.
2. Persists `profile_dom_probe_status = started`.
3. Persists `profile_dom_probe_message = sending`.
4. Persists `profile_dom_probe_started_at`.
5. Sends `DOUYIN_PROFILE_DOM_PROBE_22C9I` to the content script.
6. Awaits the response with a 10 second timeout.
7. Attempts executeScript fallback only for handler-missing style errors.
8. Persists success or specific failure diagnostics.
9. Returns a structured `{ ok, specificError, diagnostics }` result.

The controller calls this hook immediately after `content_script_ping = ok` and modal-context checks, before `completeProfileVerify(...)` can start scan rounds.

## Diagnostics added
The active Scan Profile path now stamps:

- `scanner_runtime_version = "22C-9I"`
- `state_machine_version = "22C-9I"`
- `scan_controller_version = "22C-9I-scan-controller"`
- `scan_action_trace_version = "22C-9I"`

The DOM probe path persists:

- `profile_dom_probe_message_type`
- `profile_dom_probe_message = sending | ok | <specific failure>`
- `profile_dom_probe_response_received = yes | no`
- `profile_dom_probe_started_at`
- `profile_dom_probe_completed_at`
- `profile_dom_probe_fallback_attempted`
- `profile_dom_probe_fallback_result`
- `specific_scan_error`
- `scan_failure_stage`
- safe raw error fields

## Specific failure classification
22C-9I classifies DOM probe outcomes as:

- `scan_dom_probe_message_failed` for receiving-end / message-port connection failures.
- `scan_dom_probe_handler_missing` for unknown or unsupported message type responses.
- `scan_dom_probe_timeout` for timeout.
- `scan_dom_probe_malformed_response` for an ok response without a probe payload.
- `scan_dom_probe_execute_script_failed` for fallback execution failure.
- `scan_dom_probe_not_invoked` for the invariant violation where ping was ok but no DOM probe ever started.

## Finalizer invariant
Before finalizing failed Scan Profile runs, both the controller finalizer and the background finalizer check:

- content script ping was ok
- `profile_dom_probe_started_at` is missing
- result is failed

When true, diagnostics are forced to:

- `specific_scan_error = scan_dom_probe_not_invoked`
- `scan_failure_stage = post_ping_before_dom_probe`
- `lastScannerError = scan_dom_probe_not_invoked`
- `state_invariant_violation = ping_ok_but_dom_probe_not_invoked`

This prevents the previous impossible state from ending as generic `profile_scan_failed`.

## Message compatibility
The content script supports all required DOM probe message types:

- `DOUYIN_PROFILE_DOM_PROBE`
- `DOUYIN_PROFILE_DOM_PROBE_22C9H`
- `DOUYIN_PROFILE_DOM_PROBE_22C9I`

The shared message union in `types.ts` preserves both 22C-9H and 22C-9I route/probe literals.

## Tests run
- `npm --workspace @reup-douyin/extension-douyin-capture run typecheck`
- `npm --workspace @reup-douyin/extension-douyin-capture run test`

The test command also ran the extension build as part of the package test script.

## Manual retest steps
1. Reload the unpacked extension from `apps/extension-douyin-capture/dist`.
2. Open a Douyin profile tab, not a modal URL.
3. Open the extension popup and click `Scan Profile`.
4. Inspect `chrome.storage.local` for `douyinWholeProfileHarvestState.debug.last_request_summary`.
5. Confirm ping diagnostics show `content_script_ping_result = ok`.
6. Confirm one of these is present before finalization: `profile_dom_probe_message`, `profile_dom_probe_started_at`, fallback diagnostics, or `specific_scan_error = scan_dom_probe_not_invoked`.
7. Confirm failures show a specific DOM probe error rather than generic `profile_scan_failed`.
