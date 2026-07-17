# Phase 21D-18C — Profile DOM probe force-scan resume

## What changed
- [`probeDouyinProfileVideoEvidence()`](apps/extension-douyin-capture/src/contentScript.ts:387) now provides broader clean-profile DOM evidence and is reachable through [`"REUP_DOUYIN_PROBE_PROFILE_VIDEO_EVIDENCE"`](apps/extension-douyin-capture/src/contentScript.ts:278).
- [`getActualProfileReadiness()`](apps/extension-douyin-capture/src/popup.ts:2102) now combines warmup data with the direct profile DOM probe before deciding whether profile scanning can continue.
- [`isDouyinProfileReadyForScan()`](apps/extension-douyin-capture/src/popup.ts:2035) and [`coerceCleanProfileReadiness()`](apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts:1157) now treat clean profile DOM evidence as sufficient to continue when the page URL is already the expected profile and no modal is present.
- [`navigateToProfileForScan()`](apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts:854) now allows scan continuation on a clean profile page even after strict readiness timeout, instead of failing immediately.
- [`completeProfileVerify()`](apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts:1022) now emits `profile_scan_runner_not_started` when the canonical profile scanner ends with zero rounds.
- [`wholeProfileHarvest.test.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts:1101) covers the forced-scan path, the still-modal hard failure path, and the zero-round runner failure path.

## Validation completed
- `npx tsx apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts`
- `npm --workspace @reup-douyin/extension-douyin-capture run typecheck`

## Files touched
- [`apps/extension-douyin-capture/src/contentScript.ts`](apps/extension-douyin-capture/src/contentScript.ts)
- [`apps/extension-douyin-capture/src/types.ts`](apps/extension-douyin-capture/src/types.ts)
- [`apps/extension-douyin-capture/src/popup.ts`](apps/extension-douyin-capture/src/popup.ts)
- [`apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts)
- [`apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts)
- [`docs/metadata-phase21D-18C-profile-dom-probe-force-scan-log.md`](docs/metadata-phase21D-18C-profile-dom-probe-force-scan-log.md)
- [`docs/metadata-phase21D-18C-profile-dom-probe-force-scan-resume.md`](docs/metadata-phase21D-18C-profile-dom-probe-force-scan-resume.md)

## Non-goals preserved
- No crawler implementation.
- No backend API contract changes.
- No queue, worker, or database changes.
- No unrelated UI workflow changes.
