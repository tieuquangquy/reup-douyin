# playwright-runtime-fix-log.md

## Step
- Fix `browser_runtime_unavailable` at runtime/environment level so browser-assisted Douyin connect can actually run.

## Time Started
- 2026-04-22 (UTC)

## Findings
- Canonical browser-assisted flow is implemented in API service [`DouyinBrowserConnectService`](apps/api/src/services/douyin_browser_connect_service.py:108) and capture runner [`PlaywrightDouyinBrowserSessionCapture.capture()`](apps/api/src/services/douyin_browser_connect_service.py:53).
- Runtime check currently uses only module presence via [`_is_browser_runtime_available()`](apps/api/src/services/douyin_browser_connect_service.py:289), which checks `importlib.util.find_spec("playwright.sync_api")`.
- API dependency manifest already includes Python Playwright in [`apps/api/pyproject.toml`](apps/api/pyproject.toml).
- Worker does not run browser-assisted connect and has no Playwright dependency in [`apps/worker/pyproject.toml`](apps/worker/pyproject.toml).
- Web has no Playwright dependency and should not own browser runtime execution in [`apps/web/package.json`](apps/web/package.json).
- Existing docs already state Python Playwright + browser install command in [`docs/douyin-browser-connect-architecture.md`](docs/douyin-browser-connect-architecture.md:75) and [`docs/douyin-browser-connect-user-guide.md`](docs/douyin-browser-connect-user-guide.md:17).
- Current doctor/smoke scripts do not check Playwright import + browser launch readiness:
  - [`scripts/dev-doctor.ps1`](scripts/dev-doctor.ps1)
  - [`scripts/smoke-check.ps1`](scripts/smoke-check.ps1)

## Root Cause
- Local environment can have Python package partially present/missing browser binaries while readiness detection is too shallow (module presence only), causing runtime failures at connect start/capture time.

## Canonical Runtime Strategy (Chosen)
- **Python Playwright in API process is canonical**.
- No Node Playwright, no worker Playwright, no wrapper service.
- Keep existing architecture and only harden dependency/binary readiness + setup repeatability.

## Files Planned
- `apps/api/src/services/douyin_browser_connect_service.py`
- `scripts/dev-doctor.ps1`
- `scripts/smoke-check.ps1`
- `package.json`
- `docs/local-setup.md`
- `docs/runbooks/common-debug-checks.md`
- `docs/browser-connect-local-setup.md`
- `docs/playwright-runtime-setup.md`
- `docs/playwright-runtime-fix-resume.md`

## Install/Setup Direction
- API dependency installation remains `pip install -e .` from `apps/api`.
- Browser binary install will be made explicit and repeatable via command/script using `python -m playwright install chromium` in API context.

## Verification Plan
1. Install API dependencies.
2. Install Playwright browser binary (Chromium).
3. Run doctor check including Playwright import + launch smoke.
4. Run focused API tests.
5. Confirm `/accounts/douyin` browser-assisted connect no longer fails immediately with runtime unavailable.
6. Confirm manual fallback import remains usable.

## Status
- Audit complete.
- Implementation in progress.
