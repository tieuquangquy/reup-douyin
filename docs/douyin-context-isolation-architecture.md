# Douyin Context Isolation Architecture

## Scope

This note covers only context isolation and capture-session scoping for the Douyin extension capture pipeline. It does not redesign thumbnail extraction, duration/stat parsing, UI layout, queueing, review, or publishing.

## Contamination points found during audit

1. Extension network cache records are context-free.
   - `apps/extension-douyin-capture/src/networkCache.ts` stores `NetworkVideoMetadata[]` on `window.__REUP_DOUYIN_NETWORK_CACHE__` and publishes the same records through the DOM bridge.
   - Records are merged only by `aweme_id`, with no page URL, profile identity, tab id, or capture window.

2. Content script hydration accepts all cached metadata for the current page.
   - `apps/extension-douyin-capture/src/contentScript.ts` merges bridged page-hook items and content-script cache items, then passes them to `buildCapturePayload()`.
   - The merge is keyed only by `aweme_id`, so stale metadata can hydrate a visible item if IDs collide or if stale records remain after navigation.

3. Extractor hydration is exact by `aweme_id`, but not by capture context.
   - `apps/extension-douyin-capture/src/extractor.ts` discovers visible DOM links from the current document, which is correct for discovery scope.
   - Hydration maps network/detail metadata by `aweme_id` only and does not reject page/profile/tab mismatches.

4. Popup direct fallback knows the active tab, but the payload currently does not carry tab context.
   - `apps/extension-douyin-capture/src/popupTransport.ts` obtains the active tab id before executing capture.
   - That tab id is not attached to `ExtensionCapturePayload`, so backend diagnostics cannot verify browser execution context.

5. Backend staging creates exactly one `capture_session_id` per extension capture, and `_build_item()` assigns every item to that session.
   - `apps/api/src/services/capture_inbox_service.py` creates a new `CaptureSession`, then persists each `CapturedItem` with `capture_session_id=session.id` and `workspace_id=session.workspace_id`.
   - This is structurally correct, but it currently does not validate each item’s embedded capture context against the session context.

6. Backend item listing can be unscoped by default.
   - `apps/api/src/api/routes/capture_inbox.py` exposes `GET /capture-inbox/items` where `capture_session_id` is optional.
   - If the UI or another caller uses this endpoint without a session id, previous-session items can be returned. The Capture Inbox page audited here uses session detail by default, but the API boundary is loose.

7. Frontend default Capture Inbox view loads one selected session detail.
   - `apps/web/src/components/capture-inbox/CaptureInboxPage.tsx` loads sessions and then fetches `/sessions/{id}` for the selected session.
   - Visible items are derived only from `selectedSession.items`, so the current default UI does not mix sessions unless the backend session detail response itself is polluted.

## Active capture context model

The active capture context is a typed object attached to the capture payload and propagated to staged items as safe metadata:

- `capture_id`: extension-created id for the capture action.
- `tab_id`: browser tab id when known from the popup transport.
- `page_url`: current browser URL at capture time.
- `page_url_normalized`: origin + pathname without hash/query-noise for matching.
- `profile_url`: current profile URL if derivable.
- `profile_external_id`: stable profile key if derivable (`sec_uid`, `author_id`, handle-derived id, or equivalent).
- `captured_at`: capture timestamp.
- `cache_scope_key`: deterministic local key derived from page/profile context for extension cache filtering.

Backend project/session ownership remains represented by:

- `workspace_id`: current local project/workspace identifier, defaulting to the default workspace when not supplied.
- `capture_session_id`: backend-created durable session id.

## Required isolation dimensions

1. Project/workspace: items from a different `workspace_id` must not be returned by default for current project views.
2. Capture session: every staged item belongs to exactly one `capture_session_id`; session detail returns only that session’s items.
3. Browser context: tab id is recorded when available and used for debug/mismatch diagnostics.
4. Page URL: network cache metadata can hydrate only when page context matches or when no safer profile/page context exists and the item was observed in the current page cache window.
5. Profile identity: profile URL/external id mismatch rejects hydration.
6. Capture window: stale cache entries outside a short same-page window are rejected from current hydration.

## Cache scoping rules

- Network cache entries must carry a safe context snapshot when observed/published.
- The content script must build a current capture context before reading cache entries.
- Cache lookups must return a scoped view, not the whole global cache.
- A metadata entry can hydrate a discovered item only when:
  - `aweme_id` matches the visible DOM discovery, and
  - page/profile context is compatible with the current capture context, and
  - the item is inside the active cache window.
- A metadata entry with mismatched profile/page/tab context is rejected and counted as a mismatch diagnostic; it is not merged into the current item.

## Session scoping rules

- Backend creates one `CaptureSession` per accepted extension capture.
- Every staged item must persist the session’s `capture_session_id` and `workspace_id`.
- Item-level context metadata, when supplied by the extension, must match the session context. Mismatched items are skipped/rejected rather than staged into the current session.
- Duplicate detection remains session-local via the existing session dedupe key.

## Query scoping rules

- Session detail queries must return only items owned by that `capture_session_id`.
- Current/default item queries must require a `capture_session_id`; unscoped item listing is not a safe default.
- Project/workspace filters must be available at service boundaries so future multi-project UI does not accidentally expose another project’s items.
- Older sessions remain accessible only through explicit session selection.

## Mismatch handling rules

Mismatch codes are safe diagnostics and must not expose secrets:

- `context_mismatch`
- `session_mismatch`
- `project_mismatch`
- `profile_mismatch`
- `tab_mismatch`
- `page_mismatch`

When mismatch is detected:

1. Reject the merge or staging operation for that item/context.
2. Record a safe count/reason in diagnostics or failure summaries.
3. Do not show the rejected item in the current Capture Inbox session.

## Non-goals

- No new crawler implementation.
- No video processing changes.
- No thumbnail-specific recovery changes.
- No UI redesign.
- No queue/review/publish changes.
