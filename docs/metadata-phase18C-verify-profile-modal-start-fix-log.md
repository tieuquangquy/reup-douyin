# Phase 18C Verify Profile Modal-Start Fix Log

## Scope

Phase 18C only fixes canonical Whole Profile Harvest `Verify Profile` when launched from a Douyin profile modal URL. It is limited to `apps/extension-douyin-capture` and phase docs.

## Root Cause

The canonical verify controller resolved `/user/{sec_uid}?modal_id=...` to the profile URL, but then moved directly into `scanning_profile`. The modal-start path used navigation as an optional side effect and did not require a no-reload modal close, URL cleanup, or profile-grid readiness before invoking the same scanner that works on profile-start URLs. Scanner failure reasons were also collapsed into generic `profile_scan_failed`.

## Changes

- Added rich modal/profile URL resolution diagnostics with source modal aweme id.
- Added canonical modal preparation phases: `preparing_profile_page`, `closing_modal`, `waiting_profile_ready`, and `scanning_profile`.
- Added runtime hooks for no-reload modal close and profile readiness wait.
- Wired popup runtime to reuse the existing no-reload modal close helper and grid readiness probe without legacy runtime state.
- Ensured scanner is called only after modal URL no longer contains `modal_id` and profile grid readiness succeeds.
- Preserved profile-start behavior: profile URL verify proceeds directly to readiness/scanner and does not call modal close.
- Added precise error mapping for `modal_close_failed`, `profile_grid_not_ready`, `profile_scan_timeout`, and `profile_scroll_container_not_found`.
- Stored resolver and modal transition diagnostics in canonical state under `page_context.modal_transition`.

## Non-Goals Honored

- No backend files touched.
- No `/douyin-extension/full-modal-harvest` call added.
- No Capture Inbox writes added.
- No legacy Smart Capture, V2, CDP, or old runtime state restored.
- No fake targets added.

## Verification

- `npm --workspace @reup-douyin/extension-douyin-capture run typecheck` passed.
- `npm --workspace @reup-douyin/extension-douyin-capture run test` passed and included the extension build invoked by the test script.
