# Phase 18I-C Local Queue + Checkpoint + Resume Log

## Scope
Implemented Phase 18I-C scoped changes for local-only whole-profile harvest queue simulation, checkpoint persistence, stop/resume behavior, popup/debug visibility, and extension tests without modal opening, backend flush, capture-session creation, or legacy/V2 runtime use.

## Completed Changes

### Extension
- Expanded [`douyinWholeProfileHarvest`](apps/extension-douyin-capture/src/wholeProfileHarvest/state.ts) state to support local checkpoint simulation metadata:
  - queue item `capture_status`
  - queue item `checkpoint_sequence`
  - queue item `simulated_result`
  - harvest `simulation_mode`
  - harvest `checkpoint_count`
  - harvest `resume_from_index`
- Updated result/queue status taxonomy from `updated` to `updated_mock` for local simulation-only outcomes.
- Reworked [`runHarvest()`](apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts:214) and [`resumeHarvest()`](apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts:214) to use local checkpoint simulation flow instead of canonical modal/backend execution.
- Added local helpers in [`controller.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts):
  - [`prepareHarvestQueue()`](apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts:596)
  - [`findNextPendingQueueIndex()`](apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts:653)
  - [`buildSimulatedHarvestResult()`](apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts:658)
  - [`checkpointLocalHarvestTarget()`](apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts:697)
  - [`pauseHarvestSimulation()`](apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts:734)
  - [`finalizeLocalHarvestSimulation()`](apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts:751)
- Updated [`stopHarvest()`](apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts:188) to pause simulation and persist `resume_from_index`.
- Updated [`resetHarvest()`](apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts:225) to preserve calibration and prior verify/profile-scan/dry-run layers while clearing harvest simulation progress.
- Fixed resume semantics so paused queues/results are reused instead of rebuilt on resume.
- Kept canonical helper files compile-safe with the new state types while preserving non-Phase-18I-C paths.

### Popup / Progress
- Updated popup action wording in [`popup.ts`](apps/extension-douyin-capture/src/popup.ts) to describe local checkpoint-only simulation rather than canonical harvest execution.
- Updated [`wholeProfileProgressSummary()`](apps/extension-douyin-capture/src/wholeProfileHarvest/progress.ts:3) to expose:
  - simulation mode
  - checkpoint count
  - resume index
  - simulation-specific recent result labels

### Tests
- Reworked [`wholeProfileHarvest.test.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts) to assert Phase 18I-C behavior:
  - local simulation completes without modal opening
  - no backend flush occurs
  - no capture session is created
  - pause preserves queue/results
  - resume continues from persisted pending target
  - reset preserves calibration
- Updated assertions to match implemented local checkpoint accounting and completion states.

## Validation Runs

### Extension
- `npm --workspace @reup-douyin/extension-douyin-capture run typecheck` ✅
- `npm --workspace @reup-douyin/extension-douyin-capture run build` ✅
- `npm --workspace @reup-douyin/extension-douyin-capture run test` ⏳ in progress during documentation update

## Notes
- Phase 18I-C is intentionally simulation-only: no modal opening, metric extraction, backend flush, or capture-session creation should occur in this flow.
- Resume correctness required preserving paused queue/results in [`prepareHarvestQueue()`](apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts:596) rather than rebuilding from profile scan targets.
- Current checkpoint count reflects completed simulated result rows, not intermediate processing writes.
