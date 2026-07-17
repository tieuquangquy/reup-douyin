# Phase 22C-9H - Mandatory DOM Probe After Ping Resume

## Phase
22C-9H - Mandatory DOM Probe after content script ping.

## Current Status
- Audit complete.
- Implementation complete pending validation.
- Docs created.
- Tests updated for 22C-9H static assertions.

## Key Code Paths
- Popup dispatch: `apps/extension-douyin-capture/src/popup.ts`, `dispatchBackgroundScanProfileAction22C9H()`.
- Background route: `apps/extension-douyin-capture/src/background.ts`, `DOUYIN_SCANNER_START_SCAN_PROFILE_22C9H` branch.
- Content ping: `createBackgroundScanProfileRuntime().ensureContentScriptReady()`.
- Mandatory DOM probe: `createBackgroundScanProfileRuntime().scanProfile()` -> `sendBackgroundDomProbe22C9H()`.
- Content handler: `apps/extension-douyin-capture/src/contentScript.ts`, `DOUYIN_PROFILE_DOM_PROBE_22C9H` branch.
- Fallback probe: `inlineProfileDomProbe22C9H()`.

## Expected Diagnostics
- Version fields: `scanner_runtime_version`, `state_machine_version`, and `scan_action_trace_version` should be `22C-9H`; `scan_controller_version` should be `22C-9H-scan-controller`.
- After ping ok, tab diagnostics should include `tab_resolve_result`, `tab_resolve_strategy`, `tab_id`, `tab_url`, `tab_title`, `tab_status`, `tab_is_douyin`, and `tab_resolved_at`.
- DOM probe start should include `profile_dom_probe_status: started`, `profile_dom_probe_message: sending`, and `profile_dom_probe_started_at`.
- DOM probe completion should include `profile_dom_probe_completed_at`, `profile_grid_ready`, `video_anchor_count`, `aweme_id_count`, `grid_card_candidate_count`, and `scroll_container_found`.
- Fallback should include `profile_dom_probe_fallback_attempted`, `profile_dom_probe_fallback_result`, and fallback error/result fields.

## If Continuing
1. Run `npm --workspace @reup-douyin/extension-douyin-capture run test`.
2. Run `npm --workspace @reup-douyin/extension-douyin-capture run typecheck`.
3. Run `npm --workspace @reup-douyin/extension-douyin-capture run build`.
4. If failures occur, fix only Phase 22C-9H Scan Profile scope.
