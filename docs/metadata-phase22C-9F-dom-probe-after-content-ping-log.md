# Phase 22C-9F DOM Probe After Content Ping Log

## Scope
- Phase: 22C-9F — Execute DOM probe after content ping and preserve real scan error.
- Area: extension Scan Profile background route, content-script DOM probe handler, diagnostics, and error classification.
- Out of scope: backend APIs, Capture Inbox frontend, Review Board, Reup Score, Start Collecting, modal extraction payload, and popup redesign.

## Part A Audit
- Ping sender: `background.ts` `ensureContentScriptReady()` sends `DOUYIN_SCANNER_PING` with the background trace version.
- Ping receiver: `contentScript.ts` handles `DOUYIN_SCANNER_PING` / `REUP_DOUYIN_PING` and returns `REUP_DOUYIN_PONG` with page context.
- DOM probe sender: the background runtime `scanProfile()` sends `DOUYIN_PROFILE_DOM_PROBE` before `REUP_DOUYIN_MODAL_TEST_SCAN_PROFILE`.
- DOM probe handler: `contentScript.ts` handles `DOUYIN_PROFILE_DOM_PROBE` via `buildDouyinProfileDomProbe()`.
- Root cause of `ping = ok` but DOM probe fields = none: tab success diagnostics were not persisted by `getActiveTab()`, and the probe result was only merged into the eventual scan response instead of being persisted immediately after ping/probe execution.
- Generic error source: background scan fallback returned `profile_scan_failed`; `profileScanner.ts` defaulted unmapped scan reasons to `profile_scan_failed`; controller finalization then surfaced the generic state message.

## Implementation
- Bumped background trace version to `22C-9F` and run ids to `scan_profile_22C9F_*`.
- Persisted active tab diagnostics on successful tab resolution:
  - `tab_resolve_result`
  - `tab_resolve_strategy`
  - `tab_id`
  - `tab_url`
  - `tab_title`
  - `tab_status`
  - `tab_is_douyin`
- Persisted DOM probe lifecycle independently:
  - `profile_dom_probe_status = started`
  - `profile_dom_probe_started_at`
  - `profile_dom_probe_completed_at`
  - `dom_probe_message_result`
- Added background DOM probe helper with timeout and explicit failure classification.
- Added fallback direct `chrome.scripting.executeScript()` DOM probe when the content-script DOM probe handler is missing.
- Updated content-script DOM probe handler to echo `22C-9F`, return top-level probe fields inside diagnostics, and include `error: null` on successful probes.
- Added explicit DOM probe error codes:
  - `scan_dom_probe_timeout`
  - `scan_dom_probe_handler_missing`
  - `scan_dom_probe_message_failed`
  - `scan_dom_probe_malformed_response`
  - `scan_dom_probe_execute_script_failed`
- Updated scan reason mapping so these codes are preserved instead of falling through to `profile_scan_failed`.
- Added diagnostics UI rows for probe message result, timings, fallback status, specific scan error, failure stage, and raw scan error.

## Runtime Contract
1. Scan Profile popup dispatches only `DOUYIN_SCANNER_START_SCAN_PROFILE`.
2. Background resolves and persists active tab diagnostics.
3. Background ensures content script via ping.
4. If ping is ready, background immediately records DOM probe `started`.
5. Background sends `DOUYIN_PROFILE_DOM_PROBE` and persists the normalized result.
6. Missing handler attempts direct `executeScript` fallback.
7. Probe failure returns a specific scan reason.
8. Probe success with video candidates continues to `REUP_DOUYIN_MODAL_TEST_SCAN_PROFILE`.
9. Final diagnostics preserve `specific_scan_error`, `scan_failure_stage`, and `raw_scan_error`.

## Files Changed
- `apps/extension-douyin-capture/src/background.ts`
- `apps/extension-douyin-capture/src/contentScript.ts`
- `apps/extension-douyin-capture/src/wholeProfileHarvest/errors.ts`
- `apps/extension-douyin-capture/src/wholeProfileHarvest/profileScanner.ts`
- `apps/extension-douyin-capture/src/wholeProfileHarvest/viewModel.ts`
- `apps/extension-douyin-capture/src/modalWholeProfileTest.test.ts`

## Validation
- Focused modal whole-profile static test passes.
- Typecheck passes after implementation.
- Full test/build validation is tracked in the 22C-9F resume doc and final report.
