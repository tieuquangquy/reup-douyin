# Douyin Extension Direct ExecuteScript Fix Log

## Goal

Hard-refactor the Douyin extension current-tab Detect/Capture actions so they execute directly in the active Douyin tab through `chrome.scripting.executeScript` and no longer depend on a preloaded content-script message listener.

## Initial Plan

1. Re-read `AGENTS.md` and audit popup, content script, extractor, transport, manifest, and tests.
2. Create mandatory direct-execution docs before code changes.
3. Replace the popup primary Detect/Capture path with active-tab validation plus direct script execution.
4. Keep backend handshake, detect, and capture endpoints unchanged.
5. Keep content script as legacy/auxiliary only, not required for primary Detect/Capture.
6. Add focused tests for direct execution decisions, supported/unsupported pages, login/challenge classification, friendly errors, and backend handoff shape.
7. Run extension typecheck, tests, and build.
8. Update docs with final implementation and verification notes.

## Audit Notes

- `apps/extension-douyin-capture/src/popup.ts` currently calls `sendCurrentTabMessage` for both Detect and Capture.
- `apps/extension-douyin-capture/src/popupTransport.ts` currently validates the active tab, sends `chrome.tabs.sendMessage`, injects `contentScript.js` if the receiver is missing, then retries the message once.
- `apps/extension-douyin-capture/src/contentScript.ts` registers `chrome.runtime.onMessage.addListener` and calls `detectPageFromDocument` or `buildCapturePayload`.
- `apps/extension-douyin-capture/src/extractor.ts` contains reusable DOM extraction logic, but imported module functions are not directly callable from a serialized `executeScript({ func })` callback unless the function is self-contained.
- `apps/extension-douyin-capture/public/manifest.json` already includes MV3, `activeTab`, `scripting`, `storage`, and Douyin host permissions/content script matches.

## Implementation Notes

- Replaced the popup primary current-tab transport in `apps/extension-douyin-capture/src/popupTransport.ts` with direct `chrome.scripting.executeScript` execution.
- `apps/extension-douyin-capture/src/popup.ts` now calls `executeCurrentTabAction("detect")` and `executeCurrentTabAction("capture")` instead of sending messages to a content-script listener.
- Added a self-contained in-tab runner function for detection and capture that reads safe DOM-derived data only.
- Kept backend handshake, detect, and capture endpoint payload shapes unchanged.
- Kept `apps/extension-douyin-capture/src/contentScript.ts` for legacy/auxiliary compatibility, but it is no longer required for primary Detect/Capture.
- Updated Chrome extension typings for `chrome.scripting.executeScript({ func, args })` result handling.
- Updated focused transport tests to cover direct execution, unsupported tabs, login/challenge pages, capture handoff shape, direct execution failures, and friendly error projection.
- No manifest change was required because `activeTab`, `scripting`, `storage`, supported host permissions, and MV3 configuration were already present.

## Verification

Commands run successfully:

```text
npm --workspace @reup-douyin/extension-douyin-capture run typecheck
```

```text
npm --workspace @reup-douyin/extension-douyin-capture run test
```

```text
npm --workspace @reup-douyin/extension-douyin-capture run build
```

## Final Status

Implemented and verified. Detect current page and Capture current page now use direct active-tab script execution as the primary path and no longer depend on a preloaded content-script message listener.
