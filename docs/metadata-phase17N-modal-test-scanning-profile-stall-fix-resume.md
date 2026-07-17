# Phase 17N Modal Test Scanning Profile Stall Fix Resume

## Scope

Phase 17N is limited to `apps/extension-douyin-capture` and docs/tests for the isolated Modal Whole Profile Test. It does not change Tile Gallery, modal metrics extraction, calibration, CDP/debug workflow, production Smart Capture behavior, or full-modal-harvest.

## Implemented Behavior

- Same-context profile-ready diagnostics call the profile scanner directly without a global detector reconnect.
- `scanning_profile` persists scanner start and heartbeat timestamps.
- Scanner rounds stream progress into `douyinModalWholeProfileTestRun`.
- Popup rendering uses persisted scan progress instead of showing indefinite unknown/no values.
- Stale scanner heartbeat can be resumed/repaired through `resumeModalWholeProfileProfileScan(runId)`.
- Hard scan timeout fails with `profile_scan_timeout`.
- Stale heartbeat/no progress fails with `profile_scan_stalled`.
- Runner startup failure fails with `profile_scan_runner_not_started`.
- Harvest-plan failure fails with `harvest_plan_failed`.
- Verify-only harvest-plan transition uses `douyin_extension_harvest_plan.v1` and `refresh_all`.
- Verify-only still writes only the isolated modal test runtime and does not call full-modal-harvest.

## Root Cause To Remember

The previous state machine could enter `scanning_profile` before durable scanner progress existed. If scanner execution hung or never updated runtime, popup state stayed running forever with stale detector UI. The fix makes scanner execution the active state-machine step and gives it heartbeat, timeout, resume, and precise failure paths.

## Files Touched

- `apps/extension-douyin-capture/src/modalWholeProfileTest.ts`
- `apps/extension-douyin-capture/src/popup.ts`
- `apps/extension-douyin-capture/src/modalWholeProfileTest.test.ts`
- `docs/metadata-phase17N-modal-test-scanning-profile-stall-fix-log.md`
- `docs/metadata-phase17N-modal-test-scanning-profile-stall-fix-resume.md`

## Final Validation Commands

Run from repository root:

```cmd
npm --workspace @reup-douyin/extension-douyin-capture run test
npm --workspace @reup-douyin/extension-douyin-capture run typecheck
npm --workspace @reup-douyin/extension-douyin-capture run build
```

## Live Retest Checklist

1. Reload the extension.
2. Open a supported Douyin modal profile URL.
3. Run Advanced / Beta `Test Modal → Whole Profile Harvest`.
4. Verify no-reload close reaches a profile URL without `modal_id`.
5. Verify `scanning_profile` shows live scan rounds and heartbeat-derived progress.
6. Reopen popup during scan; if heartbeat is stale, verify it resumes the existing run rather than starting a conflicting run.
7. Verify stale global detector error is not shown while same-context profile diagnostics are present.
8. Verify successful card scan transitions to harvest-plan and completes verify-only mode.
9. Verify failure cases show precise reasons instead of staying `running` forever.
