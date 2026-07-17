# Phase 22E-3 Compact Reset Action Sheet Log

## Scope
Implemented Phase 22E-3 for the Douyin extension popup reset modal only. Crawler, extractor, backend save APIs, and backend data deletion paths were not changed.

## UX Issue Fixed
The Phase 22E-2 reset modal used tall explanatory cards with paragraph-style copy. In the popup, that made Reset feel like documentation and could force scrolling. Phase 22E-3 replaces that with a compact professional action sheet.

## Layout
- Title: `Reset scanner`
- Subtitle: `Backend Capture Inbox data stays safe.`
- Footer note: `No backend sessions or items will be deleted.`
- Three compact action rows with short label, subtitle, meta line, and status badge.

## Action Mapping
- `Fix stuck run` -> `current_run`
- `Refresh profile` -> `current_profile_rescan`
- `Switch profile` -> `new_profile`

## Switch Profile Confirmation
`Switch profile` no longer dispatches immediately. It opens an inline confirmation view in the same modal with:

- Title: `Switch profile?`
- Body: `Local queue/session for this profile will be cleared. Backend data will not be deleted.`
- Buttons: `Cancel` and `Switch profile`

Confirming dispatches `new_profile`. Cancel returns to the action sheet.

## Safety and Semantics
Reset semantics are unchanged. Backend Capture Inbox sessions/items are not deleted. Calibration/settings are preserved by the underlying reset workflow.

## Accessibility and Error Handling
Rows remain native buttons for Enter/Space support. Escape closes the modal when no reset is running. Running state disables rows and shows `Resetting...`. Failure keeps the modal open and shows `Reset failed. Check Advanced diagnostics.`

## Recommendation Logic
The popup applies lightweight recommendations from available local diagnostics:

- `profile_switch_detected` recommends Switch profile.
- Existing action lock, pausing status, or pause request recommends Fix stuck run.
- Completed local queue shows `To collect another user, use Switch profile.`
