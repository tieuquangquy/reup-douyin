# Phase 18I-D Real Modal Extraction Queue Log

## Scope
Implemented Phase 18I-D scoped changes for whole-profile harvest using the canonical target queue with real modal extraction, per-target local checkpoints, stop/resume durability, captcha pause handling, and explicit extraction-only UX without backend writes, capture-session creation, Capture Inbox creation, legacy runtime reuse, or fake metric simulation.

## Completed Changes

### Extension Runtime
- Updated persisted whole-profile harvest state in [`state.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest/state.ts):
  - queue/result status taxonomy now uses `extracted`
  - queue item field `extraction_result`
  - result metadata includes `target_url`, `data_integrity_status`, `profile_card_evidence`, and `started_at`
  - harvest execution mode supports `real_modal_extraction_no_backend`
- Re-routed [`runHarvest()`](apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts:189) and [`resumeHarvest()`](apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts:209) to [`runRealModalExtractionHarvest()`](apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts:514).
- Implemented real extraction loop behavior in [`runRealModalExtractionHarvest()`](apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts:514):
  - enforce verify/dry-run/calibration guards
  - prepare the harvest queue from verified targets
  - open direct modal URL for each target
  - extract real modal metrics
  - validate identity before marking success
  - checkpoint locally after each success or failure
  - pause when captcha/checkpoint is detected
  - never create capture sessions or flush backend payloads in the active Phase 18I-D path
- Preserved durable stop/resume by reusing persisted queue/results and `resume_from_index`.
- Updated local completion/pause helpers in [`controller.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts) to use extraction-only wording and counters.

### Canonical Helper Compatibility
- Updated [`buildCanonicalHarvestQueue()`](apps/extension-douyin-capture/src/wholeProfileHarvest/canonicalHarvest.ts:48) so completed items are recognized via `extracted` results and queue items initialize `extraction_result`.
- Updated [`canonicalResultFromSuccess()`](apps/extension-douyin-capture/src/wholeProfileHarvest/canonicalHarvest.ts:137) to match the expanded Phase 18I-D result contract while remaining compile-safe for canonical helper usage.

### Popup / Progress / Operator Messaging
- Updated status and action copy in [`popup.ts`](apps/extension-douyin-capture/src/popup.ts) to explicitly state: extraction only, no backend writes yet.
- Updated [`wholeProfileProgressSummary()`](apps/extension-douyin-capture/src/wholeProfileHarvest/progress.ts:3) labels from simulation wording to extraction/execution/backend-write wording.
- Recent progress rows now display `EXTRACTED` results and modal extraction provenance instead of mock labels.

### Tests
- Updated [`wholeProfileHarvest.test.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts) to assert:
  - active mode is `real_modal_extraction_no_backend`
  - modal opening occurs during harvest
  - no capture session is created
  - no backend flush occurs
  - checkpointed queue/results survive stop and resume
  - extracted statuses replace prior mock-only statuses
- Confirmed no remaining stale `updated_mock`, `simulated_result`, `MOCK_OK`, or old progress-key strings remain in extension TypeScript sources relevant to this phase.

## Validation Runs

### Extension
- `npx tsc -p apps/extension-douyin-capture/tsconfig.json --noEmit` ✅
- `npm --workspace @reup-douyin/extension-douyin-capture run build` ✅
- `npm --workspace @reup-douyin/extension-douyin-capture run test` ✅

## Notes
- A direct `node --test` run for [`wholeProfileHarvest.test.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts) is not representative for this workspace because the tests import `.js` specifiers and are intended to run through [`tsx`](apps/extension-douyin-capture/package.json).
- Phase 18I-D remains strictly extraction-only on the active path: no backend records, no capture-session creation, and no Capture Inbox side effects are produced.
- Captcha/checkpoint detection is treated as a pause boundary, not a bypass flow.
