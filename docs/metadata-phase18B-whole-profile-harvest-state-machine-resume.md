# Metadata Phase 18B Extension Whole Profile Harvest State Machine Resume

## Current State

Phase 18B introduces a canonical local-first Whole Profile Harvest state machine for the extension. The state machine verifies a Douyin profile grid, persists verified targets, supports deterministic sample dry-runs, and reports progress from canonical state.

## Key Files

- `apps/extension-douyin-capture/src/wholeProfileHarvest/state.ts`
- `apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts`
- `apps/extension-douyin-capture/src/wholeProfileHarvest/profileResolver.ts`
- `apps/extension-douyin-capture/src/wholeProfileHarvest/profileScanner.ts`
- `apps/extension-douyin-capture/src/wholeProfileHarvest/targetValidation.ts`
- `apps/extension-douyin-capture/src/wholeProfileHarvest/dryRun.ts`
- `apps/extension-douyin-capture/src/wholeProfileHarvest/progress.ts`
- `apps/extension-douyin-capture/src/wholeProfileHarvest/errors.ts`
- `apps/extension-douyin-capture/src/popup.ts`
- `apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts`

## Operator Flow

1. Open a Douyin profile or modal on a supported Douyin tab.
2. Click Verify Profile.
3. Confirm verified target count and rejected candidate summary in popup progress.
4. Calibrate if required.
5. Run Dry-run First 3, Last 3, or Random 3.
6. Inspect pass/fail counts and Copy Debug JSON when troubleshooting.

## Phase Boundary

Run Harvest is intentionally disabled in Phase 18B and records `run_harvest_not_enabled_phase18b`. Production update/flush behavior belongs to Phase 18C.

## Verification Commands

Run from `apps/extension-douyin-capture` on Windows:

```powershell
npm run typecheck
npm run build
npm test
```
