# Douyin Extension Messaging Fix Log

## Goal

Fix the extension popup/content-script messaging path so Detect current page and Capture current page work on supported Douyin tabs and show operator-friendly guidance when the tab is unsupported or the content script is unavailable.

## Initial Plan

1. Re-read `AGENTS.md` and audit the current popup, background, content script, manifest, and extension tests.
2. Create the required messaging-fix docs before code changes.
3. Add one shared popup transport helper for active-tab lookup, Douyin URL validation, message sending, one-time content-script injection, retry, and friendly error projection.
4. Add focused extension tests for supported tabs, unsupported tabs, injection recovery, retry failure, and friendly error mapping.
5. Run extension typecheck/tests/build.
6. Update docs with final verification and completion notes.

## Audit Notes

- `apps/extension-douyin-capture/src/popup.ts` currently sends directly with `chrome.tabs.sendMessage` from the popup.
- `apps/extension-douyin-capture/src/background.ts` has a similar helper but the popup does not use it for Detect/Capture.
- `apps/extension-douyin-capture/src/contentScript.ts` registers `chrome.runtime.onMessage.addListener` and handles `REUP_DOUYIN_DETECT` plus `REUP_DOUYIN_CAPTURE`.
- Current popup transport does not validate the active tab URL before messaging.
- Current popup transport returns raw low-level Chrome messaging errors such as `Could not establish connection. Receiving end does not exist.`.
- `apps/extension-douyin-capture/public/manifest.json` is MV3, includes `activeTab`, `scripting`, and `storage`, and declares Douyin host permissions/content script matches for `www.douyin.com`, `*.douyin.com`, and `*.iesdouyin.com`.
- The manifest already has the permission required for `chrome.scripting.executeScript`; the likely root cause is stale/unloaded tabs or tabs opened before the extension/content script was loaded.

## Implementation Notes

- Added `apps/extension-douyin-capture/src/popupTransport.ts` as the canonical popup transport helper.
- The helper now resolves the active tab, requires a tab id and URL, validates supported Douyin HTTPS domains, sends the message, detects the missing-receiver Chrome error, injects `contentScript.js` once with `chrome.scripting.executeScript`, and retries once.
- Updated `apps/extension-douyin-capture/src/popup.ts` so Detect current page and Capture current page both use the shared transport helper.
- Replaced raw low-level messaging errors with operator-friendly messages.
- Updated `apps/extension-douyin-capture/src/chrome.d.ts` with tab URL and scripting API types.
- Added focused transport tests in `apps/extension-douyin-capture/src/popupTransport.test.ts`.
- Updated the extension test script so transport tests run with the existing extractor tests.
- No manifest changes were required because `activeTab`, `scripting`, `storage`, host permissions, and content script matches were already present.

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

Implemented and verified. The popup now validates tabs, recovers once from missing content-script receivers by injecting `contentScript.js`, retries the requested action, and shows friendly guidance if recovery is not possible.
