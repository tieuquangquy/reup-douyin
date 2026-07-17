# Phase 21D-15 Waiting Profile Ready Stall Fix Resume

## Status

Phase 21D-15 implementation has been completed and validated. The Scan Profile workflow now avoids the `waiting_profile_ready` stall, starts the canonical profile scanner explicitly, and preserves runner-start diagnostics.

## Completed

- Added tolerant profile-ready detection in `apps/extension-douyin-capture/src/popup.ts`.
- Updated profile warmup handling so loaded profile grids/links can proceed into scanning.
- Added persisted `waiting_profile_ready` diagnostics in `apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts`.
- Added warmup timeout handling that blocks scanner start only for explicit timeout signals.
- Added explicit scanner runner-start state and diagnostics before calling the canonical profile scanner.
- Preserved runner-start diagnostics into final verified scan diagnostics.
- Added friendly missing-grid wording in `apps/extension-douyin-capture/src/wholeProfileHarvest/errors.ts`.
- Added/updated focused workflow tests in `apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts`.
- Repaired accidental `scanRunning` replacement corruption in `apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts`.

## Validation Already Run

From `apps/extension-douyin-capture`:

```text
npx tsx src/wholeProfileHarvest.test.ts
npm test
npm run typecheck
npm run build
```

Result: passed.

## Important Files

- `apps/extension-douyin-capture/src/popup.ts`
- `apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts`
- `apps/extension-douyin-capture/src/wholeProfileHarvest/errors.ts`
- `apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts`
- `docs/metadata-phase21D-15-waiting-profile-ready-stall-fix-log.md`

## Remaining Work

- Prepare final handoff report.

## Notes

This phase remains scoped to the extension Scan Profile workflow. It does not introduce backend API changes, database or queue changes, crawler implementation, video processing implementation, or popup redesign work.
