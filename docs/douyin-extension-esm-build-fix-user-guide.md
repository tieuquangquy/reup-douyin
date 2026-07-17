# Douyin Extension ESM Build Fix User Guide

## What Changed

The extension popup build now emits browser-resolvable module imports. After rebuilding and reloading the extension, popup DevTools should no longer show `net::ERR_FILE_NOT_FOUND` for local modules such as `popupActions` or `popupTransport`.

## Rebuild the Extension

From the repository root, run:

```powershell
npm run extension:build
```

This writes the built extension to:

```text
apps/extension-douyin-capture/dist
```

## Reload in Chrome or Edge

1. Open `chrome://extensions` or `edge://extensions`.
2. Enable Developer mode.
3. Find the Reup Douyin Current Tab Capture extension.
4. Click Reload.
5. If the extension was not loaded yet, click Load unpacked and choose `apps/extension-douyin-capture/dist`.

## Verify the Popup

1. Open a supported Douyin tab.
2. Click the extension popup.
3. Open popup DevTools if needed.
4. Confirm there are no `ERR_FILE_NOT_FOUND` errors for local modules.
5. Click Check extension connection.
6. Click Detect current page.
7. Click Capture current page on a capturable Douyin page.

## If Errors Remain

- Confirm you loaded `apps/extension-douyin-capture/dist`, not `apps/extension-douyin-capture/src`.
- Re-run `npm run extension:build`.
- Reload the extension from the browser extensions page.
- Inspect `dist/popup.js`; local imports should end in `.js`.
