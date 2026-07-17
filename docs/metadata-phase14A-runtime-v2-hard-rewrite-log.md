# Phase 14A Runtime V2 Hard Rewrite Log

## Root cause

- The production extension still had two harvest state systems:
  - popup/header state from `douyinSmartHarvestState`
  - progress/panel state from `douyinFullModalHarvestState` and normalized `FullModalHarvestProgress`
- The exact conflicting code paths were:
  - `apps/extension-douyin-capture/src/popup.ts` `renderOperationalStatus(...)` deriving header state from `smartStateFromHarvestProgress(...)`
  - `apps/extension-douyin-capture/src/popupProgress.ts` `normalizeHarvestState(...)` inferring paused from legacy `can_resume` / heartbeat rules
  - `apps/extension-douyin-capture/src/contentScript.ts` legacy `douyinFullModalHarvestState` restore/start/resume/stop path
- That allowed a successful item/checkpoint to keep the runner alive while the popup still rendered `paused` / `Resume Harvest` from stale legacy state.

## Canonical state

- New runtime key: `douyinHarvestRuntimeV2`
- New pending queue key: `douyinHarvestPendingFlushQueueV2`
- Schema version: `phase14a_runtime_v2`

## Legacy keys deleted/ignored

- `harvestState`
- `smartHarvestState`
- `fullModalHarvestState`
- `modalHarvestProgress`
- `harvestProgress`
- `smartCaptureState`
- `resumeState`
- `douyinFullModalHarvestState`
- `douyinFullModalHarvestProgress`
- `douyinSmartCaptureHarvestState`
- `douyinSmartHarvestState`
- `douyinTargetAwemeQueue`
- `douyinPendingFlushQueue`
- `douyinRetryQueue`
- `douyinFailedQueue`
- `douyinHarvestRuntimePhase11`
- `douyinHarvestRuntimePhase12`
- `douyinHarvestRuntimePhase13`
- `reupDouyinFullModalHarvestFlushQueue`

## Runtime design

- Content script owns singleton runner:
  - `window.__REUP_DOUYIN_HARVEST_RUNNER_V2`
- Popup sends commands only.
- Popup progress/header reads only runtime V2-derived progress.
- No migration of old paused state into V2.

## Continuous draining behavior

- `drainHarvestQueueV2(runId)` loops until:
  - no pending targets -> final flush -> completed
  - explicit stop -> paused/operator_stop
  - real pause/fail condition
- Successful item:
  - stays `running`
  - advances `current_target_index`
  - continues to next pending target automatically

## Allowed pause reasons

- `operator_stop`
- `backend_flush_failed`
- `content_script_unavailable`
- `calibration_invalid`
- `captcha_required`
- `consecutive_failures`

## Reset behavior

- Reset deletes runtime V2, pending queue V2, and all legacy harvest keys.
- Reset preserves:
  - API base URL
  - calibration
  - harvest mode

## Tests run

- `npm --workspace @reup-douyin/extension-douyin-capture run test`
- `npm --workspace @reup-douyin/extension-douyin-capture run typecheck`
- `npm --workspace @reup-douyin/extension-douyin-capture run build`
