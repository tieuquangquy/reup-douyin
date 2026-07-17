# Extension Code Path Map

## Canonical path summary

The current practical canonical path is:

`Popup Scan Profile -> background DOUYIN_SCANNER_START_SCAN_PROFILE_22C11B or DOUYIN_SCANNER_START_SCAN_PROFILE -> content script DOUYIN_SCAN_PROFILE_MINIMAL_22C11B -> active works grid scan/autoscroll -> background queue adapter -> whole profile harvest state -> Calibration 4 Points -> Start Collecting -> canonical batch/one-item payload -> /douyin-extension/full-modal-harvest -> Capture Inbox`

## Popup entry points

Primary popup responsibilities live in [apps/extension-douyin-capture/src/popup.ts](../../apps/extension-douyin-capture/src/popup.ts):

- Initialization and state rendering.
- Scan Profile optimistic state and background dispatch.
- Dynamic primary action selection.
- Calibration controls.
- Reset controls.
- Legacy/blocked action wrappers.

Popup action lock/error behavior is isolated in [apps/extension-douyin-capture/src/popupActions.ts](../../apps/extension-douyin-capture/src/popupActions.ts).

## Background routes

Background message routing lives in [apps/extension-douyin-capture/src/background.ts](../../apps/extension-douyin-capture/src/background.ts).

Observed scan route alignment:

- Current accepted Scan Profile route names: DOUYIN_SCANNER_START_SCAN_PROFILE_22C11B and DOUYIN_SCANNER_START_SCAN_PROFILE.
- Background route persists accepted scan state, then starts asynchronous scan execution.
- Background scan engine diagnostic says minimal_active_works_grid_scanner_22C11B.
- Background queue adapter maps content response into target details and queue items.
- Terminal success currently uses scroll_converged_queue_accepted_22C11B when queue count is greater than zero.

Other background capabilities:

- CDP harvest/session helpers are still present.
- Backend post wrapper is imported.
- Auth synchronization helpers exist.
- Diagnostic persistence and storage compaction are active and can mutate state.

## Content script routes

Content message routing lives in [apps/extension-douyin-capture/src/contentScript.ts](../../apps/extension-douyin-capture/src/contentScript.ts).

Observed live/important handlers:

- DOUYIN_SCANNER_PING / REUP_DOUYIN_PING: readiness and handler inventory.
- Runtime authority snapshot route using 22C11B naming.
- DOUYIN_NETWORK_PROBE_STATUS_22C12A_R3: passive probe status.
- Manual pagination truth test 22C13A: diagnostic only unless invoked.
- DOUYIN_SCAN_PROFILE_MINIMAL_22C11B_PING: handler existence check.
- DOUYIN_SCAN_PROFILE_MINIMAL_22C11B: current active minimal profile scan route.
- Calibration routes for right rail calibration.
- Safe harvest runner routes for start/resume/stop/reset/flush.

Current scanner functions in [apps/extension-douyin-capture/src/contentScript.ts](../../apps/extension-douyin-capture/src/contentScript.ts):

- collect active works anchors from profile grid.
- detect active works tab/count text.
- select likely scroll container or window.
- dispatch synthetic wheel/scroll actions.
- repeat until stable/bottom/no-new/max-duration/checkpoint.
- merge passive network probe targets into DOM targets.

## Controller routes

Controller state machine lives in [apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts](../../apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts).

Key active responsibilities:

- Read/write whole profile harvest state while preserving calibration.
- Migrate/sanitize legacy scanner state on read.
- Verify/scan profile via runtime transport.
- Prepare/navigate/resolve profile pages.
- Complete profile verification and classification.
- Enforce allowed scanner runner targets.
- Block or recover forbidden legacy runner targets.
- Start Collecting preflight: calibration, queue, backend session.
- Run next-10 safe collection and one-item save routes.
- Reset scan/harvest state with mode-specific preservation.

## Scanner routes

Thin scanner adapter lives in [apps/extension-douyin-capture/src/wholeProfileHarvest/profileScanner.ts](../../apps/extension-douyin-capture/src/wholeProfileHarvest/profileScanner.ts):

- Calls transport scanProfile with tab id and profile URL.
- Converts successful scan cards into validated targets.
- Preserves scan diagnostics: rounds, stop reason, partial scan, expected count, missing count.
- Maps legacy scanner failure reasons into error codes for compatibility.

Actual DOM/network scanning currently lives in [apps/extension-douyin-capture/src/contentScript.ts](../../apps/extension-douyin-capture/src/contentScript.ts), not in [apps/extension-douyin-capture/src/wholeProfileHarvest/profileScanner.ts](../../apps/extension-douyin-capture/src/wholeProfileHarvest/profileScanner.ts).

