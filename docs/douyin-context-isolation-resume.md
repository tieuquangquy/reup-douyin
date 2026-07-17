# Douyin Context Isolation Resume

## Current task

Fix only context isolation and capture-session scoping for the Douyin capture pipeline. Prevent items or metadata from other pages, tabs, profiles, sessions, or projects from entering the current Capture Inbox session.

## Completed before implementation

- Read `AGENTS.md`.
- Audited relevant extension, backend, and frontend boundaries.
- Wrote docs first:
  - `docs/douyin-context-isolation-architecture.md`
  - `docs/douyin-context-isolation-log.md`
  - `docs/douyin-context-isolation-resume.md`

## Exact contamination points found

1. Extension network cache was global/context-free within the page JS context.
2. Content script merged bridged and DOM network cache entries without page/profile/tab filtering.
3. Extractor hydrated visible DOM discoveries with network metadata by `aweme_id` only.
4. Popup transport knew `tab_id` but did not attach it to the capture payload.
5. Backend accepted item payloads without validating an item/capture context because the schema had none.
6. Backend `/capture-inbox/items` could be called without `capture_session_id`, exposing previous-session items to any caller using that endpoint.
7. Frontend default view was already session-detail scoped through `selectedSession.items`.

## Implementation completed

1. Extension types now include `CaptureContext`, `ContextMismatchCode`, and context fields on network metadata, videos, and capture payloads.
2. Network cache entries from both content-script and injected page hooks are stamped with page/profile context and observation time.
3. Content script builds an active context from current page and tab id before reading cache.
4. Extractor filters network/detail hydrate metadata by context before canonical `aweme_id` hydration.
5. Popup transport passes tab id into content-script capture messages and attaches it to direct fallback payloads.
6. Backend schemas accept capture context and item mismatch markers.
7. Backend staging persists session context, rejects item context mismatches, and records safe failure summaries.
8. Backend item list now requires `capture_session_id` by default.
9. Frontend code was not changed because current visible items are already derived from selected session detail.

## Verification completed

- `npm run test --workspace apps/extension-douyin-capture` passed.
- `python -m unittest tests.test_douyin_extension_capture_service` passed from `apps/api`.
- `python -m py_compile src/schemas/douyin_extension.py src/services/capture_inbox_service.py src/api/routes/capture_inbox.py` passed from `apps/api`.
- `pytest` was unavailable in this environment; `python -m pytest apps/api/tests/test_douyin_extension_capture_service.py` failed earlier with `No module named pytest`.

## Verification result

- Capturing page A no longer hydrates with page B/profile B/tab B context-bearing network metadata.
- Current session item listing is explicit-session scoped by backend contract.
- Backend rejects project/session/profile/page/tab mismatched item contexts before staging them into the current session.
- Out-of-scope items are excluded from the current Capture Inbox session instead of being silently merged.

## Non-goals preserved

- No thumbnail-specific fixes.
- No duration/stats fixes.
- No UI redesign.
- No queue/review/publish work.
- No crawler or video-processing implementation.
