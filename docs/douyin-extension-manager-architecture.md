# Douyin Extension Manager Architecture

## Summary

The Douyin Extension Manager is the primary backend/web-app control center for the browser-extension current-page capture workflow. It consolidates setup guidance, connection/version status, current-page detection, current-page capture, capture history, and troubleshooting into one operator route.

Canonical manager route: `/ops/extensions/douyin`.

## Goals

- Give operators one page to install, verify, detect, capture, and troubleshoot the Douyin browser extension.
- Reuse the existing extension current-tab capture architecture.
- Keep extension-based current-page capture as the primary Douyin collection path.
- Preserve the existing downstream pipeline: `SourceProfile`, `SourceVideo`, `CrawlSession`, `VideoMetricSnapshot`, and `VideoCandidate`.
- Add lightweight manager state and history without introducing a second discovery pipeline.
- Avoid raw cookies, auth tokens, credentials, browser profile paths, raw browser storage, and raw HTML in UI, logs, or manager history.

## Non-goals

- No automated Chrome/Edge extension installation.
- No Chrome Web Store or Edge Add-ons publishing workflow.
- No Playwright-managed browser runtime in the normal manager flow.
- No new crawler, scoring, rendering, publishing, queue, or database schema work.
- No replacement of the existing extension detect/capture endpoints.

## Audit Findings

### Extension package/build output

- Package: `apps/extension-douyin-capture`.
- Manifest: `apps/extension-douyin-capture/public/manifest.json`.
- Manifest version: `0.1.0`.
- Build output: `apps/extension-douyin-capture/dist`.
- Popup: `apps/extension-douyin-capture/src/popup.ts`.
- The popup can send handshake metadata and call detect/capture from the current active browser tab.

### Existing backend endpoints

- `POST /douyin-extension/handshake` records safe extension metadata and computes status/version compatibility.
- `GET /douyin-extension/status` returns current connection/version/install status.
- `GET /douyin-extension/download` serves a ZIP from the built extension `dist` directory.
- `POST /douyin-extension/detect-page` classifies a current-page snapshot and returns capture guidance.
- `POST /douyin-extension/capture-current-page` ingests current-page extension payloads through the canonical downstream pipeline.

### Existing setup UI

- Existing setup page route: `/setup/douyin-extension`.
- It covers installation guidance and connection status only.
- It does not provide manager-level current-page detect/capture actions or capture history.

### Existing version exposure

- Extension reads `chrome.runtime.getManifest().version`.
- Backend expected/supported version is `0.1.0`.
- Status response includes `backend_expected_extension_version`, `backend_supported_extension_versions`, `extension_version`, and `version_status`.

### Existing capture result shape

- Capture response includes success, page type, source profile id, crawl session id, imported/updated counts, candidate counts, warnings, current page URL/title, video link count, and next suggested route.

### Manager experience added

- `GET /douyin-extension/history` now returns recent safe manager events.
- The web manager route now combines status, recent history, install guidance, detect, capture, and troubleshooting in one place.
- Web app cannot directly read an arbitrary browser tab. Manager detect/capture controls therefore use operator-provided safe page snapshots unless the action is performed inside the extension popup.

## Manager Responsibilities

The manager page owns operator guidance and visibility:

- Install/download instructions and browser extension shortcuts.
- Current connection state and version compatibility.
- Current-page tools for safe manual snapshot-based detect/capture from the web app.
- Latest capture result and capture history.
- Troubleshooting states and next actions.

The manager page does not own crawling, parsing beyond existing extension payload contracts, direct database writes, or long-running processing.

## Extension Handshake/Status Model

The manager reuses the setup status model:

- `not_installed_or_not_connected`
- `installed_not_connected`
- `connected`
- `version_mismatch`
- `backend_unreachable_from_extension`
- `stale_connection`

The extension handshake remains metadata-only:

- install id
- extension id when available
- extension version
- browser family
- configured backend URL
- client timestamp

## Install/Download Flow

The manager links to `GET /douyin-extension/download`. The backend packages `apps/extension-douyin-capture/dist` as a ZIP if it exists.

Chrome and Edge installation remains manual:

1. Build or download the extension.
2. Extract ZIP if using download.
3. Open `chrome://extensions` or `edge://extensions`.
4. Enable Developer mode.
5. Load the unpacked extension folder.
6. Open the extension popup and check connection.

## Detect/Capture Flow

Primary day-to-day capture should happen from the extension popup because it can read the active browser tab safely.

The web manager may also call the existing backend detect/capture endpoints using safe operator-provided snapshot fields:

- URL
- title
- page type
- profile URL
- handle/display name
- video link count

The manager must not request or store cookies, auth tokens, browser storage, authorization headers, or raw HTML.

## Capture History/Troubleshooting Model

The backend maintains lightweight local manager history in Phase 1:

- timestamp
- action type: handshake, detect, or capture
- page type and safe page URL/title when available
- result status
- imported profile/video/candidate counts when available
- short error code/message when failed
- warning when returned by capture
- recommended next action
- diagnostics id when available

This is process-local operational history, not a new durable source discovery architecture. Future SaaS deployment can persist this state by workspace/operator/install id without changing the public contract.

## Operator Workflow

1. Open `/ops/extensions/douyin`.
2. Build/download and manually install the extension.
3. Open the extension popup and run connection check.
4. Confirm manager status is connected and compatible.
5. Open Douyin in the same browser.
6. Use the extension popup for real current-tab detect/capture, or use manager manual snapshot tools for backend contract checks.
7. Review latest capture result and history.
8. Follow troubleshooting guidance if the manager reports stale connection, version mismatch, unsupported page, login required, challenge required, or capture failure.

## Implemented Backend Endpoints

- `POST /douyin-extension/handshake` records extension metadata and manager handshake history.
- `GET /douyin-extension/status` returns connection and version state.
- `GET /douyin-extension/history` returns recent safe manager history.
- `GET /douyin-extension/download` serves the built extension ZIP when `dist` exists.
- `POST /douyin-extension/detect-page` classifies a safe page snapshot and records success/failure history.
- `POST /douyin-extension/capture-current-page` submits extension capture payloads through the canonical downstream pipeline and records success/failure history.

## Privacy and Security

The manager must never expose raw secrets. Error messages should be short and actionable, and must not include private absolute paths or raw browser state.
