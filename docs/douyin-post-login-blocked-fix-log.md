# Douyin Post-Login Blocked Fix Log

## 2026-04-23T09:22:01+07:00

### Findings

- `/accounts/douyin` can complete browser login, but the first post-login browser-context prevalidation may return `blocked` with reason `browser_context_blocked_response`.
- The persistent browser context path raises `post_login_blocked:{reason}` in `apps/api/src/services/douyin_browser_context_registry.py` as soon as that first blocked-like page marker is seen.
- The non-persistent Playwright capture path raises the same `post_login_blocked:{reason}` in `apps/api/src/services/douyin_browser_connect_service.py`.
- `DouyinAccountService._validate_with_live_browser_context` currently maps a live browser-context `blocked` result directly to `DouyinAccountConnectionStatus.BLOCKED`.
- Existing browser connect retry UI exists, but the hard raise can end the session before the canonical `validation_retry_ready` path is reached.

### Root Cause

The first post-login browser-context probe is treated as a hard blocked classification. For Douyin, this probe can be too early or too aggressive immediately after QR/browser login, so a single ambiguous challenge-like response can prematurely become `post_login_blocked` / `browser_context_blocked_response`.

### Revised Strategy

- Keep stabilization before validation.
- Keep the browser context available when possible.
- Treat the first browser-context blocked-like result during browser connect as retryable post-login uncertainty.
- Route the connect session to `validation_retry_ready` instead of terminal hard failure.
- Mark the saved account `BLOCKED` only after repeated/canonical evidence, not on the first post-login blocked-like signal.
- Preserve the canonical `DouyinAccountConnection` and browser connect session flow.

### Files Touched

- `apps/api/src/services/douyin_browser_context_registry.py`
- `apps/api/src/services/douyin_browser_connect_service.py`
- `apps/api/src/services/douyin_account_service.py`
- `apps/api/tests/test_douyin_browser_connect_service.py`
- `apps/api/tests/test_douyin_account_service.py`
- `apps/web/src/components/douyin-accounts/DouyinAccountsPage.tsx`
- `apps/web/src/lib/i18n/en.json`
- `apps/web/src/lib/i18n/vi.json`
- `docs/douyin-post-login-blocked-fix-log.md`
- `docs/douyin-post-login-blocked-fix-resume.md`
- `docs/douyin-post-login-blocked-fix-architecture.md`
- `docs/douyin-post-login-blocked-user-guide.md`

### Verification Notes

- Passed: `$env:PYTHONPATH='apps/api'; python -m unittest apps/api/tests/test_douyin_account_service.py apps/api/tests/test_douyin_browser_connect_service.py`
- Passed: `npm --workspace @reup-douyin/web run typecheck`
- Passed: `npm --workspace @reup-douyin/web run build`
- Passed: API import smoke for browser connect, account service, and context registry modules.

### Status

Completed.
