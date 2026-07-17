# Douyin Extension Download Fix User Guide

## What Changed

The Extension Manager and Extension Setup pages must now be honest about downloads:

- If the backend can package a built extension, the page shows a clickable Download extension or Download ZIP action.
- If the backend cannot package a built extension, the page shows Download unavailable and gives manual Load unpacked steps instead of a broken link.

## Build the Extension Locally

From the repository root, run:

```powershell
npm run extension:build
```

This creates the unpacked extension folder at:

```text
apps/extension-douyin-capture/dist
```

## Install with Load Unpacked

1. Open Chrome or Edge.
2. Open `chrome://extensions` or `edge://extensions`.
3. Enable Developer mode.
4. Click Load unpacked.
5. Select `apps/extension-douyin-capture/dist`.
6. Open the extension popup.
7. Confirm the backend URL, usually `http://127.0.0.1:8000`.
8. Run Check extension connection.

## Install with Download ZIP When Available

1. Open the Extension Manager or Extension Setup page.
2. If Download extension or Download ZIP is enabled, click it.
3. Extract the downloaded ZIP.
4. Open `chrome://extensions` or `edge://extensions`.
5. Enable Developer mode.
6. Click Load unpacked.
7. Select the extracted ZIP folder.
8. Open the extension popup and check connection.

## When Download Is Unavailable

This means the backend cannot find packageable build output. Use the manual workflow:

```powershell
npm run extension:build
```

Then load:

```text
apps/extension-douyin-capture/dist
```

## Important Limitations

Chrome and Edge do not allow this local web app to install an unpacked extension automatically. Manual browser installation remains required in both ZIP and Load unpacked workflows.
