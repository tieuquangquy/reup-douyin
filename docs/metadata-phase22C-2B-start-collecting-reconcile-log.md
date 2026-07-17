# Phase 22C-2B Start Collecting Reconcile/Finalized Metadata Log

## Scope
- Implement Phase 22C-2B follow-up only.
- Keep the existing Next 3 safe batch, popup realtime subscription, and queue-derived counter work intact.
- Add Start Collecting queue hydration/reconcile before target selection.
- Add finalized metadata guardrails so one-item Start Collecting does not reopen items already finalized in Capture Inbox metadata.
- Add focused extension regression coverage for the new Start Collecting behavior and second-run stability.
- Do not introduce backend schema changes, crawler logic, or unrelated UI redesign.

## Changes Applied
- [`targetHasFinalizedMetadata()`](apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts:370) now treats a target as finalized when classification already maps it to an existing backend item with `ready`/`complete` metadata, or when hydrated profile target details carry a backend item with finalized metadata.
- [`reconcileHarvestQueueForStartCollecting()`](apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts:380) now refreshes queue item source fields and profile-card evidence from the latest classification and profile detail state before Start Collecting or one-item collect runs.
- [`runStartCollectingWorkflow()`](apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts:1446) now starts from reconciled queue state instead of using raw stored queue data directly.
- [`runOneItemCollectAndSave()`](apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts:3786) now also starts from reconciled queue state so direct one-item execution uses the same latest metadata view.
- [`getFirstPendingTargetForOneItemCollect()`](apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts:416) now skips queue items that are already finalized by backend metadata, preventing redundant modal open/save attempts.

## Regression Coverage Added
- [`apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts) now verifies repeated Start Collecting still reuses the same backend capture session after the new reconcile behavior is applied.
- [`apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts) now verifies Start Collecting skips a queue target when classification already marks it with an existing backend item and finalized metadata.
- [`apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts) now verifies reconciled queue state preserves hydrated finalized-detail evidence while Start Collecting completes without reopening that finalized target.
- [`apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts) expectations for Next 3 safe batch were updated to match the new finalized-metadata-aware pending summary behavior.

## Validation Notes
- Ran [`npx tsx src/wholeProfileHarvest.test.ts`](apps/extension-douyin-capture/package.json:8) in the extension workspace.
- Ran full extension validation with [`npm test`](apps/extension-douyin-capture/package.json:8), which also covers extension tests, [`npm run build`](apps/extension-douyin-capture/package.json:6), and dist module resolution.
- No backend files were touched in this step, so no backend-specific test run was required.
