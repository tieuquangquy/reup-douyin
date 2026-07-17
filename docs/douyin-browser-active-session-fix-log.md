# douyin-browser-active-session-fix-log.md

## Step: Active/stale browser connect session fix

### Time Started
- 2026-04-23

### Findings
- Canonical browser-assisted connect path is still `DouyinBrowserConnectService` in `apps/api/src/services/douyin_browser_connect_service.py`.
- `/accounts/douyin` calls `startDouyinBrowserConnect()` from `apps/web/src/lib/api.ts`, which posts to `POST /douyin-accounts/browser-connect/start`.
- Poll and cancel already existed through:
  - `GET /douyin-accounts/browser-connect/{connect_session_id}`
  - `POST /douyin-accounts/browser-connect/{connect_session_id}/cancel`
- Active-session guard was in `DouyinBrowserConnectService.start_connect()` and queried any session with status in `PENDING`, `LAUNCHING_BROWSER`, `WAITING_FOR_LOGIN`, `CAPTURING_SESSION`, `VALIDATING`.
- The old guard raised a flat `active_session_exists` error when any running-looking session existed.
- Existing model already inherits `created_at` and `updated_at`, so V1 stale detection does not need a migration.
- Frontend only stored the session it started in the current tab; it did not discover or attach to an already-running backend session on page load.

### Root Cause
- Backend treated every running-looking session as active forever until the background thread set a terminal state or the operator cancelled the known session id.
- Frontend did not have a recovery path when the active session id belonged to an older page/tab/process.
- `active_session_exists` therefore became a dead end when the browser/thread/session was stale or the UI had lost the session id.

### Decisions Made
- Keep one canonical connect session model and service.
- Do not add a second browser-connect pipeline.
- Reuse `updated_at` as the phase progress timestamp.
- Treat running-looking sessions as stale when their current phase deadline expires.
- Before start creates a new session, auto-finalize stale running-looking sessions as `FAILED` with a timeout-class error.
- If a truly active session exists, return that session from start so the UI can resume/poll it instead of surfacing a dead-end error.
- Add a small active-session endpoint and restart endpoint for explicit UI actions.
- Prevent background browser flow from overwriting a terminal state after cancel/stale finalization.

### Files Touched
- `apps/api/src/services/douyin_browser_connect_service.py`
- `apps/api/src/api/routes/douyin_accounts.py`
- `apps/api/src/schemas/douyin_accounts.py`
- `apps/api/tests/test_douyin_browser_connect_service.py`
- `apps/web/src/lib/api.ts`
- `apps/web/src/types/douyin-accounts.ts`
- `apps/web/src/components/douyin-accounts/DouyinAccountsPage.tsx`
- `apps/web/src/lib/i18n/en.json`
- `apps/web/src/lib/i18n/vi.json`
- `docs/douyin-browser-active-session-fix-log.md`
- `docs/douyin-browser-active-session-fix-resume.md`
- `docs/douyin-browser-active-session-state-machine.md`
- `docs/douyin-browser-active-session-user-guide.md`
- `docs/douyin-browser-connect-user-flow.md`

### Verification Notes
- Backend browser-connect unit tests passed:
  - `PYTHONPATH=apps/api python -m unittest apps/api/tests/test_douyin_browser_connect_service.py`
- Python compile sanity passed for changed API route/schema/service:
  - `python -m compileall -q apps/api/src/services/douyin_browser_connect_service.py apps/api/src/api/routes/douyin_accounts.py apps/api/src/schemas/douyin_accounts.py`
- FastAPI route registration sanity passed and includes:
  - `/douyin-accounts/browser-connect/start`
  - `/douyin-accounts/browser-connect/active`
  - `/douyin-accounts/browser-connect/{connect_session_id}`
  - `/douyin-accounts/browser-connect/{connect_session_id}/restart`
  - `/douyin-accounts/browser-connect/{connect_session_id}/cancel`
- Frontend typecheck passed:
  - `npm --workspace @reup-douyin/web run typecheck`
- Frontend production build passed:
  - `npm --workspace @reup-douyin/web run build`
- Live local endpoint sanity passed:
  - `GET http://127.0.0.1:8000/douyin-accounts/browser-connect/active` returned `{"session": null}` when no active session existed.
  - `GET http://localhost:3000/accounts/douyin` returned `200 OK`.

### Status
- Completed.
