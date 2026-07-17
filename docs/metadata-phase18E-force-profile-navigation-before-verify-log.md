# Phase 18E Force Profile Navigation Before Verify Log

## Root Cause

Verify Profile could resolve `profile_url` from a Douyin modal URL, but the canonical verify path still attempted profile readiness/scanning while the active page remained `page_type = modal` or still had `modal_id` in the URL. The profile scanner then reported `profile_grid_not_ready`, which was misleading because the scan was running against the modal page instead of the profile grid.

## Phase 18E Decision

Phase 18E makes modal-start Verify deterministic by hard-navigating to the resolved profile URL first. The verify action must not call profile grid wait or profile scanning in the same call stack after requesting navigation.

## Implemented Behavior

1. When the active URL is modal or contains `modal_id`, Verify Profile writes canonical `douyinWholeProfileHarvest` state with:
   - `status = verifying`
   - `phase = navigating_to_profile`
   - `profile_url = resolvedProfileUrl`
   - `source_modal_aweme_id = modalId`
   - `verify.status = running`
   - `debug.pending_verify_after_navigation = true`
   - `debug.navigation_method = hard_profile_navigation`
   - `debug.original_modal_url = currentUrl`
2. The runtime calls `chrome.tabs.update(tabId, { url: profileUrl })` through `navigateToProfile`.
3. The initial Verify Profile call returns immediately after navigation is requested.
4. Pending verify can resume when popup Verify is clicked again or when the popup reads a pending state and invokes resume behavior.
5. Resume reconnects content script and reruns detector after navigation instead of reusing modal detector state.
6. Resume requires active URL/profile detector state to be profile and no `modal_id` before profile grid wait/scanning.

## Error Behavior

- `profile_navigation_required` is used if code reaches a profile-grid boundary while still in modal context.
- `profile_navigation_failed_still_modal` is used when retrying hard navigation still leaves the active tab on a modal URL or detector still reports modal.
- `profile_navigation_timeout` is used when `navigating_to_profile` remains pending for more than 30 seconds.
- `profile_grid_not_ready` remains valid only after active context is confirmed as profile.

## Detector Reconnect

After hard navigation, resume calls `ensureContentScriptReady`, which performs reconnect/detector refresh and returns fresh page context data. This prevents stale modal page context from allowing profile scan.

## Tests Run

- `npm --workspace @reup-douyin/extension-douyin-capture run typecheck`
- `npm --workspace @reup-douyin/extension-douyin-capture run test`

Both commands passed during implementation.

## Live Retest Steps

1. Open a Douyin profile URL and click a video so the URL contains `modal_id`.
2. Open the extension popup.
3. Click Verify Profile.
4. Confirm progress shows `navigating_to_profile` and the tab hard-navigates to the same profile URL without `modal_id`.
5. After the tab loads, open/click Verify Profile again if it did not auto-resume.
6. Confirm phase advances through `waiting_profile_ready`, `scanning_profile`, `validating_targets`, and `verified`.
7. Confirm `Verified targets` is greater than 0 and `Last error` is not `profile_grid_not_ready`.
8. Repeat from a direct profile URL and confirm Verify Profile still succeeds without hard navigation.
