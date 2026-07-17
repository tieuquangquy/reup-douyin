# Metadata Phase 16A — Safe Harvest Runner Log

## Scope
- Introduce canonical Safe Runner storage state under `douyinSafeHarvestRun`.
- Route SAFE commands to SAFE-named execution functions.
- Preserve V2 commands as compatibility aliases.
- Keep current harvest execution behavior stable while migrating command/runtime surface.

## Changes Implemented
1. Added safe-runner key constant and persistence syncing in [`contentScript.ts`](../apps/extension-douyin-capture/src/contentScript.ts).
2. Added safe state projection helper:
   - `mapRuntimePhaseToSafePhase(...)`
   - `saveSafeHarvestRunStateFromProgress(...)`
3. Added SAFE operation entrypoints:
   - `startSafeHarvestRun(...)`
   - `resumeSafeHarvestRun(...)`
   - `stopSafeHarvestRun(...)`
   - `resetSafeHarvestRun()`
   - `getSafeHarvestRunProgress()`
   - `flushSafeHarvestRun()`
4. Kept V2 compatibility by delegating:
   - `startHarvestV2(...)` -> SAFE start
   - `resumeHarvestV2(...)` -> SAFE resume
   - `stopHarvestV2()` -> SAFE stop
   - `resetHarvestStateV2()` -> SAFE reset
   - `getHarvestProgressV2()` -> SAFE progress
   - `flushHarvestV2()` -> SAFE flush
5. Updated SAFE message handlers to call SAFE functions directly.

## Verification
- Ran extension validation via `npm run extension:test`.
- Result: passing test chain, TypeScript build, and dist resolution.

## Notes
- Core execution loop is still powered by existing V2 runtime internals in this phase step; SAFE façade and persisted SAFE state are now canonicalized and backward-compatible.
