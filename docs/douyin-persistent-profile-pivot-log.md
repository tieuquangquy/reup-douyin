# Douyin Persistent Profile Pivot Log

## 2026-04-23T09:38:42+07:00

### Findings

- Browser-assisted connect already uses a canonical backend service: `DouyinBrowserConnectService`.
- A runtime-only context registry exists in `DouyinBrowserContextRegistry`, but it keeps Playwright handles only in memory.
- Current validation and fetch can reuse a live browser context while the API process is alive.
- If the API process restarts or the browser context is closed, the account falls back to detached cookie/session validation.
- The existing happy path still contains an ephemeral fallback path where Playwright creates a temporary context and closes it after capture.
- `DouyinAccountConnection` is the canonical persisted account model; intake live fetch resolves accounts through `DouyinAccountService`.

### Fragility Points

- In-memory browser contexts disappear on API restart.
- Detached cookie validation/fetch is more fragile against Douyin than an actual browser profile.
- Re-login is required too often when only captured cookies remain.
- Reset/cancel should clear transient sessions but should not delete a persistent browser profile by default.

### Chosen Strategy

- Add persistent local browser profile support to the existing `DouyinBrowserContextRegistry`.
- Use Playwright `launch_persistent_context` when enabled.
- Store safe profile metadata on `DouyinAccountConnection.metadata_json`.
- Reopen the same profile from account metadata during validate/fetch when no live context is available.
- Keep `DouyinAccountConnection` and intake persistence unchanged.

### Files Touched

- `apps/api/src/core/settings.py`
- `apps/api/.env.example`
- `apps/api/src/services/douyin_browser_context_registry.py`
- `apps/api/src/services/douyin_browser_connect_service.py`
- `apps/api/src/services/douyin_account_service.py`
- `apps/web/src/components/douyin-accounts/DouyinAccountsPage.tsx`
- `apps/web/src/components/intake/IntakePage.tsx`
- `apps/web/src/lib/i18n/en.json`
- `apps/web/src/lib/i18n/vi.json`
- `scripts/dev-stop.ps1`
- `docs/douyin-persistent-profile-pivot-log.md`
- `docs/douyin-persistent-profile-pivot-resume.md`
- `docs/douyin-persistent-profile-pivot-architecture.md`
- `docs/douyin-persistent-profile-pivot-user-guide.md`

### Verification Notes

- Passed: `$env:PYTHONPATH='apps/api'; python -m unittest apps/api/tests/test_douyin_account_service.py apps/api/tests/test_douyin_browser_connect_service.py apps/api/tests/test_intake_discovery_service.py`
- Passed: API import smoke for browser context registry, browser connect service, and account service.
- Passed: `npm --workspace @reup-douyin/web run typecheck`
- Passed: `npm --workspace @reup-douyin/web run build`
- Passed: restarted local stack with `npm run dev:stop; npm run dev`.
- Passed smoke checks for `/`, `/accounts/douyin`, `/intake`, `/docs`, and `/douyin-accounts`.

### Status

Completed.
