# Phase 21D-14 Scan/Collect Status Separation Resume

## Status

Phase 21D-14 test alignment for scan/classification/collection workflow separation has been implemented and validated.

## Completed

- Repaired the syntax break in `apps/extension-douyin-capture/src/wholeProfileHarvest.viewModel.test.ts`.
- Updated `apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts` to assert canonical workflow fields for:
  - successful Scan Profile
  - failed Scan Profile
  - paused collection
  - resumed collection
  - reset clearing
  - classification failure
- Updated `apps/extension-douyin-capture/src/wholeProfileHarvest.readiness.test.ts` so resume and stop controls follow canonical collection workflow status instead of only legacy paused/running fields.
- Confirmed successful Scan Profile diagnostics now persist the completed action code:

```text
scan_profile.success
```

- Confirmed failed Scan Profile canonical scan workflow state is `failed`, matching runtime behavior.
- Re-ran the extension workspace validation successfully.

## Validation Already Run

From the repository root:

```text
npm --workspace @reup-douyin/extension-douyin-capture run test
```

Result: passed.

That script also completed:

```text
npm run build
node dist/distModuleResolution.test.js
```

Result: passed.

## Important Files

- `apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts`
- `apps/extension-douyin-capture/src/wholeProfileHarvest.readiness.test.ts`
- `apps/extension-douyin-capture/src/wholeProfileHarvest.viewModel.test.ts`
- `apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts`
- `apps/extension-douyin-capture/src/wholeProfileHarvest/readiness.ts`
- `docs/metadata-phase21D-14-scan-collect-status-separation-log.md`

## Remaining Work

Recommended next Phase 21D-14 follow-up items still pending in the broader task:

- review whether `Start Collecting` preflight/no-op behavior needs further code tightening beyond current passing assertions
- finish any remaining implementation cleanup in scanner workflow separation if new product requirements appear
- prepare final handoff summary for the full Phase 21D-14 task

## Notes

This phase kept existing extension boundaries intact. No backend APIs, queue implementations, crawler logic, or popup redesign work were introduced.
