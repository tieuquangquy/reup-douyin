# Phase 21D-18 Scan Profile Navigation Resolver Resume

## Task

Implement Phase 21D-18 only: Scan Profile navigation resolver for modal, video, and any Douyin URL where a target profile URL can be resolved.

## Scope Lock

- Extension Scan Profile workflow only.
- No crawler implementation.
- No video processing implementation.
- No scoring or filtering implementation.
- No database schema.
- No queue implementation beyond existing harvest queue state preparation.
- No auto-publish integration.

## Current Status

Completed and validated.

## Implementation Outcome

1. Added profile URL normalization in `apps/extension-douyin-capture/src/wholeProfileHarvest/profileResolver.ts`.
2. Added scan target resolver in `apps/extension-douyin-capture/src/wholeProfileHarvest/profileResolver.ts`.
3. Integrated resolver into `verifyProfile()` in `apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts`.
4. Added Scan Profile navigation helper behavior in `apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts`.
5. Changed readiness waiting to 20 seconds maximum with 500ms polling.
6. Added `profile_navigation_or_grid_ready_timeout` error code/message in `apps/extension-douyin-capture/src/wholeProfileHarvest/errors.ts`.
7. Updated pending-navigation resume failure mapping to use `profile_navigation_or_grid_ready_timeout`.
8. Added/updated tests in `apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts`.
9. Added this resume artifact and the implementation log.

## URL Cases Covered

- `https://www.douyin.com/user/<secUid>` resolves as the current profile.
- `https://www.douyin.com/user/<secUid>?modal_id=<awemeId>` resolves to `https://www.douyin.com/user/<secUid>` and requires navigation.
- `https://www.douyin.com/video/<awemeId>` resolves from discovered author profile links when available.
- Other Douyin URL contexts can use stored, queue, or last successful profile URLs as fallback.
- Unresolvable contexts fail before scanning.

## Runtime Behavior

- Scan Profile writes `navigating_to_profile` only while navigation/readiness is actually active.
- Scan Profile starts the scanner only after the resolved profile page is ready.
- If readiness times out, the workflow fails and releases the action lock.
- Scanner success is never recorded during navigation or before scan rounds run.

## Validation Completed

Commands completed successfully:

```bash
npm --workspace @reup-douyin/extension-douyin-capture run test
npm --workspace @reup-douyin/extension-douyin-capture run typecheck
npm --workspace @reup-douyin/extension-douyin-capture run build
```

## Manual Retest Steps

1. Open a clean Douyin profile URL and click Scan Profile.
2. Confirm status reaches scan/classification results instead of staying at navigation.
3. Open a Douyin profile modal URL with `modal_id` and click Scan Profile.
4. Confirm the tab navigates to the clean `/user/<secUid>` URL and scan starts after grid readiness.
5. Open a direct Douyin video URL and click Scan Profile when an author profile URL can be resolved.
6. Confirm Scan Profile navigates to the resolved author profile before scanning.
7. Simulate a stuck modal/profile readiness failure.
8. Confirm final state is `failed`, phase is `failed`, and the error code is `profile_navigation_or_grid_ready_timeout`.
