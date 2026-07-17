# Phase 5E Open Profile Fix Log

## Status
- completed

## Exact root cause
- `python scripts/douyin_account_readiness.py --open-profile ...` used `DouyinBrowserConnectService.start_connect(...)`.
- `start_connect(...)` created a background thread with `daemon=True`.
- The CLI script returned immediately, so the Python process exited and the daemon thread died before the visible browser workflow could remain usable.
- Result: operator saw open-profile flow output but no stable browser window to continue manual Douyin login/captcha.

## Before / after behavior

### Before
- `--open-profile` only kicked off browser-connect async work.
- It depended on a daemon thread inside the short-lived CLI process.
- Browser window did not stay operator-usable.

### After
- `--open-profile` directly opens the saved persistent browser profile in visible mode via the browser context registry.
- The CLI process stays alive for the requested timeout (or until `Ctrl+C`) so the visible browser window remains usable for manual login/captcha.
- If opening fails, the command returns a structured actionable error.

## Worker / browser runner behavior
- Worker is **not** required for this command.
- Browser open now happens directly from the `apps/api` readiness script/process.

## Exact operator commands

```powershell
cd apps/api
python scripts/douyin_account_readiness.py --account-id 552e16ae-2d5c-40a6-a26c-bc917b28a172 --open-profile --timeout-seconds 300
python scripts/douyin_account_readiness.py --account-id 552e16ae-2d5c-40a6-a26c-bc917b28a172 --revalidate --timeout-seconds 120
python scripts/hydrate_capture_session_metadata.py --session-id a57e64d1-a7a8-48e0-b49a-199128b25740
```

## Files touched
- `apps/api/scripts/douyin_account_readiness.py`
- `apps/api/tests/test_douyin_account_readiness_script.py`
- `docs/metadata-phase5E-open-profile-fix-log.md`
- `docs/metadata-phase5E-open-profile-fix-resume.md`

## Tests run
- `python -m unittest tests.test_douyin_account_readiness_script tests.test_hydrate_capture_session_metadata_script tests.test_douyin_browser_connect_service`
- `python -m compileall src scripts`

## Verification result
- Focused tests passed.
- Live command verification passed:

```powershell
python scripts/douyin_account_readiness.py --account-id 552e16ae-2d5c-40a6-a26c-bc917b28a172 --open-profile --timeout-seconds 1
```

- Output returned:
  - `"success": true`
  - `"open_profile_status": "opened"`
