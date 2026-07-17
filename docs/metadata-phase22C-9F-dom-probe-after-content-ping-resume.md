# Phase 22C-9F DOM Probe After Content Ping Resume

## Goal
Ensure a successful content-script ping is immediately followed by a persisted profile DOM probe, and ensure any scan failure preserves the real DOM probe or scan error instead of collapsing to generic `profile_scan_failed`.

## Expected Diagnostics
After pressing Scan Profile on a Douyin profile page, advanced diagnostics should show:
- `Scan action trace version: 22C-9F`
- `Popup route hit: true`
- `Background route hit: true`
- `Controller route hit: true`
- `Scan run id: scan_profile_22C9F_*`
- `Tab resolved: success`
- `Tab resolve strategy: active_current_window`
- `Tab URL: https://www.douyin.com/...`
- `Content script ensure status: ready`
- `Content script ping: ok`
- `Content injection: not_needed` or `attempted`
- `Profile DOM probe status: available`
- `Profile DOM probe message: ok`, `timeout`, `failed`, or `handler_missing`
- `Profile DOM probe started at: <timestamp>`
- `Profile DOM probe completed at: <timestamp>`
- `Profile grid ready: true` when video candidates exist
- `Video anchor count`, `Aweme id count`, and `Grid card candidate count` populated
- `Specific scan error` populated with the precise failure if the probe or scan fails
- `Scan failure stage` set to `dom_probe` or `scan_round` on failures

## Error Contract
The Scan Profile route should preserve these specific DOM probe errors:
- `scan_dom_probe_timeout`
- `scan_dom_probe_handler_missing`
- `scan_dom_probe_message_failed`
- `scan_dom_probe_malformed_response`
- `scan_dom_probe_execute_script_failed`

The generic `profile_scan_failed` should only remain a final fallback for genuinely unmapped scan failures.

## Fallback Contract
When `DOUYIN_PROFILE_DOM_PROBE` cannot be delivered because the handler is missing, the background route attempts `chrome.scripting.executeScript()` with an inline DOM probe. Diagnostics should include:
- `dom_probe_message_result: handler_missing`
- `dom_probe_fallback_execute_script_attempted: true`
- `dom_probe_fallback_execute_script_result: success` or `failed`

## Manual Retest Steps
1. Reload the extension build.
2. Open a Douyin profile page with visible videos.
3. Open the extension popup and click Scan Profile.
4. Confirm the popup no longer hangs and the background route is hit.
5. Confirm tab diagnostics are populated after content ping.
6. Confirm DOM probe fields populate before scan finalization.
7. If the scan fails, confirm `Specific scan error` is not hidden by generic `profile_scan_failed`.
8. Copy advanced diagnostics if the probe reports `handler_missing`, `timeout`, or `message_failed`.

## Validation Commands
```bash
npx --workspace @reup-douyin/extension-douyin-capture tsx src/modalWholeProfileTest.test.ts
npm --workspace @reup-douyin/extension-douyin-capture run test
npm --workspace @reup-douyin/extension-douyin-capture run typecheck
npm --workspace @reup-douyin/extension-douyin-capture run build
```

## Notes
- The background route persists diagnostics into `WHOLE_PROFILE_HARVEST_STATE_KEY` so the popup can show probe state even if the final scan fails.
- The content script does not mutate scanner state from the DOM probe handler; it only returns probe fields and diagnostics to the background owner.
