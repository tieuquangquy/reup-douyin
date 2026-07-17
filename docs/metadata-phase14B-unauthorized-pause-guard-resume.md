# Phase 14B Unauthorized Pause Guard Resume

## Scope

- Extension only: runtime V2, popup progress normalization, transition diagnostics, counter repair

## Files touched

- `apps/extension-douyin-capture/src/harvestRuntimeV2.ts`
- `apps/extension-douyin-capture/src/contentScript.ts`
- `apps/extension-douyin-capture/src/popupProgress.ts`
- `apps/extension-douyin-capture/src/popup.ts`
- `apps/extension-douyin-capture/src/popupWorkflow.ts`
- `apps/extension-douyin-capture/src/types.ts`
- `apps/extension-douyin-capture/public/popup.html`
- tests:
  - `src/harvestRuntimeV2.test.ts`
  - `src/popupProgress.test.ts`
  - `src/popupWorkflow.test.ts`

## What changed

- Added canonical runtime transition gate `transitionHarvestRuntime(...)`
- Added runtime transition ring buffer
- Rebuilt progress normalization so popup no longer infers `paused` without allowed `pause_reason`
- Recomputed counts and target index from `target_status`
- Split `flush_attempt_count` from `flushed_count`
- Added `Show Runtime Transitions` maintenance button

## Verification

- Typecheck passed
- Extension test suite passed
- Build passed through the test command
