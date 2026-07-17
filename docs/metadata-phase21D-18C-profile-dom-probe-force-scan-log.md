# Phase 21D-18C — Profile DOM probe force-scan log

## Scope
- Force a broader profile DOM evidence probe before failing `Scan Profile` on a clean Douyin profile page.
- Keep the change limited to the extension flow in [`apps/extension-douyin-capture/src/contentScript.ts`](apps/extension-douyin-capture/src/contentScript.ts), [`apps/extension-douyin-capture/src/types.ts`](apps/extension-douyin-capture/src/types.ts), [`apps/extension-douyin-capture/src/popup.ts`](apps/extension-douyin-capture/src/popup.ts), [`apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts), and [`apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts).

## Implemented
- Added a broader profile-page evidence probe in [`probeDouyinProfileVideoEvidence()`](apps/extension-douyin-capture/src/contentScript.ts:387) and exposed it through the new message handler branch for [`"REUP_DOUYIN_PROBE_PROFILE_VIDEO_EVIDENCE"`](apps/extension-douyin-capture/src/contentScript.ts:278).
- Extended the shared message contract in [`ExtensionMessage`](apps/extension-douyin-capture/src/types.ts:1420) and [`ExtensionMessageResponse`](apps/extension-douyin-capture/src/types.ts:1472) to carry profile DOM evidence.
- Expanded popup readiness heuristics in [`isDouyinProfileReadyForScan()`](apps/extension-douyin-capture/src/popup.ts:2035) so a clean `/user/` page can be considered ready from profile DOM evidence even when grid/video candidates are still absent.
- Updated [`getActualProfileReadiness()`](apps/extension-douyin-capture/src/popup.ts:2102) to request the new content-script probe, merge its diagnostics with warmup evidence, and classify `profile_url_and_profile_dom_evidence` readiness.
- Updated [`WholeProfileActualProfileReadiness`](apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts:79) to include the new readiness reason and to preserve probe diagnostics across controller boundaries.
- Relaxed the failure path in [`navigateToProfileForScan()`](apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts:854) so the controller does not fail immediately when the tab is already on a clean profile page without `modal_id`, and records the forced-start diagnostics in the request summary.
- Updated [`coerceCleanProfileReadiness()`](apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts:1157) so tolerant readiness includes profile DOM evidence, not only card/link candidates.
- Updated [`completeProfileVerify()`](apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts:1022) to fail with `profile_scan_runner_not_started` when the canonical scanner completes with zero rounds, before applying the zero-card failure path.
- Added regression coverage in [`wholeProfileHarvest.test.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts:1101) for:
  - forced scan continuation after readiness timeout on a clean profile page with DOM evidence,
  - hard timeout failure when the page is still modal,
  - zero-round runner failure semantics.

## Validation
- `npx tsx apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts`
- `npm --workspace @reup-douyin/extension-douyin-capture run typecheck`
- Initial repo-level `npm test -- --runInBand apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts` was not used as the final signal because it routed through the workspace smoke-check script and failed in unrelated API tests.

## Notes
- This phase stays local to extension readiness and controller behavior; no backend, queue, worker, crawler, or database behavior changed.
- The new behavior intentionally distinguishes:
  - profile page ready enough to force scanner start,
  - scanner runner not started (`scan_rounds === 0`),
  - scanner started but returned no usable cards.
