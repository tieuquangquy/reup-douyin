# Douyin Browser Runtime Local Setup

## Runtime Stack

Browser-assisted Douyin connect uses Python Playwright in `apps/api`.

Do not install or wire Node Playwright for this feature.

## Fresh Setup Commands

From repo root:

```powershell
cd apps/api
pip install -e .
python -m playwright install chromium
cd ..\..
npm run doctor
npm run smoke
```

Alternative browser install from repo root:

```powershell
npm run playwright:install
```

## Expected Healthy Checks

`npm run doctor` should show:

- `api dependencies` PASS
- `playwright browser binary` PASS
- `playwright launch` PASS
- `api app import` PASS

`npm run smoke` should show:

- API app import succeeds
- API unit tests pass
- Playwright launch smoke prints `playwright launch ok`
- Web tests and typecheck pass

## Connect Flow Verification

1. Start the stack:

```powershell
npm run dev
```

2. Open:

```text
http://localhost:3000/accounts/douyin
```

3. Click browser connect.
4. A visible browser window should open to Douyin.
5. Complete login in that window.
6. The UI should move through:

- starting browser
- waiting for login
- capturing session
- validating session
- completed

If login is not completed, the session should time out or be cancellable without creating a fake account.

## Security Notes

- Never paste or commit a real Douyin cookie into docs or logs.
- The browser connect API never returns raw cookies.
- Manual import fallback remains available when local runtime setup is broken.
