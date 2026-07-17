# Phase 18A Extension Cleanup UI Legacy Quarantine Resume

Date: 2026-05-05
Status: Completed

## Summary

Phase 18A cleaned the Douyin extension popup into a single Whole Profile Harvest product surface and quarantined old capture/harvest/CDP/debug controls.

## Key Files

- Feature map: [`featureMap.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest/featureMap.ts:1)
- Canonical state: [`state.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest/state.ts:1)
- Legacy guard: [`legacyGuard.ts`](apps/extension-douyin-capture/src/legacy/legacyGuard.ts:1)
- Legacy state keys: [`legacyStateKeys.ts`](apps/extension-douyin-capture/src/legacy/legacyStateKeys.ts:1)
- Popup UI: [`popup.html`](apps/extension-douyin-capture/public/popup.html:1)
- Popup wiring/adapter: [`popup.ts`](apps/extension-douyin-capture/src/popup.ts:1)
- Phase 18A tests: [`phase18aPopupCleanup.test.ts`](apps/extension-douyin-capture/src/phase18aPopupCleanup.test.ts:1)

## What Remains Visible

- Connection.
- Calibration.
- Verify Profile.
- Dry-run First 3 / Last 3 / Random 3.
- Run Harvest.
- Stop / Resume / Reset Harvest.
- Progress summary.
- Advanced Diagnostics collapsed by default.

## Quarantined

Legacy Capture current page, Smart Capture & Harvest, old Full Modal Harvest controls, old Safe Runner UI, CDP controls, old probe/debug buttons, and legacy state keys are no longer exposed as normal popup actions.

## State Notes

The new canonical key is:

```text
douyinWholeProfileHarvest
```

Phase 18A uses this as a clean UI/product state and keeps adapters to existing V2 verification/harvest internals. It does not fully migrate all harvest implementation state yet.

## Validation

Final validation should use:

```text
npm --workspace @reup-douyin/extension-douyin-capture run test
npm --workspace @reup-douyin/extension-douyin-capture run typecheck
npm --workspace @reup-douyin/extension-douyin-capture run build
```

## Phase 18B Starting Point

Start by replacing remaining V2 adapter state dependencies with native [`douyinWholeProfileHarvest`](apps/extension-douyin-capture/src/wholeProfileHarvest/state.ts:1) transitions. Do not re-enable legacy entrypoints unless a future phase adds explicit product need, request guards, and tests.
