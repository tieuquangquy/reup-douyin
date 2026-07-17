# Phase 7B CDP Observability Attach-Before-Modal Resume

## Current State

The extension popup now exposes explicit CDP controls and diagnostics for the active Douyin tab. The background service worker owns privileged Chrome Debugger Protocol calls, while the content script continues to own modal probe and harvest orchestration.

## Implemented Files

- `apps/extension-douyin-capture/public/manifest.json`
- `apps/extension-douyin-capture/public/popup.html`
- `apps/extension-douyin-capture/src/background.ts`
- `apps/extension-douyin-capture/src/background.test.ts`
- `apps/extension-douyin-capture/src/chrome.d.ts`
- `apps/extension-douyin-capture/src/modalHarvest.ts`
- `apps/extension-douyin-capture/src/popup.ts`
- `apps/extension-douyin-capture/src/types.ts`

## Important Behavior

Probe source priority remains:

1. `cdp_network_aweme`
2. `cdp_runtime_aweme`
3. `page_network_cache_aweme`
4. DOM fallback

`PASS` requires an exact CDP/page-cache source plus duration, like, comment, favorite, and share counts. DOM fallback and partial exact metrics are `WARN`. Missing aweme id or duration is `FAIL`. Normal full harvest is blocked for `WARN` unless the popup performs the explicit warning override path.

## Follow-Up Guidance

If live probe still shows DOM fallback only, the operator should attach CDP before opening the modal or use `Attach CDP and Refresh Current Modal`. Do not patch DOM rail heuristics for this symptom unless CDP diagnostics show that exact aweme data is unavailable from both network and runtime.

## Validation Commands

Run from `apps/extension-douyin-capture`:

```cmd
npx tsc -p tsconfig.json --noEmit
npx tsx src\\background.test.ts
npx tsx src\\modalHarvest.test.ts
npm run test
```
