# Douyin Browser Connect User Guide

## What It Does
Browser-assisted connect lets the local operator connect a Douyin source account without copying cookies by hand.

The app opens a real Douyin login page. If Douyin shows a QR code, scan it there. After login succeeds, the API captures the browser session, validates it, and saves a normal Douyin account connection.

## Steps
1. Open `/accounts/douyin`.
2. Click `Connect with browser`.
3. Complete login in the opened Douyin browser window.
4. Wait for the status panel to move from waiting to validating.
5. When complete, the account appears in the connected accounts table.
6. Open `/intake` and select the connected account for live fetch or force refresh.

## Local Runtime Requirement
The API uses Playwright for the local browser flow.

After installing API dependencies, run this once if the Playwright browser is not installed:

```powershell
python -m playwright install chromium
```

## Browser-Assisted vs Manual Import
- Browser-assisted is the primary V1 UX.
- Manual import remains as a fallback when the local browser runtime is unavailable.
- Both paths save the same canonical `DouyinAccountConnection` record.

## Security Notes
- Do not enter a password into the app UI.
- The app does not return raw cookies after saving.
- Do not paste session cookies into logs, screenshots, issues, or chat.
- V1 local storage is suitable for local-first operation, not SaaS-grade secret vaulting.

## Deferred
- Native QR protocol integration.
- Password login.
- Cloud brokered auth.
- Mobile login flow.
- Production secret vault integration.
