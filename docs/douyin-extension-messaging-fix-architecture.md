# Douyin Extension Messaging Fix Architecture

## Summary

Backend connection health and extension popup/content-script messaging are separate boundaries. A healthy backend handshake only proves the popup can reach the API. Detect current page and Capture current page require a live content script receiver in the active Douyin tab.

The fix introduces one canonical popup transport path that validates the active tab, checks supported Douyin URLs, sends the message, performs one content-script injection recovery attempt when the receiver is missing, retries once, and returns operator-friendly errors.

## Root Cause

The existing popup sends `chrome.tabs.sendMessage` directly to the active tab. If the active tab does not have `contentScript.js` loaded, Chrome throws a low-level error: `Could not establish connection. Receiving end does not exist.` This can happen when:

- the tab is unsupported;
- the active tab URL is unavailable;
- the Douyin tab was opened before the extension was installed/reloaded;
- the page has not been refreshed after extension reload;
- the content script failed to load or was not injected yet.

## Goals

- Keep Detect current page and Capture current page reliable on supported Douyin tabs.
- Validate active tab state before messaging.
- Recover once by injecting `contentScript.js` with `chrome.scripting.executeScript`.
- Retry the original message once after injection.
- Never show raw Chrome messaging errors as the primary operator message.
- Keep the backend API and downstream capture pipeline unchanged.

## Implemented Files

- `apps/extension-douyin-capture/src/popupTransport.ts`: canonical active-tab messaging helper.
- `apps/extension-douyin-capture/src/popup.ts`: Detect/Capture now use the shared helper and friendly error projection.
- `apps/extension-douyin-capture/src/chrome.d.ts`: extension API typing for tab URLs and `chrome.scripting.executeScript`.
- `apps/extension-douyin-capture/src/popupTransport.test.ts`: focused transport tests.
- `apps/extension-douyin-capture/package.json`: test script includes transport tests.

## Non-goals

- No backend ingest changes.
- No web manager changes unless required by extension contracts.
- No new crawler/discovery architecture.
- No automated browser install flow.

## Manifest Requirements

The MV3 manifest must include:

- `activeTab` for current-tab access initiated by the popup.
- `scripting` for one-time recovery injection.
- `storage` for popup settings.
- Douyin host permissions and content script matches for supported Douyin domains.

The audited manifest already includes these permissions and matches, so no manifest changes were required.

## Transport Design

One shared helper owns:

1. Query active tab.
2. Reject missing tab or missing URL with `no_active_tab`.
3. Reject unsupported URLs with `unsupported_tab`.
4. Send the message to the active tab.
5. If the error indicates no receiver, inject `contentScript.js` once.
6. Retry the original message once.
7. If retry fails, return `content_script_not_loaded` or `douyin_page_refresh_required` with actionable guidance.
8. If content script responds with unsupported capture state, project it as `capture_not_supported_on_this_page`.

Detect current page and Capture current page both use this helper, so active-tab validation, injection retry, and friendly error projection stay consistent.

## Operator Error Categories

- `no_active_tab`: no active browser tab is available.
- `unsupported_tab`: active tab is not a supported Douyin page.
- `content_script_not_loaded`: content script receiver is unavailable after recovery.
- `inject_failed`: recovery injection failed.
- `douyin_page_refresh_required`: user should refresh the Douyin tab and retry.
- `capture_not_supported_on_this_page`: page was reached but cannot be captured.

## Privacy

The transport layer does not collect cookies, tokens, browser storage, raw HTML, credentials, or private local paths.
