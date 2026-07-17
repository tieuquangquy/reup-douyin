# Phase 21D-18B — Modal-to-profile scan continuation log

## Scope
- Continue `Scan Profile` after modal-to-profile navigation.
- Keep the change limited to the extension flow in [`apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts), [`apps/extension-douyin-capture/src/popup.ts`](apps/extension-douyin-capture/src/popup.ts), [`apps/extension-douyin-capture/src/contentScript.ts`](apps/extension-douyin-capture/src/contentScript.ts), [`apps/extension-douyin-capture/src/types.ts`](apps/extension-douyin-capture/src/types.ts), and [`apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts).

## Implemented
- Added post-navigation tab-context refresh support in [`refreshDouyinTabContextAfterNavigation()`](apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts:1097).
- Added clean-profile readiness polling in [`waitForCleanProfilePageReady()`](apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts:1128).
- Added tolerant profile readiness coercion in [`coerceCleanProfileReadiness()`](apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts:1145) so a clean profile URL plus strong profile candidates can proceed even if stale detector state still reports modal.
- Updated modal navigation flow in [`navigateToProfileForScan()`](apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts:853) to:
  - navigate to the clean profile URL,
  - refresh context,
  - attempt stale modal cleanup,
  - wait for clean-profile readiness,
  - then continue into the scanner.
- Extended [`WholeProfileHarvestRuntime`](apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts:151) with:
  - `refreshDouyinTabContextAfterNavigation`
  - `closeDouyinModalIfPresent`
- Added extension message support in [`ExtensionMessage`](apps/extension-douyin-capture/src/types.ts:1420) and [`ExtensionMessageResponse`](apps/extension-douyin-capture/src/types.ts:1472) for modal cleanup messaging.
- Added content-script modal cleanup handling in [`chrome.runtime.onMessage.addListener()`](apps/extension-douyin-capture/src/contentScript.ts:92) and [`closeDouyinModalIfPresent()`](apps/extension-douyin-capture/src/contentScript.ts:377).
- Wired popup runtime methods in [`createWholeProfilePopupRuntime()`](apps/extension-douyin-capture/src/popup.ts:1813) to call the content script and refresh the tab context after hard navigation.
- Updated modal scan regression coverage in [`wholeProfileHarvest.test.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts:987) to assert the refresh/cleanup path and successful continuation into scanning with `scan_rounds > 0`.

## Validation
- `npm --workspace @reup-douyin/extension-douyin-capture run typecheck`
- `npm --workspace @reup-douyin/extension-douyin-capture run build`
- `npx tsx apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts && node apps/extension-douyin-capture/dist/distModuleResolution.test.js wholeProfileHarvest.test.ts`

## Notes
- The full workspace test script was also re-run during verification and advanced past [`wholeProfileHarvest.test.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts), but the direct targeted validation above is the explicit confirmed check captured for this phase.
- No backend, crawler, queue, or worker behavior was changed.
