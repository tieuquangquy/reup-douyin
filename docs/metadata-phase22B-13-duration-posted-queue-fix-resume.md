# Phase 22B-13 Duration/Posted Queue Fix Resume

## Completed
- Enforced aweme-scoped duration selection and diagnostics in [`apps/extension-douyin-capture/src/modalHarvest.ts`](apps/extension-douyin-capture/src/modalHarvest.ts:1694) and [`apps/extension-douyin-capture/src/cdpAweme.ts`](apps/extension-douyin-capture/src/cdpAweme.ts:77).
- Removed caption/desc misuse as posted text and preserved aweme `create_time` as [`posted_at`](apps/extension-douyin-capture/src/modalHarvest.ts:2572).
- Propagated duration diagnostics and posted provenance through [`apps/extension-douyin-capture/src/wholeProfileHarvest/state.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest/state.ts:206) and [`apps/extension-douyin-capture/src/wholeProfileHarvest/canonicalHarvest.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest/canonicalHarvest.ts:401).
- Fixed one-item queue continuation in [`apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts:2884) and [`apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts:3890).
- Updated focused regression coverage in [`apps/extension-douyin-capture/src/cdpAweme.test.ts`](apps/extension-douyin-capture/src/cdpAweme.test.ts) and [`apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts).

## Key Findings
- Exact aweme objects already contained the most reliable duration and posted metadata; the bug came from fallback precedence and payload propagation rather than missing source data.
- Generic video element and timeline duration should remain visible only as diagnostics when exact aweme duration is absent.
- [`posted_at`](apps/extension-douyin-capture/src/wholeProfileHarvest/canonicalHarvest.ts:418) is sufficient to satisfy posted metadata readiness for Capture Inbox without requiring a raw posted text string.
- Queue exhaustion in one-item mode depended on which selector counted pending work; using [`getFirstPendingTargetForOneItemCollect()`](apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts:370) and consistent pending accounting fixed the false no-pending state.

## Validation Status
- Passed: [`npx tsx apps/extension-douyin-capture/src/cdpAweme.test.ts`](apps/extension-douyin-capture/src/cdpAweme.test.ts)
- Passed: [`npx tsx apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts)
- Passed: [`npm --workspace @reup-douyin/extension-douyin-capture run typecheck`](apps/extension-douyin-capture/package.json:7)
- Not yet run: [`npm --workspace @reup-douyin/extension-douyin-capture run build`](apps/extension-douyin-capture/package.json:6)
- Blocked unrelated at workspace scope: [`npm test`](package.json:20) due to existing failures in [`apps/api/tests/test_douyin_profile_video_classification.py`](apps/api/tests/test_douyin_profile_video_classification.py)

## Files Touched In This Phase
- [`apps/extension-douyin-capture/src/modalHarvest.ts`](apps/extension-douyin-capture/src/modalHarvest.ts)
- [`apps/extension-douyin-capture/src/cdpAweme.ts`](apps/extension-douyin-capture/src/cdpAweme.ts)
- [`apps/extension-douyin-capture/src/wholeProfileHarvest/state.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest/state.ts)
- [`apps/extension-douyin-capture/src/wholeProfileHarvest/canonicalHarvest.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest/canonicalHarvest.ts)
- [`apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts)
- [`apps/extension-douyin-capture/src/cdpAweme.test.ts`](apps/extension-douyin-capture/src/cdpAweme.test.ts)
- [`apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts)
- [`docs/metadata-phase22B-13-duration-posted-queue-fix-log.md`](docs/metadata-phase22B-13-duration-posted-queue-fix-log.md)
- [`docs/metadata-phase22B-13-duration-posted-queue-fix-resume.md`](docs/metadata-phase22B-13-duration-posted-queue-fix-resume.md)
