# Phase 22C-2B Start Collecting Reconcile/Finalized Metadata Resume

## Completed
- Added Start Collecting queue reconciliation in [`reconcileHarvestQueueForStartCollecting()`](apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts:380) so stored queue items are refreshed from latest classification and profile target details before selection.
- Wired reconciliation into [`runStartCollectingWorkflow()`](apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts:1446) and [`runOneItemCollectAndSave()`](apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts:3786).
- Added finalized metadata detection in [`targetHasFinalizedMetadata()`](apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts:370), covering classification-backed existing items and profile-detail-backed backend items with `ready` or `complete` metadata.
- Updated [`getFirstPendingTargetForOneItemCollect()`](apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts:416) to avoid reopening finalized targets.
- Added focused regressions in [`apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts) for session reuse, finalized existing-item skipping, hydrated detail handling, and Next 3 safe batch summary behavior after finalized-metadata awareness.
- Added implementation log in [`docs/metadata-phase22C-2B-start-collecting-reconcile-log.md`](docs/metadata-phase22C-2B-start-collecting-reconcile-log.md).

## Validation Status
- Passed focused whole-profile harvest tests with [`npx tsx src/wholeProfileHarvest.test.ts`](apps/extension-douyin-capture/package.json:8) from [`apps/extension-douyin-capture`](apps/extension-douyin-capture).
- Passed full extension validation with [`npm test`](apps/extension-douyin-capture/package.json:8), including extension test suite, [`npm run build`](apps/extension-douyin-capture/package.json:6), and dist module resolution.
- Backend tests were not run because this step touched only extension and docs files.

## Files Touched In This Step
- [`apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts)
- [`apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts)
- [`docs/metadata-phase22C-2B-start-collecting-reconcile-log.md`](docs/metadata-phase22C-2B-start-collecting-reconcile-log.md)
- [`docs/metadata-phase22C-2B-start-collecting-reconcile-resume.md`](docs/metadata-phase22C-2B-start-collecting-reconcile-resume.md)

## Notes For Future Work
- The finalized metadata guard is scoped to one-item Start Collecting selection and does not introduce backend schema changes.
- Safe batch pending summary expectations now account for finalized/complete queue awareness, avoiding misleading `next_pending_aweme` output when the remaining queue head should not be collected.
- Future refinements should keep queue reconciliation at the controller boundary and avoid pushing product workflow decisions into shared infrastructure.
