# Phase 15C Item Data Integrity Fix Log

## Scope
Implemented Phase 15C integrity safeguards in the extension harvest runtime to prevent stale/misaligned modal metrics from being committed to the wrong target aweme.

## Files Changed
- `apps/extension-douyin-capture/src/modalHarvest.ts`
- `apps/extension-douyin-capture/src/types.ts`
- `apps/extension-douyin-capture/src/popupProgress.ts`
- `apps/extension-douyin-capture/src/popupProgress.test.ts`
- `apps/extension-douyin-capture/src/modalHarvest.test.ts`

## Implemented Changes

### 1) Runtime integrity tracking in harvest controller
In `FullModalHarvestController`:
- Added counters/diagnostics for integrity mismatch tracking.
- Persisted and restored integrity diagnostics in controller state/progress.
- Added stale extracted-metrics cleanup helper.

### 2) Commit-path integrity gates
Before committing extracted metrics:
- Verify current modal aweme matches expected target.
- Wait for metrics readiness tied to target aweme.
- Validate item payload/probe/target consistency.
- On mismatch, record diagnostics and avoid unsafe commit.

### 3) Bootstrap integrity gate
In bootstrap extraction flow:
- Validate bootstrap extracted item against current target before commit.
- On mismatch, track mismatch and avoid committing incorrect data.

### 4) Exported integrity audit helper
Added exported helper in `modalHarvest.ts`:
- `auditHarvestRecentItemsIntegrity(items, expectedAwemeId)`
- Validates latest `recent_items` aweme id against expected target.

### 5) Type contracts extended
Added integrity diagnostic fields to:
- `FullModalHarvestProgress`
- `StoredFullModalHarvestState`

### 6) Popup diagnostics updates
In paused-state error lines:
- Added mismatch count and last integrity details display.

### 7) Tests
- Added/updated tests for popup diagnostics integrity lines.
- Added tests for `auditHarvestRecentItemsIntegrity` pass/mismatch behavior.

## Verification
Executed in `apps/extension-douyin-capture`:
- `npm run typecheck` ✅ pass
- `npm run build` ✅ pass
- `npm run test` ❌ fails on pre-existing legacy expectation mismatch (`/Maintenance/`) unrelated to Phase 15C integrity changes.

## Notes
The test failure is consistent with previously known baseline behavior in popup markup/assertion compatibility and is not introduced by the new integrity helper or commit guards.
