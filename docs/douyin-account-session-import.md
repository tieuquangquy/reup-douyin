# Douyin Account Session Import

## What V1 Supports
Primary V1 support is browser-assisted connect from `/accounts/douyin`.

Manual Douyin session import is kept as a fallback:

1. Create or choose a Douyin account in the browser.
2. Copy the session cookie string from the browser developer tools.
3. Open `/accounts/douyin`.
4. Import the connection with a display name and cookie.
5. Validate the connection.
6. Select the validated connection on `/intake` when live fetching or forcing refresh.

## What V1 Does Not Support
- Password login.
- Storing Douyin password.
- Native QR protocol reverse engineering.
- Production-grade secret vaulting.

## Security Notes
- The API does not return raw cookies after import.
- Do not paste cookies into screenshots, logs, issues, or chat.
- Local DB storage is suitable only for Phase 1 local-first operation.
- For SaaS, replace local blobs with encrypted secret storage and account-scoped access controls.

## Browser-Assisted Direction
Browser-assisted connect now creates a short-lived login session, opens a real Douyin browser page, captures authenticated cookies after login, validates the account, and saves a canonical `DouyinAccountConnection`.

If the real Douyin page shows QR login, the operator scans that QR in the opened browser.
