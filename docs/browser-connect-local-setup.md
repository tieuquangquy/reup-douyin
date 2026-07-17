# browser-connect-local-setup.md

## Purpose
- Make browser-assisted Douyin connect runnable on a fresh local machine without hitting `browser_runtime_unavailable`.

## Canonical Runtime
- Browser-assisted connect uses **Python Playwright in API** via [`PlaywrightDouyinBrowserSessionCapture`](apps/api/src/services/douyin_browser_connect_service.py:52).
- Do not install Node Playwright for this feature path.

## Fresh Setup (Windows)
1. Copy env files (if not yet copied).
2. Install API dependencies:
   - `cd apps/api`
   - `pip install -e .`
3. Install Playwright Chromium browser runtime:
   - `python -m playwright install chromium`
   - or from repo root: `npm run playwright:install`
4. Run environment checks:
   - `npm run doctor`
5. Run smoke checks:
   - `npm run smoke`

## Runtime Readiness Signals
- API runtime probe returns actionable failure codes from [`_runtime_probe()`](apps/api/src/services/douyin_browser_connect_service.py:290):
  - `dependency_missing`
  - `browser_binary_missing`
  - `launch_failed`
  - `runtime_probe_failed`
  - `runtime_not_supported`
- UI at `/accounts/douyin` shows deterministic failed state and keeps manual import fallback accessible.

## If Browser Connect Still Fails
- `dependency_missing`: reinstall API dependencies in the same Python environment used by API process.
- `browser_binary_missing`: run `python -m playwright install chromium` in `apps/api`.
- `launch_failed`: check local OS/browser policy, antivirus/sandbox rules, and rerun doctor.
- `runtime_not_supported`: restart API after the Windows Playwright event-loop policy fix and rerun doctor.

## Manual Fallback
- Manual session import remains available in `/accounts/douyin` and should be used when runtime cannot be repaired immediately.
