# Phase 18C Verify Profile Modal-Start Fix Resume

## Implemented State

Canonical Whole Profile Harvest `Verify Profile` now supports starting from a Douyin modal URL such as `/user/{sec_uid}?modal_id={aweme_id}`.

## Flow

1. Resolve current URL into profile URL and optional `source_modal_aweme_id`.
2. Persist resolver diagnostics into canonical state.
3. Ensure content script is ready.
4. If current page is modal, close modal to profile URL before scanning.
5. Wait for profile readiness and require non-modal profile diagnostics with visible profile-grid candidates.
6. Invoke the same canonical profile scanner used by profile-start verify.
7. Validate targets and persist verified state.

## Important Files

- `apps/extension-douyin-capture/src/wholeProfileHarvest/profileResolver.ts`
- `apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts`
- `apps/extension-douyin-capture/src/wholeProfileHarvest/profileScanner.ts`
- `apps/extension-douyin-capture/src/wholeProfileHarvest/errors.ts`
- `apps/extension-douyin-capture/src/wholeProfileHarvest/state.ts`
- `apps/extension-douyin-capture/src/popup.ts`
- `apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts`

## Retest Steps

1. Open a Douyin profile page and click one profile video so the URL becomes `/user/{sec_uid}?modal_id={aweme_id}`.
2. Open the extension popup.
3. Click `Verify Profile` in Whole Profile Harvest.
4. Confirm the modal closes or transitions back to the profile without a full reload when possible.
5. Confirm canonical state reaches `verified` with `source_modal_aweme_id` set to the modal aweme id.
6. Confirm verified targets are populated.
7. Repeat from the plain `/user/{sec_uid}` profile URL and confirm profile-start still verifies successfully.

## Verification Commands

- `npm --workspace @reup-douyin/extension-douyin-capture run test`
- `npm --workspace @reup-douyin/extension-douyin-capture run typecheck`
- `npm --workspace @reup-douyin/extension-douyin-capture run build`
