# Phase 22B-12 Reuse Active Capture Session Per Profile Log

## Scope
- Implement Phase 22B-12 only across the existing extension, API, and Capture Inbox boundaries.
- Reuse an active backend Capture Session for the same profile instead of creating a duplicate session on every Start Collecting click.
- Improve the Session Ribbon label so it prefers human-readable session metadata over truncated technical identifiers.
- Strengthen posted extraction persistence only within the existing one-item-per-click and current Capture Inbox flow.
- Do not redesign the Capture Inbox layout, queue model, or batch collection workflow.

## Changes Applied
- [`ensureBackendCaptureSession()`](apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts:1886) now verifies the current stored session first, then falls back to [`listCaptureSessions()`](apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts:188) and reuses a profile-matched active session before creating a new one.
- [`captureSessionMatchesProfile()`](apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts:1913) compares both normalized profile URL and normalized profile identifier so same-profile clicks can safely reuse an active session.
- [`DouyinExtensionCaptureSessionRequest`](apps/extension-douyin-capture/src/types.ts:1275) and [`DouyinExtensionCaptureSessionRequest`](apps/api/src/schemas/douyin_extension.py:575) now carry normalized profile URL, display metadata, and queued count.
- [`create_capture_session()`](apps/api/src/services/douyin_extension_capture_service.py:228) now persists a human-readable [`capture_id`](apps/api/src/services/douyin_extension_capture_service.py:266), stores normalized profile metadata, and records display-title/session-label fields used by the UI.
- [`shortSessionLabel()`](apps/web/src/components/capture-inbox/CaptureInboxPage.tsx:1408) now prefers metadata fields such as `display_title`, `profile_display_name`, and `normalized_profile_identifier` before falling back to technical IDs.

## Regression Coverage Added
- [`test_v2_capture_session_preflight_creates_zero_visible_items_and_is_idempotent()`](apps/api/tests/test_douyin_extension_capture_service.py:1137) now asserts human-readable session labels and enriched metadata persistence.
- [`test_canonical_capture_session_preflight_accepts_whole_profile_harvest_and_is_idempotent()`](apps/api/tests/test_douyin_extension_capture_service.py:1179) now covers normalized profile metadata and queued-count persistence.
- [`apps/web/src/test/capture-inbox.test.ts`](apps/web/src/test/capture-inbox.test.ts) now asserts Session Ribbon metadata-first label fallback and friendly truncation behavior.
- [`apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts) now includes profile-matched session reuse coverage in addition to stored-session reuse.

## Validation Pending
- Run [`npm --workspace @reup-douyin/extension-douyin-capture run test`](apps/extension-douyin-capture/package.json).
- Run [`npm --workspace @reup-douyin/extension-douyin-capture run typecheck`](apps/extension-douyin-capture/package.json).
- Run [`npm --workspace @reup-douyin/extension-douyin-capture run build`](apps/extension-douyin-capture/package.json).
- Run backend tests covering [`apps/api/tests/test_douyin_extension_capture_service.py`](apps/api/tests/test_douyin_extension_capture_service.py).
