# Phase 21D-18B — Modal-to-profile scan continuation resume

## What changed
- [`navigateToProfileForScan()`](apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts:853) now refreshes page context after modal-to-profile navigation before starting the scanner.
- [`refreshDouyinTabContextAfterNavigation()`](apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts:1097) records refresh diagnostics, attempts stale modal cleanup, and reacquires readiness.
- [`waitForCleanProfilePageReady()`](apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts:1128) and [`coerceCleanProfileReadiness()`](apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts:1145) allow scan continuation when the clean profile URL is active and profile-card evidence is present.
- [`closeDouyinModalIfPresent()`](apps/extension-douyin-capture/src/contentScript.ts:377) provides content-script modal cleanup support through the new message contract in [`ExtensionMessage`](apps/extension-douyin-capture/src/types.ts:1420).
- [`createWholeProfilePopupRuntime()`](apps/extension-douyin-capture/src/popup.ts:1813) now exposes runtime hooks for modal cleanup and post-navigation refresh.
- [`wholeProfileHarvest.test.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts:987) covers the modal navigation continuation path and asserts that scanning proceeds with rounds greater than zero.

## Validation completed
- `npm --workspace @reup-douyin/extension-douyin-capture run typecheck`
- `npm --workspace @reup-douyin/extension-douyin-capture run build`
- `npx tsx apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts && node apps/extension-douyin-capture/dist/distModuleResolution.test.js wholeProfileHarvest.test.ts`

## Files touched
- [`apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts)
- [`apps/extension-douyin-capture/src/types.ts`](apps/extension-douyin-capture/src/types.ts)
- [`apps/extension-douyin-capture/src/contentScript.ts`](apps/extension-douyin-capture/src/contentScript.ts)
- [`apps/extension-douyin-capture/src/popup.ts`](apps/extension-douyin-capture/src/popup.ts)
- [`apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts)
- [`docs/metadata-phase21D-18B-modal-navigation-continue-scan-log.md`](docs/metadata-phase21D-18B-modal-navigation-continue-scan-log.md)

## Non-goals preserved
- No crawler implementation.
- No backend API contract changes.
- No queue, worker, or database changes.
- No unrelated UI workflow changes.
