# playwright-runtime-setup.md

## Canonical Runtime Choice
- Canonical runtime for browser-assisted Douyin connect is **Python Playwright in API process**.
- Implemented by capture runner [`PlaywrightDouyinBrowserSessionCapture`](apps/api/src/services/douyin_browser_connect_service.py:52).
- Browser-assisted connect is started via API endpoint/service path, not web runtime and not worker runtime.

## Where Playwright Must Be Installed
- Install in the Python environment used to run `apps/api`.
- Dependency is declared in [`apps/api/pyproject.toml`](apps/api/pyproject.toml).

## Required Setup Commands (Windows)
From repo root:

```powershell
cd apps/api
pip install -e .
python -m playwright install chromium
```

Notes:
- `pip install -e .` installs Python package dependencies including Playwright.
- `python -m playwright install chromium` installs required browser binaries.

## Readiness Model
Runtime is ready only when all are true:
1. Playwright Python module is importable.
2. Playwright Chromium browser binary exists.
3. Local launch smoke for Chromium succeeds in API runtime context.

## Expected Runtime Errors
- `dependency_missing` / `browser_runtime_unavailable`: Playwright package not installed.
- `browser_binary_missing`: Playwright package installed but browser binary missing.
- `launch_failed`: package and binary exist but launch fails (policy/permissions/system dependency).
- `runtime_not_supported`: Playwright subprocess launch hit an incompatible runtime context, such as a Windows asyncio event loop policy issue.

## Local Dev Workflow
1. Run dependency install + browser install commands.
2. Run [`scripts/dev-doctor.ps1`](scripts/dev-doctor.ps1).
3. Start stack with [`scripts/dev-start.ps1`](scripts/dev-start.ps1).
4. Open `/accounts/douyin` and run browser-assisted connect.

## Troubleshooting Quick Notes
- If connect fails immediately with runtime unavailable, verify API Python environment path and rerun install commands.
- If binary missing, rerun `python -m playwright install chromium` in `apps/api` context.
- If launch fails, test local launch via doctor check output and inspect system/browser policy constraints.
- Manual import fallback at `/accounts/douyin` remains valid and should still be used when runtime cannot be repaired immediately.
