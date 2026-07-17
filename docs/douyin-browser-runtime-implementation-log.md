# Douyin Browser Runtime Implementation Log

## Step

Fix the Douyin browser-assisted connect runtime so `/accounts/douyin` no longer fails immediately with `runtime_launch_failed: Playwright runtime probe failed: NotImplementedError`.

## Time Started

2026-04-23 01:39:29 +07:00

## Findings

- Frontend route `/accounts/douyin` renders `apps/web/src/components/douyin-accounts/DouyinAccountsPage.tsx`.
- Browser connect start calls `startDouyinBrowserConnect()` in `apps/web/src/lib/api.ts`.
- API endpoint is `POST /douyin-accounts/browser-connect/start` in `apps/api/src/api/routes/douyin_accounts.py`.
- Canonical backend service is `DouyinBrowserConnectService` in `apps/api/src/services/douyin_browser_connect_service.py`.
- Canonical runtime runner is `PlaywrightDouyinBrowserSessionCapture`.
- Current architecture uses Python Playwright inside the API process.
- Worker and web do not own browser runtime execution.
- Manual session import is already preserved in the same `/accounts/douyin` screen.

## Exact NotImplementedError Source

- There is no `raise NotImplementedError` in the browser-connect service itself.
- The observed error comes from the runtime probe catching a Playwright runtime exception and wrapping it as:
  - `runtime_launch_failed: Playwright runtime probe failed: NotImplementedError`
- The likely runtime cause on Windows is Playwright subprocess launch running under an incompatible asyncio event loop policy or runtime context.
- Repo base classes also contain intentional `NotImplementedError` abstract methods, but they are not on the canonical browser-connect path.

## Chosen Runtime Strategy

- Keep **Python Playwright in `apps/api`** as the single canonical browser runtime.
- Do not introduce Node Playwright.
- Do not move browser connect to worker.
- Do not create a second browser connect pipeline.

## Implementation Decisions

- Add a small runtime helper layer inside the existing service:
  - enforce Windows Proactor event loop policy before Playwright starts
  - classify Playwright runtime exceptions into actionable error codes
  - keep probe and launch logic in the canonical API service path
- Keep persisted session statuses unchanged for compatibility.
- Preserve safe API responses: no raw cookies returned to UI.
- Keep backward-compatible frontend help for old `runtime_launch_failed`, while new backend codes use `launch_failed`, `runtime_probe_failed`, or `runtime_not_supported`.
- Treat browser closure during login as `browser_closed`.

## Files Touched

- `apps/api/src/services/douyin_browser_connect_service.py`
- `apps/api/src/services/intake_discovery_service.py`
- `apps/api/tests/test_douyin_browser_connect_service.py`
- `apps/web/src/components/douyin-accounts/DouyinAccountsPage.tsx`
- `apps/web/src/lib/i18n/en.json`
- `apps/web/src/lib/i18n/vi.json`
- `scripts/dev-doctor.ps1`
- `scripts/smoke-check.ps1`
- `docs/douyin-browser-runtime-implementation-log.md`
- `docs/douyin-browser-runtime-implementation-resume.md`
- `docs/douyin-browser-runtime-implementation-architecture.md`
- `docs/douyin-browser-runtime-local-setup.md`
- `docs/douyin-browser-connect-troubleshooting.md`
- `docs/browser-connect-local-setup.md`
- `docs/playwright-runtime-setup.md`

## Verification Notes

Initial local probe command with Python Playwright succeeded in this shell:

```powershell
python -c "from playwright.sync_api import sync_playwright; ..."
```

The fix still needs service-level tests and API/runtime verification after implementation.

Completed verification:

- Service-level runtime probe returns `(True, None, None)` with and without launch.
- `npm run doctor` reports Playwright browser binary and launch PASS.
- API endpoint start/poll/cancel smoke:
  - start returned `LAUNCHING_BROWSER`
  - poll returned `WAITING_FOR_LOGIN`
  - cancel returned `CANCELLED`
- `/accounts/douyin` returned HTTP 200.
- Focused API tests passed:
  - `python -m unittest apps/api/tests/test_douyin_browser_connect_service.py apps/api/tests/test_intake_discovery_service.py`
- Full smoke passed:
  - `npm run smoke`
- Web verification passed:
  - `npm --workspace @reup-douyin/web run typecheck`
  - `npm --workspace @reup-douyin/web run test`

## Status

Completed.
