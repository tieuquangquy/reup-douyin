# Douyin Context Isolation Log

## Task

Fix only context isolation and capture-session scoping for the Douyin capture pipeline so items from other pages, tabs, profiles, sessions, or projects cannot enter the current Capture Inbox session.

## Guardrails

- Keep the change scoped to `apps/extension-douyin-capture`, `apps/api`, and frontend only if needed.
- Do not implement thumbnail extraction fixes, duration/stat fixes, UI redesign, queue/review/publish changes, or broad pipeline refactors.
- Preserve local-first behavior while keeping project/session boundaries SaaS-ready.

## Audit completed

### Extension

- `apps/extension-douyin-capture/src/contentScript.ts`
  - Previous capture merged `bridgedNetworkItems` and `readDouyinNetworkCache()` without context filtering.
  - `bridgedNetworkItems` is module-level mutable state and previously contained context-free `NetworkVideoMetadata` entries.
  - `mergeNetworkCacheItems()` deduped only by `aweme_id`.

- `apps/extension-douyin-capture/src/networkCache.ts`
  - Page hook cache is stored in `window.__REUP_DOUYIN_NETWORK_CACHE__` as a global array.
  - Previous cache entries included no page URL, profile URL, profile id, tab id, or observed timestamp.
  - `publishCache()` posted all safe items without scoped filtering.

- `apps/extension-douyin-capture/src/pageNetworkHook.ts`
  - Injected page hook also wrote context-free network cache entries before this task.

- `apps/extension-douyin-capture/src/extractor.ts`
  - Discovery uses current DOM video links and is correctly current-page visible-discovery scoped.
  - Hydration previously used `canonicalNetworkMap()` keyed by `aweme_id` only.
  - `buildCapturePayload()` previously created `capture_id` and page/profile snapshots but did not create or enforce a capture context.

- `apps/extension-douyin-capture/src/popupTransport.ts`
  - Active tab id is available in `executeCurrentTabAction()` before capture runs.
  - The tab id was not attached to the payload or content-script message.
  - Direct execute-script fallback is DOM-only and does not use network cache, so its primary risk was missing tab context rather than network-cache contamination.

- `apps/extension-douyin-capture/src/types.ts`
  - `NetworkVideoMetadata` and `ExtensionCapturePayload` had no context model.

### Backend

- `apps/api/src/services/capture_inbox_service.py`
  - `stage_extension_capture()` creates one session and `_build_item()` assigns each item to that session id and workspace id.
  - Dedupe is session-local via `UniqueConstraint("capture_session_id", "dedupe_key")`.
  - Item context was not validated against session context because the extension payload lacked item/capture context fields.

- `apps/api/src/api/routes/capture_inbox.py`
  - Session detail endpoint scopes by session id.
  - Item list endpoint accepted optional `capture_session_id`; unscoped default could return previous-session items.

- `apps/api/src/schemas/douyin_extension.py`
  - Capture request schema had `workspace_id`, `capture_id`, page/profile/videos, but no `capture_context` or item context fields.

### Frontend

- `apps/web/src/components/capture-inbox/CaptureInboxPage.tsx`
  - Default page loads a selected session detail and derives visible items from `selectedSession.items`.
  - No direct use of unscoped `/capture-inbox/items` was found in this component.
  - No frontend code change was needed for this task.

## Implementation completed

1. Added extension capture context and mismatch code types.
2. Attached page/profile context to content-script and injected page-hook network cache entries.
3. Scoped content-script cache reads to the active page/profile/tab context before hydration.
4. Passed capture context into extraction and per-item payload diagnostics.
5. Attached tab id from popup transport to content-script messages and returned payloads.
6. Added backend schema fields for capture context and item context mismatch codes.
7. Validated/staged only items matching the session context; mismatched items are rejected with safe failure summaries.
8. Tightened backend item-list default to require an explicit `capture_session_id`.
9. Added focused tests for extension cache mismatch rejection and backend mismatch/query rejection.

## Rules now enforced

- Network cache metadata hydrates visible DOM discoveries only after context filtering and `aweme_id` canonicalization.
- Metadata from another page, profile, or tab is rejected before merge/hydration.
- Context-marked mismatch entries are not allowed to hydrate current-session items.
- Every accepted backend item is tied to one `capture_session_id` and `workspace_id`.
- Backend item contexts are checked against session context for project, session, tab, profile, and page mismatches.
- `GET /capture-inbox/items` requires a session id by default.

## Verification

- `npm run test --workspace apps/extension-douyin-capture` passed.
- `python -m unittest tests.test_douyin_extension_capture_service` passed from `apps/api`.
- `python -m py_compile src/schemas/douyin_extension.py src/services/capture_inbox_service.py src/api/routes/capture_inbox.py` passed from `apps/api`.
- `python -m pytest apps/api/tests/test_douyin_extension_capture_service.py` could not run earlier because `pytest` is not installed in the environment; unittest coverage was used for the available backend verification.
