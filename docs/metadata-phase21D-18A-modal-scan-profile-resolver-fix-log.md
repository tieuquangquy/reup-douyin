# Phase 21D-18A — Modal Scan Profile Resolver Fix Log

## Summary

Phase 21D-18A fixes Scan Profile startup from Douyin profile modal URLs such as `https://www.douyin.com/user/MS4w...?modal_id=AWEME_ID`.

The extension now treats a profile modal URL as a valid scan start context, resolves it to the clean parent profile URL, navigates the current tab to that profile URL, waits for profile readiness/grid candidates, and only then starts the scan runner.

## Scope

Changed extension-only Scan Profile behavior:

- Modal profile URL detection.
- Scan Profile resolver priority.
- Modal-to-profile navigation diagnostics.
- Failure messages for modal navigation and post-navigation grid timeout.
- Focused controller and resolver tests.

Out of scope:

- Backend API changes.
- Capture Inbox UI changes.
- Collector/save logic changes.
- Fake scan results.
- Manual modal close requirement.

## Bad Failure Path Fixed

The bad failure path was the Scan Profile action wrapper mapping navigation/profile errors to the generic operator message `Open a Douyin profile page first.`.

That was wrong for valid profile modal URLs because a modal URL already contains the parent `/user/<secUid>` route and only needs clean-profile navigation before scanning.

The mapping now keeps the generic prompt for true non-Douyin/profile resolution failures, while preserving modal-specific failures such as `Could not navigate from modal to profile page.` and `profile_grid_not_ready_timeout`.

## Resolver Behavior

Added `isDouyinProfileModalUrl(url)`.

It returns true when:

- The URL host is Douyin.
- The path starts with `/user/`.
- The query string has `modal_id`.

`normalizeDouyinProfileUrl(url)` continues to strip all query/hash state and returns the clean profile URL.

Resolver priority now explicitly accepts:

1. Current clean profile URL.
2. Current profile modal URL.
3. `pageType === "modal"` with a `/user/` current URL.
4. Direct video author profile links.
5. Stored/previous profile URLs.
6. Otherwise unresolved.

## Navigation Behavior

When the resolver source is `modal_parent_profile`, Scan Profile now:

1. Sets phase to `navigating_to_profile`.
2. Stores `resolved_profile_url` in diagnostics.
3. Calls `navigateToProfile` with the clean profile URL.
4. Waits for actual profile readiness.
5. Waits for grid/card readiness.
6. Starts the scan runner only after readiness succeeds.

Navigation failure reports `Could not navigate from modal to profile page.`.

Navigation success followed by grid timeout reports `profile_grid_not_ready_timeout`.

## Diagnostics Added

Scan Profile diagnostics now include:

- `scan_start_url`
- `scan_start_page_type`
- `is_profile_modal_url`
- `modal_id_at_scan_start`
- `resolved_profile_url`
- `resolved_profile_source`
- `needs_profile_navigation`
- `profile_navigation_status`
- `profile_navigation_error`

## Validation

Ran:

- `npm --workspace @reup-douyin/extension-douyin-capture run test`
- `npm --workspace @reup-douyin/extension-douyin-capture run typecheck`
- `npm --workspace @reup-douyin/extension-douyin-capture run build`
