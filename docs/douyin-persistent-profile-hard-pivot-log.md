# Douyin Persistent Profile Hard Pivot Log

## 2026-04-23T09:55:11+07:00

### Findings

- `POST /douyin-accounts/browser-connect/start` did not accept a target `DouyinAccountConnection`.
- `DouyinBrowserConnectService.start_connect()` always created a new `DouyinBrowserConnectSession`.
- `DouyinBrowserContextRegistry.open_login_context_and_capture()` chose profile id from `workspace_id + connect_session_id`, so reconnect attempts could create different profile directories.
- `/accounts/douyin` had no account-row action to explicitly reopen the same saved browser profile.
- Validation/fetch had already started to prefer live/reopened profile state, but connect/reconnect identity was not yet anchored to one account profile.

### Architectural Root Cause

The primary connect path was still session-centric. A retry/reconnect meant "start another connect session", and that session could generate a new profile identity. For local Douyin auth, this is the wrong anchor. The stable identity must be the source account's persistent browser profile, not the transient connect session.

### Chosen Model

- `DouyinAccountConnection` remains canonical.
- Each account stores one persistent profile identity in `metadata_json`.
- New account connect creates one profile, then stores it on the created account.
- Existing account reconnect passes `account_connection_id` and reuses that account's stored profile.
- If the profile is already live in the API runtime, backend reuses that live context instead of launching another browser.
- If not live, backend reopens the same `userDataDir`.

### Files Touched

- `apps/api/src/schemas/douyin_accounts.py`
- `apps/api/src/services/douyin_browser_context_registry.py`
- `apps/api/src/services/douyin_browser_connect_service.py`
- `apps/api/tests/test_douyin_browser_connect_service.py`
- `apps/web/src/types/douyin-accounts.ts`
- `apps/web/src/components/douyin-accounts/DouyinAccountsPage.tsx`
- `apps/web/src/lib/i18n/en.json`
- `apps/web/src/lib/i18n/vi.json`
- `docs/douyin-persistent-profile-hard-pivot-architecture.md`
- `docs/douyin-persistent-profile-hard-pivot-resume.md`
- `docs/douyin-persistent-profile-hard-pivot-user-guide.md`

### Implementation Decisions

- Browser connect start now accepts `account_connection_id`.
- Existing-account reconnect uses `account-{account_connection_id}` as the deterministic profile identity when no stored profile id exists yet.
- If a live context for the account already exists and has authenticated Douyin cookies, backend reuses it directly.
- If a live context exists but is not authenticated yet, backend keeps using that same context and waits for login instead of launching a different profile.
- If no live context exists, backend reopens the account's stored `browser_profile_path` or deterministic account profile directory.
- `/accounts/douyin` now exposes an account-row `Open profile` action, so operator reconnect is explicitly account/profile-targeted.
- Force restart preserves the existing session's derived account id when available.
- New-account browser connect remains supported; the first successful connect stores the generated persistent profile metadata on the created `DouyinAccountConnection`.

### Verification Notes

- `npm --workspace @reup-douyin/web run typecheck` passed.
- `python -m py_compile apps/api/src/services/douyin_browser_context_registry.py apps/api/src/services/douyin_browser_connect_service.py apps/api/src/schemas/douyin_accounts.py` passed.
- `python -m unittest apps/api/tests/test_douyin_browser_connect_service.py apps/api/tests/test_douyin_account_service.py apps/api/tests/test_intake_discovery_service.py` passed with 28 tests.
- `npm --workspace @reup-douyin/web run build` passed.
- `npm run dev:stop` then `npm run dev` restarted API, web, and worker.
- Route smoke checks returned 200 for `/`, `/accounts/douyin`, `/intake`, FastAPI `/docs`, and `/douyin-accounts`.
- `npm run smoke` passed. This included API unit tests, Playwright launch probe, worker import, web tests, and web typecheck.

### Status

Completed.
