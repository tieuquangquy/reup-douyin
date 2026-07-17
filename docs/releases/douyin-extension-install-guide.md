# Douyin Extension Install Guide

Release: `0.1.0`

## Prerequisites

- Windows operator machine.
- Chrome or Microsoft Edge.
- Local reup-douyin backend running and reachable from the browser.
- Default backend URL: `http://127.0.0.1:8000`.

## Build and package

From the repository root, run:

```cmd
npm --workspace @reup-douyin/extension-douyin-capture run package
```

This creates:

- Unpacked extension directory: `apps/extension-douyin-capture/release/reup-douyin-extension-0.1.0`
- Zip package: `apps/extension-douyin-capture/release/reup-douyin-extension-0.1.0.zip`
- Hygiene report: `apps/extension-douyin-capture/release/package-hygiene-report.json`

## Install unpacked in Chrome

1. Open Chrome.
2. Navigate to `chrome://extensions`.
3. Enable Developer mode.
4. Select Load unpacked.
5. Choose `apps/extension-douyin-capture/release/reup-douyin-extension-0.1.0`.
6. Confirm the extension appears as `Reup Douyin Current Tab Capture`.
7. Pin the extension if desired.

## Install unpacked in Microsoft Edge

1. Open Edge.
2. Navigate to `edge://extensions`.
3. Enable Developer mode.
4. Select Load unpacked.
5. Choose `apps/extension-douyin-capture/release/reup-douyin-extension-0.1.0`.
6. Confirm the extension appears as `Reup Douyin Current Tab Capture`.

## Configure backend URL

1. Open the extension popup.
2. Open Advanced.
3. Confirm API Base URL is `http://127.0.0.1:8000` or enter the operator backend URL.
4. Use Reconnect Douyin Tab after opening a Douyin profile page.

## First smoke test

1. Start the local backend.
2. Open a supported Douyin profile page.
3. Open the extension popup.
4. Confirm the health row shows a supported profile context.
5. Run Scan Profile.
6. Confirm the scanner builds a collection plan.
7. Use Capture Inbox only after save flow completes.

## Package download alternative

The backend may expose `GET /douyin-extension/download` for operator download. That endpoint packages the clean `dist` build. Run the package/build command first when preparing a release package.
