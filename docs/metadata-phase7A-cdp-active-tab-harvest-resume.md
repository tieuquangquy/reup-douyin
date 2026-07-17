# Phase 7A CDP Active-Tab Harvest Resume

## Current State

Phase 7A CDP active-tab harvesting is implemented in the extension. The background service worker owns privileged Chrome Debugger Protocol operations, while the content script owns operator workflow orchestration and communicates with background through extension messages.

## Important Files

- `apps/extension-douyin-capture/src/cdpAweme.ts`: pure parsing, bounded walking, exact matching, metric mapping, and sanitized raw evidence helpers.
- `apps/extension-douyin-capture/src/background.ts`: CDP attach/detach, Network response body processing, runtime scanner, aweme evidence cache, and CDP message handlers.
- `apps/extension-douyin-capture/src/contentScript.ts`: CDP start/stop/get/runtime scan bridge integrated with start/resume/stop/probe/unload/full-harvest lifecycle.
- `apps/extension-douyin-capture/src/modalHarvest.ts`: CDP-first source priority, probe diagnostics, PASS/WARN/FAIL semantics, and controller CDP aweme lookup callbacks.
- `apps/extension-douyin-capture/src/types.ts`: CDP status/evidence/probe/progress contract fields.
- `apps/extension-douyin-capture/public/manifest.json`: includes Chrome `debugger` permission.

## Source Priority

Use this order when continuing work:

1. `cdp_network_aweme`
2. `cdp_runtime_aweme`
3. `page_network_cache_aweme`
4. `script_hydration_aweme`
5. `video_element_duration` for duration only
6. DOM visual fallback for manual/WARN fallback only

## Resume Notes

- Do not move CDP operations into content script; `chrome.debugger` remains background-owned.
- Do not add backend browser crawling or captcha bypass behavior.
- Do not treat DOM visual extraction as PASS.
- Preserve existing flush cadence, pending queue, idempotent backend updates, stop/resume, duplicate avoidance, and progress storage.
- WARN means explicit override is required before harvest continues; PASS is the normal start requirement.

## Verification Command

Run from the repository root on Windows:

```cmd
cd apps\extension-douyin-capture && npx tsc -p tsconfig.json --noEmit && npx tsx src\cdpAweme.test.ts && npx tsx src\modalHarvest.test.ts && npx tsx src\background.test.ts
```

The latest focused run passed.