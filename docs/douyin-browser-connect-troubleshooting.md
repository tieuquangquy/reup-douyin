# Douyin Browser Connect Troubleshooting

## Root Cause Fixed In This Pass

The previous failure:

```text
runtime_launch_failed: Playwright runtime probe failed: NotImplementedError
```

came from the API runtime probe wrapping a Playwright runtime exception. The repo browser-connect service did not directly raise `NotImplementedError`; Playwright subprocess startup could hit it in an incompatible Windows asyncio runtime context.

The canonical service now forces the Windows Proactor event loop policy before Playwright starts and maps this class of failure to an actionable runtime error.

## Common Failure Categories

### `dependency_missing`

Playwright Python package is not installed in the API Python environment.

Fix:

```powershell
cd apps/api
pip install -e .
```

### `browser_binary_missing`

Playwright is installed, but Chromium browser binaries are missing.

Fix:

```powershell
cd apps/api
python -m playwright install chromium
```

or:

```powershell
npm run playwright:install
```

### `launch_failed`

Playwright and browser binary exist, but Chromium cannot launch.

Check:

```powershell
npm run doctor
```

Common causes:

- antivirus or local security policy blocks browser launch
- corrupted Playwright browser install
- incompatible proxy/runtime configuration

### `runtime_not_supported`

Playwright subprocess launch hit `NotImplementedError`, usually because the API process is using an incompatible Windows asyncio event loop policy.

Fix:

1. Pull the runtime fix.
2. Restart the API process.
3. Run `npm run doctor`.
4. Retry browser connect.

### `browser_closed`

The browser window or page closed before login completed.

Fix:

- Start browser connect again.
- Keep the browser open until `/accounts/douyin` reports completion.
- Use manual import fallback if the browser window keeps closing.

### `login_timed_out`

The operator did not complete Douyin login before timeout.

Fix:

- Retry browser connect.
- Increase timeout only if needed through the API request path.
- Use manual import fallback when login cannot complete.

### `validation_failed`

The session was captured, but the canonical Douyin account validation path did not accept it.

Fix:

- Retry browser connect.
- Try manual import with a known-good session.
- Use account validation action after saving.

## What Should No Longer Happen

- `/accounts/douyin` should not fail immediately because the canonical runtime path depends on a stub.
- Runtime probe failure should not surface as an unexplained `NotImplementedError`.
- Manual import fallback should not disappear when browser connect fails.

## Verification Commands

```powershell
npm run doctor
npm run smoke
npm --workspace @reup-douyin/web run typecheck
```

Endpoint smoke when API is running:

```powershell
$body = @{ display_name = "Runtime smoke"; timeout_seconds = 30; is_default = $false } | ConvertTo-Json
$session = Invoke-RestMethod -Uri "http://127.0.0.1:8000/douyin-accounts/browser-connect/start" -Method POST -ContentType "application/json" -Body $body
Invoke-RestMethod -Uri "http://127.0.0.1:8000/douyin-accounts/browser-connect/$($session.id)/cancel" -Method POST
```

This should reach at least `LAUNCHING_BROWSER` or `WAITING_FOR_LOGIN` before cancellation if runtime is healthy.

## Reset Stuck Browser Connect State

Use this only when local browser connect state is inconsistent, for example:

- `/accounts/douyin` keeps showing an old active session
- the browser window is already closed but the backend still appears blocked
- polling is attached to an abandoned local session

API recovery:

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/douyin-accounts/browser-connect/reset" -Method POST -ContentType "application/json" -Body "{}"
```

UI recovery:

- Open `/accounts/douyin`
- Click `Reset browser connect state`
- Confirm the warning
- Start browser connect again

Reset only terminalizes browser-connect attempts. It does not delete saved Douyin accounts or validated account connections.
