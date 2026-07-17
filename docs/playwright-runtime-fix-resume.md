# playwright-runtime-fix-resume.md

## Current Step
- Hardening runtime readiness checks and setup workflow for browser-assisted Douyin connect.

## Done
- Audited browser runtime dependency path across API/worker/web/manifests/scripts/docs.
- Confirmed canonical execution path is Python Playwright in API service [`DouyinBrowserConnectService`](apps/api/src/services/douyin_browser_connect_service.py:108).
- Confirmed API already declares `playwright` dependency in [`apps/api/pyproject.toml`](apps/api/pyproject.toml).
- Confirmed detection gap: readiness check currently only tests module presence in [`_is_browser_runtime_available()`](apps/api/src/services/douyin_browser_connect_service.py:289).

## In Progress
- Writing runtime setup docs and preparing script/code updates for robust readiness verification.

## Next Exact Task
- Implement stronger runtime detection in [`apps/api/src/services/douyin_browser_connect_service.py`](apps/api/src/services/douyin_browser_connect_service.py) to distinguish dependency missing, browser binary missing, and launch failure.

## Key Files To Continue
- `apps/api/src/services/douyin_browser_connect_service.py`
- `scripts/dev-doctor.ps1`
- `scripts/smoke-check.ps1`
- `package.json`
- `docs/playwright-runtime-setup.md`
- `docs/browser-connect-local-setup.md`
- `docs/local-setup.md`
- `docs/runbooks/common-debug-checks.md`
