# Phase 22C-11A - Minimal Active-Tab Scan Profile

## Summary

Phase 22C-11A replaces the active Scan Profile route with a single minimal background-owned path:

Popup Scan Profile -> background handler -> active Douyin tab resolution -> content script ping/self-test -> `DOUYIN_SCAN_PROFILE_MINIMAL_22C11A` -> active works grid target collection -> compact queue adapter -> terminal finalization.

The active route now stamps:

- `scanner_runtime_version = 22C-11A`
- `state_machine_version = 22C-11A`
- `scan_controller_version = 22C-11A-minimal-canonical`
- `active_scan_profile_engine = minimal_active_tab_scanner_22C11A`
- `queue_source_mode = fresh_scan`

## Deletion Audit

| Area | Purpose | References | Action | Reason |
| --- | --- | --- | --- | --- |
| `background.ts` 22C-10I active constants | Previous canonical route markers | Active Scan Profile handler | Replace with 22C-11A | Runtime must not present 22C-10I as active |
| `background.ts` `runCanonicalScanProfile22C10D` active call | Previous canonical orchestrator | Active handler called it | Replace active call with `runScanProfile22C11A` | Active Scan Profile must use one 22C-11A route |
| `contentScript.ts` 22C-10H/I handlers | Previous canonical scan wrappers | Content script message listener | Keep unreachable from active route | Existing tests/debug may still reference; active route uses 22C-11A only |
| `contentScript.ts` 22C9Z3 legacy scroll handler | Old post-probe legacy dispatch | Content script message listener only | Keep unreachable from active route | Not called by background 22C-11A; removal risk isolated to legacy/debug tests |
| `wholeProfileHarvest/state.ts` 22C-9C no-round repair | Legacy no-round validator | State normalization | Bypass for 22C-11A diagnostics | Prevents old direct legacy errors on new path |
| `popup.ts` 22C-10I diagnostics | Popup route witness | Scan Profile dispatch diagnostics | Replace with 22C-11A | Manual diagnostics must prove current route |
| `readiness.ts` expected-count gate | Start Collecting gating | Shared scanner readiness | Keep, adjust terminal-state handling | Incomplete/overcollected remain blocked; unknown expected with queue is allowed |

No Start Collecting, Pause, Resume, Reset, backend flush, Capture Inbox, Review Board, or Reup Score paths were changed.

## Active Path

The popup still sends the compatibility start message `DOUYIN_SCANNER_START_SCAN_PROFILE_22C9I`, but the background handler now creates a `scan_profile_22C11A_` run and dispatches the minimal content-script message:

- self-test: `DOUYIN_SCAN_PROFILE_MINIMAL_22C11A_PING`
- scan: `DOUYIN_SCAN_PROFILE_MINIMAL_22C11A`

The content script collects visible active works grid video anchors only, deduplicates by aweme id, and returns compact targets.

## Count Finalization

- `final_queue_count == expected` -> `success`, `profileScanReady = yes`
- `final_queue_count < expected` -> `incomplete`, `profileScanReady = no`
- `final_queue_count > expected` -> `overcollected`, `profileScanReady = no`
- expected count unknown + queue > 0 -> `success_unknown_expected`, `profileScanReady = yes`
- expected count unknown + queue = 0 -> `canonical_no_targets_found`

`profile_expected_count_semantics_unverified` is no longer a blocking error when the current run produced a valid queue.

## Compact Queue

Durable queue entries remain compact:

- `aweme_id`
- `source_url`
- `profile_url`
- `status`
- `index`
- `discovered_at`
- `discovery_source = active_works_grid_22C11A`

No raw DOM HTML, page-state dumps, normalized card arrays, or large rejected arrays are required for the active route.

## Tests Run

- `npm --workspace @reup-douyin/extension-douyin-capture run test`
- `npm --workspace @reup-douyin/extension-douyin-capture run typecheck`
- `npm --workspace @reup-douyin/extension-douyin-capture run build`

## Manual Retest

1. Reload the unpacked extension from `apps/extension-douyin-capture/dist`.
2. Refresh the target Douyin profile tab.
3. Click Scan Profile.
4. Confirm diagnostics show `22C-11A`, `minimal_active_tab_scanner_22C11A`, `queue_source_mode = fresh_scan`, and no stale 22C-9C/22C-10I Scan Profile failure.
