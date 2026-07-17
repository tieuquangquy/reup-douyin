# Douyin Extension Download Fix Architecture

## Summary

The local-first extension install flow has two truthful modes:

1. **Download available**: the backend packages the built extension `dist` directory into a ZIP and serves it from `GET /douyin-extension/download`.
2. **Download unavailable**: the UI does not render a clickable broken download link and instead instructs the operator to build locally and load the unpacked `dist` folder.

## Backend Contract

`GET /douyin-extension/status` is the source of truth for whether the download action should be enabled.

Important status fields:

- `download_available`: true only when a packageable built extension directory exists.
- `download_url`: stable relative URL `/douyin-extension/download`.
- `manual_install_required`: always true for local unpacked/browser-managed installation.
- `chrome_extensions_url` and `edge_extensions_url`: browser extension management shortcuts.

`GET /douyin-extension/download` serves a ZIP only when build output exists. If output is missing or empty, it returns a clear error instead of pretending a file exists.

## Packaging Strategy

The extension workspace build command creates unpacked output:

```powershell
npm run extension:build
```

The backend uses Python standard library ZIP creation to package files from:

```text
apps/extension-douyin-capture/dist
```

This avoids new dependencies and preserves a simple local-first workflow.

## Web UI Rules

The web UI must not infer download availability from the URL helper alone.

- If status is loaded and `download_available` is true, render a clickable Download extension/ZIP link.
- If status is missing or `download_available` is false, render an unavailable state and manual Load unpacked instructions.
- Always keep Chrome/Edge extension-page shortcuts visible.
- Always make clear that browser installation is manual.

## Manual Install Workflow

1. Run `npm run extension:build` from the repository root.
2. Open `chrome://extensions` or `edge://extensions`.
3. Enable Developer mode.
4. Choose Load unpacked.
5. Select `apps/extension-douyin-capture/dist`.
6. Open the extension popup and check backend connection.

## Non-Goals

- No automatic extension install.
- No external artifact hosting.
- No Chrome Web Store packaging.
- No unrelated capture/backend changes.
