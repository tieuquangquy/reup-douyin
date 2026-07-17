# Phase 17H Modal Whole Profile Test zero-target scanner fix log

## Scope

Phase 17H fixes the isolated extension beta flow for Advanced/Beta → Test Modal → Whole Profile Harvest when a modal URL resolves to a profile URL but the profile scanner returns zero targets.

## Changes

- The beta test now navigates the active Douyin tab to the resolved profile URL before scanning.
- The beta test waits for the active tab URL to match the profile path without a `modal_id` query parameter before scanning.
- A diagnostic profile-card scanner runs in the page before any harvest-plan request.
- The scanner records selector attempts, current URL, page type, modal presence, readiness, body sample, scroll/viewport details, grid/card/link counts, empty-state detection, login/captcha detection, and scan rounds.
- The scanner extracts aweme IDs from `/video/{id}` links, `modal_id` query links, data attributes, and bounded local card/context regex fallbacks.
- Zero-card scans fail before calling `/douyin-extension/harvest-plan`.
- Harvest-plan coverage for this beta test defaults to `refresh_all` and is reported separately from raw card count.
- Runtime state now separates profile navigation, grid readiness, card scanning, harvest-plan status, total cards found, returned target count, and refresh-all target count.

## Isolation

The flow continues to write only the isolated `douyinModalWholeProfileTestRun` state key. It does not start production Safe Harvest, does not call full-modal-harvest start/flush in verify-only mode, and does not persist Smart Capture state from the beta path.

## Failure reasons

The beta flow now reports precise scanner/navigation blockers instead of treating a zero-card profile scan as success:

- `profile_navigation_failed`
- `profile_grid_not_ready`
- `profile_card_selector_failed`
- `profile_empty_detected`
- `login_or_captcha_blocked`
- `scan_timeout`
- `profile_scan_returned_no_cards`
