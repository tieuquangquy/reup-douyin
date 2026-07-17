# Douyin Extension Direct ExecuteScript Fix Resume

## Current Goal

Make Detect current page and Capture current page execute directly in the active Douyin tab through `chrome.scripting.executeScript`, avoiding the brittle dependency on a preloaded content-script message listener.

## Canonical Direction

The extension popup remains the primary current-tab operator surface. Backend handshake/status and backend capture endpoints stay unchanged. The primary current-tab execution path must be direct tab execution, not popup-to-content-script messaging.

## Relevant Files

- `apps/extension-douyin-capture/src/popup.ts`
- `apps/extension-douyin-capture/src/popupTransport.ts`
- `apps/extension-douyin-capture/src/contentScript.ts`
- `apps/extension-douyin-capture/src/extractor.ts`
- `apps/extension-douyin-capture/src/types.ts`
- `apps/extension-douyin-capture/src/chrome.d.ts`
- `apps/extension-douyin-capture/public/manifest.json`
- `apps/extension-douyin-capture/src/popupTransport.test.ts`
- `apps/extension-douyin-capture/src/extractor.test.ts`

## Completed Work

- Re-read `AGENTS.md`.
- Audited popup Detect/Capture path.
- Audited transport helper and removed the primary `chrome.tabs.sendMessage` dependency.
- Audited content-script listener registration and retained it only for legacy/auxiliary compatibility.
- Audited reusable extractor logic and duplicated the required safe DOM logic inside the self-contained in-tab runner because Chrome serializes `executeScript({ func })` callbacks.
- Audited manifest permissions and host permissions.
- Created this mandatory direct-execution documentation set before code changes.
- Replaced `sendCurrentTabMessage` primary path with direct `chrome.scripting.executeScript` execution.
- Added `executeCurrentTabAction` as the canonical helper for active-tab lookup, URL validation, direct execution, result normalization, and friendly error projection.
- Added a self-contained in-tab runner for Detect current page and Capture current page.
- Updated focused transport tests for direct execution, friendly error states, and backend handoff shape.
- Updated Chrome extension typings for `chrome.scripting.executeScript({ func, args })` result handling.

## Verification Completed

The following commands passed:

- `npm --workspace @reup-douyin/extension-douyin-capture run typecheck`
- `npm --workspace @reup-douyin/extension-douyin-capture run test`
- `npm --workspace @reup-douyin/extension-douyin-capture run build`

## Resume Point

No implementation resume is currently required. The direct executeScript refactor is implemented and verified. If future work resumes from this note, start by checking the operator-reported browser behavior against `apps/extension-douyin-capture/src/popupTransport.ts` and the direct execution tests in `apps/extension-douyin-capture/src/popupTransport.test.ts`.
