# Phase 18I-E Captcha-Safe Scheduler Resume

## Current State
Phase 18I-E is implemented for the requested extension-only scope:
- Whole-profile harvest remains on the extraction-only `real_modal_extraction_no_backend` path.
- The active queue uses randomized between-target waits and scheduled safety pauses based on the selected speed policy.
- Stop requests are honored while the queue is waiting or paused, so the operator can halt safely without forcing another target to run.
- Captcha, checkpoint, login-required, abnormal-traffic, and access-denied conditions pause the run before unsafe continuation.
- Tab-health failures also pause the run when the content script is missing, the page context is no longer valid, or the active tab is no longer safe for extraction.
- Resume uses persisted local queue state plus `resume_from_index`; it does not use legacy runtime state or V2 staged harvest state.
- Popup/progress output now surfaces pause message, resume availability, captcha evidence, delay state, scheduled-pause state, tab health, and resume preflight status.
- No capture session is created.
- No backend flush is performed.
- No Capture Inbox items are created by this Phase 18I-E run path.
- Extension [`typecheck`](apps/extension-douyin-capture/package.json), full workspace extension [`test`](apps/extension-douyin-capture/package.json), and build-through-test flow are passing in the current environment.

## What Was Delivered
- Safety-state persistence and normalization updates in [`state.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest/state.ts).
- Delay/pause scheduling policy in [`delayPolicyForSpeed()`](apps/extension-douyin-capture/src/wholeProfileHarvest/canonicalHarvest.ts:174).
- Runtime safety enforcement in [`runRealModalExtractionHarvest()`](apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts:627), [`checkHarvestTabHealth()`](apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts:334), and [`pauseHarvest()`](apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts:566).
- Captcha/checkpoint normalization in [`normalizeCaptchaCheck()`](apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts:315).
- Operator-facing safety visibility in [`wholeProfileProgressSummary()`](apps/extension-douyin-capture/src/wholeProfileHarvest/progress.ts:3) and [`runWholeProfileControllerAction()`](apps/extension-douyin-capture/src/popup.ts:356).
- Phase 18I-E extension tests in [`wholeProfileHarvest.test.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts) for safety pauses, stop durability, progress fields, and no-backend guarantees.

## Validation Snapshot
- `npm --workspace @reup-douyin/extension-douyin-capture run typecheck` ✅
- `npm --workspace @reup-douyin/extension-douyin-capture run test` ✅

## Follow-up (if continuing)
1. If future work adds more scheduler behavior, keep it inside the extension worker/controller layer and preserve extraction-only semantics until a later phase explicitly reintroduces backend flush.
2. Preserve manual-operator pause boundaries for captcha, checkpoint, login, abnormal-traffic, access-denied, and broken tab-health conditions.
3. Keep resume strictly local-state-driven so crash recovery and operator restarts remain durable and do not depend on hidden runtime memory.
