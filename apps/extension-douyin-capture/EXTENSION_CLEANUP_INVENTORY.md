# Extension cleanup inventory

Phased plan to remove dead/conflicting code without breaking the canonical operator path:
**Scan Profile (22C11B) → Start Collecting (hybrid) → Capture Inbox**.

## Classification

| Class | Meaning | Action |
|-------|---------|--------|
| **P0-product** | Scanner shell, scan/collect, profile context, inbox | Keep |
| **P1-dev** | Guarded beta/pilot, modal whole-profile test, advanced diagnostics | Isolate (Phase 2) |
| **P2-dead** | No DOM binding, no call sites, feature flags off | Delete (Phase 1) |
| **P3-compat** | Route aliases, legacy storage keys, migration readers | Keep |
| **P4-conflict** | Multiple counter/render authorities | Consolidate later (Phase 3) |

## P0-product (do not delete)

- `DOUYIN_SCANNER_START_SCAN_PROFILE_22C11B` → `runScanProfile22C11B` (`routeOwnership.test.ts`)
- `runWholeProfileHarvestProductFromPopup` / `runStartCollectingWorkflow`
- `profileContext.ts`, `expectedCollectContinuationRemaining`, batch continuation UX
- `scheduleWholeProfileHarvestLiveRender`, `patchBatchContinuationChrome`
- `clearLegacyState` / `LEGACY_STATE_KEYS` (operators may still have old storage)

## P2-dead removed in PR-1 (2026-07-06)

Legacy **modal Smart Capture & Harvest** orchestration in `popup.ts` (no buttons in `popup.html`, no `addEventListener`):

- `runSmartCaptureHarvest`, `resumeHarvest`, `retryFailedHarvest`, `stopHarvest`, `flushHarvest`
- `probeHarvest`, `loadHarvestProgress`, `verifyModalHarvestCoverageFromPopup`
- `runWholeProfileStagedHarvestFromPopup`, `startWholeProfileStagedHarvest` (+ staged helpers)
- `resetHarvestStateFromPopup`, `showRuntimeTransitions`
- `resolveProfileQueueFromModal`, `runCaptureCurrentPage`, `runHarvestPlanCurrentPage`, `runProfileScanRequest`, `startHarvestWithBinding`
- `legacyDebugSection` wiring (`SHOW_LEGACY_DEBUG_ACTIONS` always false; section absent from HTML)
- Unused `#resumeHarvestButton` / `#stopHarvestButton` queries (elements not in HTML)

**Kept:** `readSmartState` / `saveSmartState` / `smartStateFromHarvestProgress` for calibration + operational status reconciliation; `renderHarvestProgressPanel` + polling for legacy modal progress cleanup on factory reset.

## P1-dev (Phase 2 — next)

~3k lines in `popup.ts`: guarded hybrid beta/pilot pipeline (`runGuardedHybrid*`, evidence exports).  
**Action:** move to `src/popup/dev/guardedHybridPipeline.ts` without behavior change.

Modal whole-profile test (`runModalWholeProfileTestFromPopup`, `modalWholeProfileTest.ts`) — **keep**, wired from Advanced panel.

## P4-conflict (Phase 3 — deferred)

- Counter authorities: `harvest.queue`, diagnostics persisted totals, inbox summary, `post_scan_counter_snapshot`, `authoritativePopupState`
- Presentation stack: `viewModel` gates + `sanitizePopupViewState` + popup render drivers

Do not delete layers until a single idle/collect-live contract is documented and regression tests cover profile switch + large-profile batch.

## Verification gate (every cleanup PR)

```powershell
cd apps/extension-douyin-capture
npx tsx src/phase18aPopupCleanup.test.ts
npx tsx src/routeOwnership.test.ts
npx tsx src/wholeProfileHarvest.operatorRegression.test.ts
npm run build
```

Manual: scan → collect 500/1002 → batch toast → collect next batch → switch profile.

## Audit helper

```powershell
node scripts/audit-extension-dead-symbols.mjs
```
