# Douyin Extension Setup User Guide

## What This Page Is For

The Douyin Extension Setup page helps you install and verify the browser extension used for current-tab Douyin capture.

Open it at `/setup/douyin-extension` in the web app.

The extension flow uses your real Chrome or Edge browser session. You browse Douyin normally, log in manually, solve any challenge manually, open the page you want, then use the extension to detect or capture the current visible tab.

## Important Limitation

Chrome and Edge do not allow a normal local web app to fully install an unpacked extension automatically.

The app can help you by:

- Providing a download link or build instructions.
- Opening or showing the Chrome/Edge extensions-page shortcuts.
- Showing manual install steps.
- Checking whether the extension has contacted the backend.
- Checking version compatibility.

You still need to load the extension manually in the browser.

## Setup Steps

### 1. Build or Download the Extension

Use the setup page download button if the backend reports that a ZIP is available.

If the backend says the build is missing, build it from the repository root:

```powershell
npm run extension:build
```

The unpacked build output is:

```text
apps/extension-douyin-capture/dist
```

### 2. Open Your Browser Extensions Page

Chrome:

```text
chrome://extensions
```

Edge:

```text
edge://extensions
```

The setup page may provide buttons for these shortcuts. If the browser blocks them, copy and paste the URL into the address bar manually.

### 3. Enable Developer Mode

In Chrome or Edge extensions page:

1. Turn on Developer mode.
2. Choose Load unpacked.
3. Select the `apps/extension-douyin-capture/dist` folder.
4. Confirm that the Reup Douyin Current Tab Capture extension appears.

If using the ZIP download, extract it first and then load the extracted folder as an unpacked extension.

### 4. Configure Backend URL

Open the extension popup and confirm the backend URL.

Default local backend URL:

```text
http://127.0.0.1:8000
```

If your API runs elsewhere, update the URL in the extension popup.

### 5. Check Connection

Use either:

- The setup page Check extension connection button to refresh the backend-reported status.
- The extension popup Check extension connection button to send a fresh handshake to the backend.

A healthy setup should show:

- Status: connected.
- Recent last seen time.
- Browser family, if detectable.
- Extension version.
- Backend expected version.
- Compatibility: compatible.
- Recommended next action: open Douyin and capture.

## Status Meanings

### `not_installed_or_not_connected`

The backend has not received a handshake from the extension in this backend process.

Recommended actions:

1. Build/download the extension.
2. Load it manually in Chrome or Edge.
3. Open the extension popup.
4. Confirm the backend URL.
5. Run the connection check again.

### `installed_not_connected`

Reserved for future setup flows where the browser can report that the extension exists but has not reached the backend.

Recommended action: open the extension popup and check the backend URL.

### `connected`

The backend recently received a compatible extension handshake.

Recommended action: open Douyin in the same browser, log in if needed, open the target page, then use Detect current page and Capture current page.

### `version_mismatch`

The extension contacted the backend, but the extension version does not match the backend-supported version.

Recommended action: rebuild or download the current extension and reload it in the browser extensions page.

### `backend_unreachable_from_extension`

The extension could not reach the backend.

Recommended actions:

1. Confirm the API server is running.
2. Confirm the backend URL in the extension popup.
3. Try `http://127.0.0.1:8000` for local development.
4. Check firewall/proxy settings if needed.

### `stale_connection`

The backend received a handshake before, but it is no longer recent.

Recommended action: open the extension popup and run the connection check again.

## What Gets Sent During Setup

The setup handshake may send safe metadata:

- Extension install/session id.
- Extension id when available.
- Extension version.
- Browser family.
- Configured backend URL.
- Timestamp.

## What Is Never Needed

Do not paste or send:

- Cookies.
- Passwords.
- Auth tokens.
- Authorization headers.
- Browser profile paths.
- Local storage/session storage.
- Raw page HTML.

The extension setup check does not need these values.

## Implemented Setup Contracts

The setup flow uses these backend endpoints:

- `POST /douyin-extension/handshake`: extension-to-backend metadata handshake.
- `GET /douyin-extension/status`: web setup page status refresh.
- `GET /douyin-extension/download`: extension ZIP download when the built `dist` folder exists.

The capture flow still uses these extension endpoints after setup:

- `POST /douyin-extension/detect-page`.
- `POST /douyin-extension/capture-current-page`.

## Verification Status

The completed setup implementation was verified with backend setup tests, backend capture regression tests, extension build/tests, web typecheck, route navigation coverage, and the full web test command.

## After Setup

Once connected and compatible:

1. Open Douyin in Chrome or Edge.
2. Log in manually if needed.
3. Solve any challenge manually if needed.
4. Open a profile, profile feed, home feed, or video detail page.
5. Click Detect current page in the extension popup.
6. Click Capture current page.
7. Review imported candidates in the normal review flow.

## Legacy Managed Browser Path

Older Playwright-managed browser features may still exist in legacy/debug areas. They are not the primary setup or capture path. Use the extension setup and current-tab capture flow first.

## Troubleshooting

### The setup page says no connection

Open the extension popup, verify the backend URL, and click the extension connection check. Then refresh the setup page.

### The browser blocks `chrome://extensions` or `edge://extensions`

Copy the shortcut text from the setup page and paste it directly into the browser address bar.

### The download says build missing

Run:

```powershell
npm run extension:build
```

Then reload the setup page and try download again, or load the unpacked `dist` folder manually.

### Version mismatch remains after rebuild

Remove the old extension from the browser, load the rebuilt `dist` folder again, and run the connection check.