## Calibration routes

Calibration storage and types are in [apps/extension-douyin-capture/src/wholeProfileHarvest/calibration.ts](../../apps/extension-douyin-capture/src/wholeProfileHarvest/calibration.ts).

Calibration UI and capture are in [apps/extension-douyin-capture/src/contentScript.ts](../../apps/extension-douyin-capture/src/contentScript.ts).

Controller preservation/hydration is in [apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts](../../apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts).

Popup controls are in [apps/extension-douyin-capture/src/popup.ts](../../apps/extension-douyin-capture/src/popup.ts).

## Collection routes

- Start Collecting preflight and dispatch: [apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts](../../apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts)
- Safe modal collection runner in content script: [apps/extension-douyin-capture/src/contentScript.ts](../../apps/extension-douyin-capture/src/contentScript.ts)
- Canonical payload builder and guards: [apps/extension-douyin-capture/src/wholeProfileHarvest/canonicalHarvest.ts](../../apps/extension-douyin-capture/src/wholeProfileHarvest/canonicalHarvest.ts)
- Backend full modal post and guard: [apps/extension-douyin-capture/src/extensionBackendClient.ts](../../apps/extension-douyin-capture/src/extensionBackendClient.ts)

## Backend flush routes

- Path: /douyin-extension/full-modal-harvest.
- Guarded local callers include whole_profile_staged_harvest_v2_direct and whole_profile_one_item_collect_save.
- Disallowed fields include diagnostics/debug/trace/state/runtime/tokens/cookies/authorization/secrets/headers and related raw storage fields.
- Capture Inbox payload requires capture_session_id, item aweme/source URL, duration, and four metric counts.

## Storage keys

Key groups live in [apps/extension-douyin-capture/src/storageKeys.ts](../../apps/extension-douyin-capture/src/storageKeys.ts).

Current important keys/groups:

- apiBaseUrl.
- installId.
- lastCaptureSessionId / lastCaptureId.
- right rail calibration key.
- DOUYIN_SCANNER_CALIBRATION_KEY and DOUYIN_SCANNER_STORAGE_ROOT_KEY.
- safe harvest run state.
- harvest runtime v2.
- harvest pending flush queue v2.
- full modal harvest state/flush queue.
- smart capture harvest state.
- legacy CDP/debug/state/queue/retry/failed keys.

Reset groups:

- HARVEST_STATE_STORAGE_KEYS clears harvest/progress/cache/legacy harvest keys.
- CALIBRATION_STATE_STORAGE_KEYS clears calibration and probe keys.
- FACTORY_RESET_LOCAL_STORAGE_KEYS combines harvest and calibration keys.
- FACTORY_RESET_SYNC_STORAGE_KEYS clears last capture id/session id.

## Legacy/deprecated/fallback paths and conflicts

- Legacy guard and clear helpers exist in [apps/extension-douyin-capture/src/legacy/legacyGuard.ts](../../apps/extension-douyin-capture/src/legacy/legacyGuard.ts) and [apps/extension-douyin-capture/src/legacy/legacyStateKeys.ts](../../apps/extension-douyin-capture/src/legacy/legacyStateKeys.ts).
- Controller still contains deprecated real modal extraction code and explicit forbidden runner target handling in [apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts](../../apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts).
- Content script still contains CDP-era/safe-harvest/diagnostic/pagination/network probe generations in [apps/extension-douyin-capture/src/contentScript.ts](../../apps/extension-douyin-capture/src/contentScript.ts).
- Background still contains CDP harvest helpers alongside the Scan Profile route in [apps/extension-douyin-capture/src/background.ts](../../apps/extension-douyin-capture/src/background.ts).
- Tests reference 22C12F/22C13A network-first authority while current active route reports 22C11B/minimal active works. Treat this as marker/test drift until proven otherwise.

## Duplicated handlers and possible conflicts

- Scan Profile has at least two background action names accepted: DOUYIN_SCANNER_START_SCAN_PROFILE_22C11B and DOUYIN_SCANNER_START_SCAN_PROFILE.
- Content script has minimal scanner, passive network probe, network-first helper, pagination diagnostics, activation diagnostics, and safe harvest runner in one file.
- Primary action selection exists in popup and controller-side preflight/diagnostic state, so cleanup must not introduce disagreement.
- Reset behavior exists in popup, controller, and extension reset modules; destructive scope must remain explicit.
