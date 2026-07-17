# Phase 22C-9J Build Queue From DOM Probe Resume

## Status
Phase 22C-9J implementation is in progress. Core code, tests, and log doc have been added.

## Files Changed
- `apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts`
- `apps/extension-douyin-capture/src/wholeProfileHarvest/errors.ts`
- `apps/extension-douyin-capture/src/wholeProfileHarvest/profileScanner.ts`
- `apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts`
- `docs/metadata-phase22C-9J-build-queue-from-dom-probe-log.md`
- `docs/metadata-phase22C-9J-build-queue-from-dom-probe-resume.md`

## Key Behavior
- If DOM probe has candidates and the legacy scanner fails or returns zero rounds, Scan Profile now normalizes probe candidates and builds a pending queue.
- Successful fallback sets scan rounds to 1, `profile_scan_ready` to true, clears active task/action lock, clears visible scanner error, and persists the queue.
- Calibration remains outside Scan Profile success and is handled by existing next-action readiness logic.

## Validation So Far
- `npm --workspace @reup-douyin/extension-douyin-capture run typecheck` passed after implementation.

## Remaining
- Run full test/typecheck/build.
- Review any failures and update final report.
