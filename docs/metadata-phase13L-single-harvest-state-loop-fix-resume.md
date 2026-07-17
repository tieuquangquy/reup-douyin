# Phase 13L single harvest state and loop-owner fix resume

## What was completed

- Canonical storage migration finalized for smart harvest state to `douyinSmartHarvestState`.
- Popup runtime/state rendering aligned to a single derivation path using normalized harvest progress + `smartStateFromHarvestProgress()`.
- Legacy dual-write removed from popup smart-state persistence.
- Regression assertions added for canonical key usage and runtime smart-state derivation in popup smart workflow tests.
- Extension test suite run passed.

## Current state

Phase 13L implementation is functionally complete for storage canonicalization and UI derivation consistency.

## Remaining follow-up

1. Keep monitoring for any remaining legacy-key reads once migration grace period ends.
2. If desired later, remove legacy fallback read path from popup once all operators are migrated.

## Re-run commands

```bash
npm run -w apps/extension-douyin-capture test
```

## Notes for next phase

- Preserve separation: popup = orchestrator/render surface, content script/controller = harvest loop owner.
- Any future state fields should be introduced through canonical key only and reflected via the same runtime-derived render path.
