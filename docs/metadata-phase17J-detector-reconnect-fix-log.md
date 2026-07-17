# Phase 17J Detector Reconnect Fix Log

## Scope

Phase 17J fixed Douyin detector/content-script execution failures inside `apps/extension-douyin-capture` only. No backend, web app, CDP workflow, modal metric extraction, calibration algorithm, or Safe Runner orchestration changes were made.

## Root Cause

The popup could reach a Douyin tab whose manifest match or injected content script was stale or missing after extension reload / SPA navigation. Existing detector paths surfaced a generic direct-execution failure and told the operator to refresh, but they did not first verify content-script liveness, reinject `contentScript.js`, and rerun page-context detection with structured diagnostics.

## Implementation

- Added rich content-script `REUP_DOUYIN_PING` / `REUP_DOUYIN_PONG` response with URL, version, page context, and viewport.
- Added detector-ready fields to page-context detection responses.
- Added popup-side `ensureDouyinContentScriptReady()` flow:
  - validate active Douyin URL,
  - ping content script,
  - inject `contentScript.js` on missing/forced reconnect,
  - wait briefly,
  - ping again,
  - return structured diagnostics on failure.
- Updated `runDetectorWithReconnect()` to run only after readiness succeeds, separate content-script failures from detector-message failures, and clear stale detector errors when ready.
- Updated popup diagnostics to show supported tab, content script status, detector status, last reconnect, last Chrome error, ping error, injection attempt/error, and manifest match.
- Updated source manifest exact Douyin matches and assertions for required host permissions.
- Updated direct execution fallback text so the popup guides operators to `Reconnect Douyin Tab` first.

## Tests Added/Updated

- Source assertions for ping-first / inject / ping-again reconnect flow.
- Source assertions for unsupported-tab no-injection guard.
- Source assertions for structured `content_script_unavailable` and `detector_message_failed` diagnostics.
- Source assertions for popup reconnect diagnostics and required failed-reconnect guidance.
- Manifest assertions for `storage`, `activeTab`, `scripting`, exact Douyin host permissions, API host permissions, and exact Douyin content-script matches.
- Transport tests updated for new operator-facing detector failure guidance.

## Verification

- `npm --workspace @reup-douyin/extension-douyin-capture run typecheck` passed.
- `npm --workspace @reup-douyin/extension-douyin-capture run test` passed, including package build and dist module resolution.
