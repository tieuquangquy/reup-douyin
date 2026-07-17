# Douyin Extension Direct ExecuteScript Fix Architecture

## Summary

The previous primary Detect/Capture path depended on messaging a content script listener in the active tab. That architecture is brittle because `chrome.tabs.sendMessage` fails when the content script was not preloaded or the listener is missing. The new primary path resolves the active tab, validates the Douyin URL, and directly executes a self-contained detector/extractor function in the active tab with `chrome.scripting.executeScript`.

## Old Brittle Flow

1. Popup resolves active tab.
2. Popup calls `chrome.tabs.sendMessage`.
3. The content script must already be loaded and must have registered `chrome.runtime.onMessage.addListener`.
4. If no listener exists, Chrome returns `Could not establish connection. Receiving end does not exist.`.
5. Previous recovery attempted to inject `contentScript.js` and retry messaging once, but the primary architecture still depended on listener messaging.

## New Direct ExecuteScript Flow

1. Popup resolves the active tab.
2. Popup validates that the tab has a URL and is on a supported HTTPS Douyin domain.
3. Popup calls `chrome.scripting.executeScript` with a self-contained in-tab action runner.
4. The action runner inspects the real page DOM directly and returns either:
   - a `PageSnapshot` for Detect current page; or
   - an `ExtensionCapturePayload` for Capture current page.
5. Popup sends the returned safe structure to the existing backend endpoint.

## Implemented Files

- `apps/extension-douyin-capture/src/popupTransport.ts` owns the direct execution transport, active-tab validation, in-tab runner, response normalization, and friendly error projection.
- `apps/extension-douyin-capture/src/popup.ts` calls `executeCurrentTabAction("detect")` and `executeCurrentTabAction("capture")` before posting unchanged payloads to the backend.
- `apps/extension-douyin-capture/src/chrome.d.ts` types function-based `chrome.scripting.executeScript` calls and their returned `result` values.
- `apps/extension-douyin-capture/src/popupTransport.test.ts` covers the direct execution helper and friendly error behavior.
- `apps/extension-douyin-capture/src/contentScript.ts` remains available for legacy/auxiliary compatibility only; it is not required by the primary popup flow.

## Active-Tab Resolution

The popup still queries `chrome.tabs.query({ active: true, currentWindow: true })`. It rejects missing tab id or missing URL with a friendly `no_active_tab` error.

## Current-Page Detection

The in-tab runner reads only safe DOM-derived metadata:

- URL
- title
- compact body text sample
- page type
- profile URL/external id/handle/display name
- visible video link count

It classifies login and challenge pages from URL/title/body markers.

## Capture Extraction

Capture uses the same in-tab runner and shared DOM helper logic. It returns the same safe extension capture payload shape already accepted by the backend. It does not export cookies, tokens, browser storage, raw HTML, credentials, or private local paths.

## Error Mapping

Operator-facing errors are explicit:

- `no_active_tab`
- `unsupported_tab`
- `unsupported_douyin_page`
- `login_page`
- `challenge_page`
- `capture_not_supported`
- `direct_execution_failed`

Low-level `Receiving end does not exist` is no longer part of the primary flow because the primary flow does not call `chrome.tabs.sendMessage`.

## Content Script Status

The content script may remain for compatibility or auxiliary use, but Detect current page and Capture current page must not depend on its message listener in the normal flow.

## Manifest Requirements

The manifest needs MV3 plus `activeTab`, `scripting`, `storage`, and Douyin host permissions. The audited manifest already has those requirements, so no manifest change was required.

## Verification Status

The direct execution architecture was verified with:

- `npm --workspace @reup-douyin/extension-douyin-capture run typecheck`
- `npm --workspace @reup-douyin/extension-douyin-capture run test`
- `npm --workspace @reup-douyin/extension-douyin-capture run build`
