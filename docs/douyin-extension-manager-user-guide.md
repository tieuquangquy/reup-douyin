# Douyin Extension Manager User Guide

## What This Page Is For

The Douyin Extension Manager is the main operator page for the Douyin browser-extension workflow.

Open it at:

```text
/ops/extensions/douyin
```

Use it to:

- Download or locate the extension build.
- Open Chrome or Edge extension management pages.
- Check whether the extension is connected.
- Verify extension/backend version compatibility.
- Detect a Douyin page using safe page snapshot fields.
- Capture a Douyin page using safe page snapshot fields.
- Inspect recent detect/capture status and troubleshooting history.

## Browser Installation Limitation

Chrome and Edge do not allow this local web app to fully install an unpacked extension automatically.

The manager helps with download, build guidance, status, version checks, and troubleshooting. You still need to load the extension manually.

## Install Flow

1. Open the Extension Manager.
2. Click Download extension if a built ZIP is available.
3. If the download is missing, run from the repository root:

```powershell
npm run extension:build
```

4. Open one of these browser pages:

```text
chrome://extensions
edge://extensions
```

5. Enable Developer mode.
6. Choose Load unpacked.
7. Select `apps/extension-douyin-capture/dist` or the extracted ZIP folder.
8. Open the extension popup and confirm the backend URL.
9. Click Check extension connection in the popup.
10. Return to the manager and refresh/check status.

## Connection and Version Status

The manager shows:

- connected/disconnected status
- last seen time
- browser family
- extension version
- backend expected version
- compatibility state
- recommended next action

Healthy status should show connected and compatible.

## Detect Current Page

Best day-to-day flow: use the extension popup while a Douyin tab is active.

The manager also provides backend contract checks using safe fields only. Enter the current page URL/title/type/profile information and run Detect current page. The manager will show:

- detected page type
- whether capture is supported
- recommended next action
- operator guidance

## Capture Current Page

Best day-to-day flow: use the extension popup because it can read the real active tab.

The manager can submit a safe manual snapshot for capture testing or controlled operator workflows. It will show:

- success/failure
- imported/updated video counts
- candidate counts
- latest warning/error
- latest capture timestamp

## History

The manager shows recent extension manager events from `GET /douyin-extension/history`:

- handshake/status context
- detect attempts
- capture attempts
- timestamp
- page type and safe page URL/title when available
- success/failure
- imported profile/video/candidate counts
- short error or warning
- diagnostics id when available
- recommended next action

History is lightweight process-local Phase 1 state, capped at the newest 20 events. It is not a new discovery pipeline.

## Troubleshooting States

### not_installed_or_not_connected

Build/download the extension, manually load it in Chrome/Edge, open the extension popup, confirm backend URL, and run connection check.

### stale_connection

Open the extension popup and run Check extension connection again.

### version_mismatch

Rebuild/download the latest extension, remove or reload the old browser extension, and run connection check again.

### login_required

Open Douyin in the browser and log in manually.

### challenge_required

Solve the Douyin challenge manually in the browser, then retry detect/capture.

### unsupported_page

Open a profile, profile feed, home feed, or video detail page.

### capture_ready

Run Capture current page.

### capture_failed

Review the short error in manager history, correct the page/backend state, then retry.

## Privacy Rules

The manager does not need and should never show:

- cookies
- passwords
- auth tokens
- authorization headers
- browser profile paths
- local/session storage
- raw HTML

## Backend Endpoints Used

- `POST /douyin-extension/handshake`: called by the extension popup to report safe connection/version metadata.
- `GET /douyin-extension/status`: used by the manager to show connected/disconnected, stale, and version states.
- `GET /douyin-extension/history`: used by the manager to show recent handshake/detect/capture history.
- `GET /douyin-extension/download`: used by the manager download button when the extension build output exists.
- `POST /douyin-extension/detect-page`: used by the extension popup and manager safe snapshot tool.
- `POST /douyin-extension/capture-current-page`: used by the extension popup and manager safe snapshot capture tool.

## Legacy Managed Browser Path

Older Playwright-managed browser surfaces may still exist for legacy/debug use. They are not the normal manager flow.
