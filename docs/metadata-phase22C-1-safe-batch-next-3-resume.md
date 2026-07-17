# Phase 22C-1 Safe Batch Next 3 Resume

## Completed
- Confirmed `runStartCollectingWorkflow()` dispatches to `runBatchCollectNext3SafeMode()` when `effective_batch_limit > 1` and keeps `runOneItemCollectAndSave()` for `batch_limit = 1`.
- Exported [`runBatchCollectNext3SafeMode()`](apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts) for direct test coverage.
- Preserved the existing queue during `next_3_safe` batch execution so the delegated one-item runner no longer rewrites the queue down to one target on the first item.
- Preserved cumulative `processed / updated / flushed / failed` counters across the whole safe batch instead of resetting them after each one-item save.
- Added explicit no-pending batch completion behavior instead of falling back to the one-item path when the queue has no eligible targets.
- Added regression coverage in [`apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts) for cap-to-3, queue preservation, session reuse, checkpoint ordering, skip rules, no-pending behavior, and safe stop conditions.
- Added Phase 22C-1 handoff docs in [`docs/metadata-phase22C-1-safe-batch-next-3-log.md`](docs/metadata-phase22C-1-safe-batch-next-3-log.md) and [`docs/metadata-phase22C-1-safe-batch-next-3-resume.md`](docs/metadata-phase22C-1-safe-batch-next-3-resume.md).

## Key Findings
- The existing one-item backend-proof runner already contains the extraction, payload guard, save, verify, and checkpoint behavior needed for this phase, so safe batching can stay as a thin orchestrator around that runner.
- Reusing the same stored session works naturally because the one-item path already goes through [`ensureBackendCaptureSession()`](apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts:1937), which prefers the existing verified session before creating a new one.
- Skipping already-saved queue entries is safest before dispatching the one-item runner so Phase 22C-1 remains sequential and does not redo successful work.
- The missing regression gap from the earlier attempt was real: direct `batch_limit: 3` coverage was still asserting one-item semantics, and the first delegated one-item run could collapse the queue unless the existing queue was preserved explicitly.

## Validation Status
- Passed: focused whole-profile extension test file command
- Pending in this resume note until full command rerun from the current turn: workspace test / typecheck / build
- Backend validation is not required because this phase stayed inside the extension.

## Files Touched In This Phase
- [`apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts)
- [`apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts)
- [`docs/metadata-phase22C-1-safe-batch-next-3-log.md`](docs/metadata-phase22C-1-safe-batch-next-3-log.md)
- [`docs/metadata-phase22C-1-safe-batch-next-3-resume.md`](docs/metadata-phase22C-1-safe-batch-next-3-resume.md)
