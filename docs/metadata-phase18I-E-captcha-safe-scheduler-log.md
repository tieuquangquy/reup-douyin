# Phase 18I-E Captcha-Safe Scheduler Log

## Scope
Implemented the Phase 18I-E extension-only hardening for whole-profile harvest safety scheduling: randomized between-target waits, scheduled operator pauses, cancellable stop behavior during waits, stronger captcha/checkpoint/login/traffic-block detection, tab-health pause boundaries, resume preflight checks, and popup/progress visibility for manual operator recovery. The active run path remains extraction-only with no backend flush, no capture-session creation, no Capture Inbox side effects, no legacy runtime reuse, and no V2 runtime fallback.

## Completed Changes

### Extension Runtime
- Extended persisted whole-profile harvest safety state in [`state.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest/state.ts) so the run records:
  - captcha/checkpoint/login-required/abnormal-traffic detection flags
  - evidence text and current blocked URL
  - consecutive error counters and configured threshold
  - processed-target count since the last scheduled pause
  - last randomized delay timing and last scheduled pause timing
  - tab-health status and resume-preflight status
  - pause messaging, last safety event, and resume availability
- Hardened real extraction execution in [`runRealModalExtractionHarvest()`](apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts:627) to:
  - use Phase 18I-E speed policy from [`delayPolicyForSpeed()`](apps/extension-douyin-capture/src/wholeProfileHarvest/canonicalHarvest.ts:174)
  - apply randomized delay windows between targets
  - trigger scheduled pauses after the configured processed-target interval
  - honor stop requests while delayed/paused instead of continuing to the next target
  - pause before extraction when captcha/checkpoint or broken tab state is detected
  - preserve `resume_from_index` and checkpointed queue/results for manual operator resume
- Strengthened captcha/checkpoint normalization in [`normalizeCaptchaCheck()`](apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts:315) and pause handling in [`pauseHarvest()`](apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts:566).
- Added tab-health gating in [`checkHarvestTabHealth()`](apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts:334) so content-script loss, unsupported page context, or navigation away from the expected Douyin surface becomes an operator-visible pause boundary rather than a silent failure.
- Preserved the Phase 18I-D non-goals:
  - no capture-session creation
  - no backend flush
  - no Capture Inbox creation
  - no legacy runtime state
  - no V2 staged harvest path

### Popup / Progress / Operator Messaging
- Updated [`wholeProfileProgressSummary()`](apps/extension-douyin-capture/src/wholeProfileHarvest/progress.ts:3) to expose Phase 18I-E safety diagnostics including pause message, resume availability, last safety event, captcha evidence, scheduled pause state, delay state, tab health, and resume check status.
- Updated popup action result handling in [`runWholeProfileControllerAction()`](apps/extension-douyin-capture/src/popup.ts:356) so paused harvests show operator-facing safety instructions instead of a generic completion banner.
- Preserved extraction-only wording in popup state so the active queue is clearly not flushing backend records during this phase.

### Tests
- Expanded [`wholeProfileHarvest.test.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts) to cover:
  - progress-summary visibility for Phase 18I-E safety fields
  - stop-to-paused durability with resume still available
  - captcha/login-required pause before any modal opens
  - tab-health pause before target processing begins
  - no-backend guarantees on the active extraction path
- Kept the extension validation path aligned with workspace scripts in [`apps/extension-douyin-capture/package.json`](apps/extension-douyin-capture/package.json) and root workspace commands in [`package.json`](package.json).

## Validation Runs

### Extension
- `npm --workspace @reup-douyin/extension-douyin-capture run typecheck` ✅
- `npm --workspace @reup-douyin/extension-douyin-capture run test` ✅

## Notes
- The active Phase 18I-E path is still extraction-only and checkpoint-driven; safety pauses are explicit product states, not hidden retries.
- Captcha/checkpoint/login/traffic-block conditions are treated as manual-operator recovery boundaries.
- Resume continues from persisted local state and does not reconstruct work from legacy/V2 harvest state.
