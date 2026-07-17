# Phase 18E Force Profile Navigation Before Verify Resume

## Scope

Phase 18E only: force canonical Verify Profile to hard-navigate from modal URL to the resolved profile URL before profile readiness or scanning.

## Files Changed

- `apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts`
- `apps/extension-douyin-capture/src/wholeProfileHarvest/state.ts`
- `apps/extension-douyin-capture/src/wholeProfileHarvest/errors.ts`
- `apps/extension-douyin-capture/src/popup.ts`
- `apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts`
- `docs/metadata-phase18E-force-profile-navigation-before-verify-log.md`
- `docs/metadata-phase18E-force-profile-navigation-before-verify-resume.md`

## Behavior Summary

- Modal-start Verify detects `page_type = modal` or URL `modal_id`.
- It writes pending verify state with `phase = navigating_to_profile`.
- It calls hard navigation to the resolved profile URL.
- It returns immediately and does not call profile grid wait or scanner in the same call stack.
- Resume reads the pending state, confirms active URL is profile/no modal, reconnects content script, reruns detector, then runs existing profile readiness and scanner path.

## Error Summary

- `profile_navigation_required`: scanning was requested before leaving modal context.
- `profile_navigation_failed_still_modal`: navigation retry still leaves modal URL or modal detector state.
- `profile_navigation_timeout`: pending navigation is older than 30 seconds.
- `profile_grid_not_ready`: now reserved for confirmed profile context only.

## Validation

Passed:

- `npm --workspace @reup-douyin/extension-douyin-capture run typecheck`
- `npm --workspace @reup-douyin/extension-douyin-capture run test`

Still to run before final delivery if not already done in the active session:

- `npm --workspace @reup-douyin/extension-douyin-capture run build`

## Live Retest

1. Open a Douyin profile.
2. Open a video modal so the active URL includes `modal_id`.
3. Click Verify Profile in the popup.
4. Expected first result: `phase = navigating_to_profile`, tab URL changes to profile URL without `modal_id`, no scan happens in that same call.
5. After profile load, reopen/click Verify Profile to resume if needed.
6. Expected resume result: detector reconnects fresh, phase proceeds to `waiting_profile_ready`, `scanning_profile`, `validating_targets`, then `verified`.
7. Confirm `profile_grid_not_ready` is not shown while popup Connection still says `Page: modal`.
8. Start from direct profile URL and confirm Verify Profile still scans directly and succeeds.
