# Phase 18A Extension Cleanup UI Legacy Quarantine Log

Date: 2026-05-05
Status: Completed

## 1. Why the Extension Needed Cleanup

The popup had accumulated overlapping capture, harvest, modal, CDP, safe-runner, and debug controls from many phases. That made the product path ambiguous and increased the risk that real backend writes could originate from a legacy path rather than the new Whole Profile Harvest flow.

Phase 18A narrows the operator-facing extension to one product surface: Whole Profile Harvest.

## 2. Features Kept

The clean feature map in [`featureMap.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest/featureMap.ts:1) keeps only:

- Connection status and Local API base URL.
- Calibration with Calibrate 4 Points, Test Current Video, and Reset Calibration.
- Whole Profile Harvest controls: Verify Profile, Dry-run First 3, Dry-run Last 3, Dry-run Random 3, Run Harvest, Stop, Resume, Reset Harvest.
- Progress summary and debug JSON copy.
- Advanced diagnostics, collapsed by default.

## 3. Legacy Features Hidden/Quarantined

The popup UI in [`popup.html`](apps/extension-douyin-capture/public/popup.html:1) no longer renders user-facing legacy buttons for:

- Capture current page.
- Smart Capture & Harvest.
- Attach/Detach/Show CDP tools.
- Probe Current Modal via CDP.
- Legacy Full Modal Harvest start/resume/flush/progress actions.
- Modal Whole Profile Test beta as a visible action.
- Phase/debug buttons not required for Whole Profile Harvest.

## 4. New State Key

Phase 18A adds the canonical state key [`WHOLE_PROFILE_HARVEST_STATE_KEY`](apps/extension-douyin-capture/src/wholeProfileHarvest/state.ts:1):

```text
douyinWholeProfileHarvest
```

The state schema is [`phase18a_whole_profile_harvest`](apps/extension-douyin-capture/src/wholeProfileHarvest/state.ts:2), initialized by [`createWholeProfileHarvestIdleState()`](apps/extension-douyin-capture/src/wholeProfileHarvest/state.ts:25).

## 5. Legacy State Keys

Legacy keys are listed in [`LEGACY_STATE_KEYS`](apps/extension-douyin-capture/src/legacy/legacyStateKeys.ts:1), including old safe-runner, runtime, full-modal, smart-harvest, pending queues, Capture Session aliases, Modal Whole Profile Test, staged V2 state, and CDP debug/status keys.

Diagnostics can read them through [`getLegacyStateSummary()`](apps/extension-douyin-capture/src/legacy/legacyStateKeys.ts:26). The Clear Legacy State action uses [`clearLegacyState()`](apps/extension-douyin-capture/src/legacy/legacyStateKeys.ts:33) and intentionally does not clear calibration.

## 6. Legacy Guard

[`blockLegacyHarvestEntrypoint()`](apps/extension-douyin-capture/src/legacy/legacyGuard.ts:8) returns:

```json
{
  "ok": false,
  "code": "legacy_feature_disabled",
  "message": "This legacy harvest feature is disabled. Use Whole Profile Harvest."
}
```

The popup wires old button references, if present, to guarded blocked actions in [`popup.ts`](apps/extension-douyin-capture/src/popup.ts:266), preventing legacy user-triggered backend writes.

## 7. New UI

The popup title is now Douyin Whole Profile Harvest. The visible sections are:

1. Connection.
2. Calibration.
3. Harvest Workflow.
4. Progress.
5. Controls.
6. Advanced Diagnostics, collapsed by default.
7. Details.

The UI avoids long JSON by default and exposes Copy Debug JSON only under Advanced Diagnostics.

## 8. Tests Run

Focused checks run during implementation:

```text
npm --workspace @reup-douyin/extension-douyin-capture run typecheck
npm --workspace @reup-douyin/extension-douyin-capture run build
npx --workspace @reup-douyin/extension-douyin-capture tsx src/phase18aPopupCleanup.test.ts
```

The final verification commands are recorded in the resume document after full validation.

## 9. Next Phase 18B

Phase 18B should migrate more runtime logic from legacy V2 adapters into [`douyinWholeProfileHarvest`](apps/extension-douyin-capture/src/wholeProfileHarvest/state.ts:1), refine backend item creation only if needed, and keep all non-product legacy entrypoints blocked until explicitly redesigned.
