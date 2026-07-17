# Phase 14A Runtime V2 Resume

## What changed

- Harvest production runtime moved to `douyinHarvestRuntimeV2`.
- Content script now owns continuous queue draining.
- Legacy `FullModalHarvestController` path is removed from production content-script routing.
- Popup harvest commands now use:
  - `REUP_DOUYIN_START_HARVEST_V2`
  - `REUP_DOUYIN_RESUME_HARVEST_V2`
  - `REUP_DOUYIN_STOP_HARVEST_V2`
  - `REUP_DOUYIN_GET_HARVEST_RUNTIME_V2`
  - `REUP_DOUYIN_RESET_HARVEST_RUNTIME_V2`

## Key files

- `apps/extension-douyin-capture/src/harvestRuntimeV2.ts`
- `apps/extension-douyin-capture/src/contentScript.ts`
- `apps/extension-douyin-capture/src/popup.ts`
- `apps/extension-douyin-capture/src/storageKeys.ts`
- `apps/extension-douyin-capture/src/extensionReset.ts`
- tests:
  - `apps/extension-douyin-capture/src/harvestRuntimeV2.test.ts`
  - updated popup/reset tests

## Live retest

1. Build extension.
2. Reload unpacked extension.
3. Open a calibrated Douyin modal.
4. Run `Smart Capture & Harvest`.
5. Verify video #1 success does not switch UI to paused.
6. Verify target index advances automatically to #2 without popup interaction.
7. Verify Stop sets paused with reason `operator_stop`.
8. Verify Resume continues multiple targets, not one-step.

