# Phase 21D-18A — Modal Scan Profile Resolver Fix Resume

## Status

Implemented.

Phase 21D-18A updates the extension Scan Profile flow so a valid Douyin profile modal URL is no longer rejected with `Open a Douyin profile page first.`.

## Files Changed

- `apps/extension-douyin-capture/src/wholeProfileHarvest/profileResolver.ts`
- `apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts`
- `apps/extension-douyin-capture/src/wholeProfileHarvest/errors.ts`
- `apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts`
- `docs/metadata-phase21D-18A-modal-scan-profile-resolver-fix-log.md`
- `docs/metadata-phase21D-18A-modal-scan-profile-resolver-fix-resume.md`

## Implemented Behavior

A URL like `https://www.douyin.com/user/MS4w...?modal_id=7637147110034394414` is now treated as a valid profile modal scan start URL.

The resolver returns:

- `source = modal_parent_profile`
- `needsNavigation = true`
- `targetProfileUrl = https://www.douyin.com/user/MS4w...`

The controller then navigates the current tab to the clean profile URL and waits for profile/grid readiness before scanning.

## Error Behavior

- True non-profile/non-Douyin failures still use `Open a Douyin profile page first.`.
- Modal navigation failures use `Could not navigate from modal to profile page.`.
- Grid/card readiness failures after successful navigation use `profile_grid_not_ready_timeout`.

## Diagnostics

The Scan Profile debug summary includes modal URL, resolver, and navigation fields so manual retests can verify the modal path without requiring browser devtools.

## Manual Retest

1. Open a Douyin profile.
2. Open any video modal from that profile so the tab URL becomes `/user/<secUid>?modal_id=<awemeId>`.
3. Click Scan Profile in the extension popup.
4. Confirm the tab navigates to `/user/<secUid>` without `modal_id`.
5. Confirm the scanner reaches profile grid readiness and scan rounds increase above `0`.
6. Confirm the popup does not show `Open a Douyin profile page first.` for the valid profile modal URL.

## Validation Commands

Run from the repository root:

```bash
npm --workspace @reup-douyin/extension-douyin-capture run test
npm --workspace @reup-douyin/extension-douyin-capture run typecheck
npm --workspace @reup-douyin/extension-douyin-capture run build
```
