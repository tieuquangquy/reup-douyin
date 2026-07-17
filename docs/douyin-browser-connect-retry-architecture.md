# douyin-browser-connect-retry-architecture.md

## Goal
Provide predictable operator UX for browser connect retry/timeout/polling at [`/accounts/douyin`](apps/web/src/components/douyin-accounts/DouyinAccountsPage.tsx:56), while reusing canonical backend session lifecycle.

## Canonical Connect Lifecycle
Persisted status source remains [`DouyinBrowserConnectSessionStatus`](apps/api/src/enums/__init__.py:66):
- `PENDING`
- `LAUNCHING_BROWSER`
- `WAITING_FOR_LOGIN`
- `CAPTURING_SESSION`
- `VALIDATING`
- `COMPLETED` (terminal)
- `FAILED` (terminal)
- `CANCELLED` (terminal)

Frontend-only `idle` is absence of selected active session.

### Timeout Outcome Normalization
To avoid enum migration risk, timeout is normalized as a backend-derived terminal **outcome**:
- `timeout` when status is `FAILED` with timeout-class `error_code` (for example `login_timed_out`, `browser_launch_timed_out`, `validation_timed_out`, `overall_timed_out`)
- `failed` for non-timeout failures
- `completed` and `cancelled` map directly

This keeps one persisted state machine and still gives explicit timeout semantics to UI.

## Polling Model
Backend remains source of truth through [`GET browser-connect/{id}`](apps/api/src/api/routes/douyin_accounts.py:115).

UI polling rules:
1. Start polling only after successful start returns session id.
2. Poll at stable interval (2s).
3. Stop on terminal backend status (`COMPLETED`, `FAILED`, `CANCELLED`).
4. Ignore stale poll responses if they do not match currently selected session id.
5. Reset per-attempt local transient state on retry/new start.

## Timeout Model
Backend response will provide per-session timing metadata:
- `phase` (derived from status)
- `phase_deadline_at` (derived from `started_at` + configured timeout budget)
- `remaining_seconds` (derived, lower bounded to 0)
- `timed_out_at` when timeout outcome is detected
- `outcome` (`running|completed|failed|timed_out|cancelled`)

Backend is authoritative; frontend renders these fields without optimistic overrides.

## Retry Model (V1)
- Retry = create a **new** session via existing start endpoint.
- Old terminal sessions are immutable history.
- If a session is running, retry is blocked in UI; operator can `Cancel` first.
- No silent multi-session launch stacking.

## Cancel Behavior
- Reuse existing cancel endpoint [`cancel_session()`](apps/api/src/services/douyin_browser_connect_service.py:157).
- Cancel sets terminal state (`CANCELLED`), polling stops, retry becomes available.

## No-Duplication Strategy
- Keep existing backend service, model, and routes.
- Do not add second session table, second worker flow, or alternate browser-connect pipeline.
- Extend response contract and frontend rendering/polling logic only.

## V1 Simplifications (Intentional)
- No DB enum migration to add `TIMED_OUT` persisted status.
- No deep browser process kill orchestration beyond current cancel semantics.
- No attempt history page redesign; only current `/accounts/douyin` operator flow improvements.
