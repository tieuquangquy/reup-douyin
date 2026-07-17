# Metadata Phase 5B Extension Evidence Acquisition Log

## Scope

- Requested scope: Phase 5B only.
- Goal: make the Douyin extension collect real `raw_network_aweme` and/or `raw_detail_aweme` evidence for captured items.
- Non-goals:
  - no backend normalizer change
  - no Capture Inbox UI change
  - no hydration job
  - no fake metric extraction from DOM

## Phase 5A-R input evidence

Latest live audit result from Phase 5A-R:

- live session: `7a0084ad-20a7-4135-a6e1-db6f847e87af`
- live items: `49`
- `raw_network_aweme`: `0 / 49`
- `raw_detail_aweme`: `0 / 49`
- `raw_dom_snapshot`: `49 / 49`
- time usable: `98.0%`
- performance usable: `0.0%`
- processing fit usable: `0.0%`

Conclusion carried into Phase 5B:

- backend normalizer is not the immediate bottleneck
- extension evidence acquisition is the bottleneck

## Audit findings

### 1. Hook injection timing

- `public/manifest.json` registers `contentScript.js` with `run_at: "document_idle"`.
- `contentScript.ts` injects `pageNetworkHook.js` only after the content script has loaded.
- Result: the page-world hook can miss early Douyin network/detail responses that happen before idle.

Root-cause category:

- `hook_runs_too_late`

### 2. Page-world hook does not publish normalized aweme evidence

- `src/pageNetworkHook.ts` intercepts fetch/XHR in page world.
- It detects aweme-like objects and writes reduced metrics into `window.__DOUYIN_AWEME_CACHE__`.
- But it does **not** publish normalized `NetworkVideoMetadata` items into:
  - `window.__REUP_DOUYIN_NETWORK_CACHE__`
  - the DOM cache element
  - the `window.postMessage` bridge consumed by `contentScript.ts`
- `contentScript.ts` listens for `REUP_DOUYIN_NETWORK_CACHE_UPDATE`, but `pageNetworkHook.ts` never emits real normalized aweme evidence into that channel.

Root-cause categories:

- `page_world_to_content_world_bridge_missing`
- `network_cache_not_read_by_extractor`
- `payload_attachment_missing`

### 3. Detection logic is present but effectively disconnected

- `pageNetworkHook.ts` already contains:
  - recursive `normalizeDouyinNetworkPayload`
  - bounded raw aweme preservation
  - `publishCache`
  - detail-vs-network source classification
- But the live path uses only `detectAwemeObjects()` -> `cacheAwemeMetadata()` and stops there.
- The richer normalized evidence path is effectively dead code for live capture.

Root-cause category:

- `payload_attachment_missing`

### 4. Direct fallback path is intentionally null-safe

- `popupTransport.ts` direct execute-script fallback emits:
  - `raw_network_aweme: null`
  - `raw_detail_aweme: null`
- This is correct for safety and should remain fallback-only.

Root-cause category:

- `direct_path_mirror_missing` is **not** a bug here; it is an intentional non-network fallback.

## Chosen fix

Fix the narrowest working path:

1. move content script injection earlier to `document_start`
2. make `pageNetworkHook.ts` publish normalized network/detail evidence into the shared cache + bridge
3. keep exact-id extractor attachment unchanged, because it already expects `NetworkVideoMetadata`

## Expected architecture after fix

Douyin page response
-> page-world `pageNetworkHook`
-> recursive aweme detection + bounded raw evidence preservation
-> page-world shared cache + DOM cache element + `postMessage` bridge
-> content script receives bridged cache items
-> extractor exact-id matches by `aweme_id`
-> `VideoPayload.raw_network_aweme` / `raw_detail_aweme` / `raw_evidence_summary`

## Files touched

- `docs/metadata-phase5B-extension-evidence-acquisition-log.md`
- `docs/metadata-phase5B-extension-evidence-acquisition-resume.md`
- `docs/metadata-phase5B-extension-evidence-acquisition-architecture.md`
- `apps/extension-douyin-capture/public/manifest.json`
- `apps/extension-douyin-capture/src/contentScript.ts`
- `apps/extension-douyin-capture/src/pageNetworkHook.ts`
- `apps/extension-douyin-capture/src/networkCache.ts`
- `apps/extension-douyin-capture/src/extractor.test.ts`
- `apps/extension-douyin-capture/src/networkCache.test.ts`
- `apps/extension-douyin-capture/package.json`

## Implemented fix

### 1. Inject earlier

- Changed content script `run_at` from `document_idle` to `document_start`.
- Purpose: catch early Douyin network/detail responses before the page settles.

### 2. Publish normalized page-world evidence

- `pageNetworkHook.ts` now:
  - normalizes intercepted responses with recursive aweme detection
  - attaches capture context and observed timestamp
  - merges items into `__REUP_DOUYIN_NETWORK_CACHE__`
  - publishes them through:
    - DOM cache element
    - `window.postMessage`
- This connects page-world evidence to the content-script cache that extractor already consumes.

### 3. Keep reduced aweme metrics cache in sync

- `pageNetworkHook.ts` still populates `__DOUYIN_AWEME_CACHE__`
- It now does so from normalized evidence that has already been accepted into the shared cache path.

### 4. Align isolated-world normalizer

- `networkCache.ts` now matches the page hook more closely:
  - supports numeric `aweme_id`
  - supports `video_info` / `videoInfo`
  - supports `statistics_info` / `statisticsInfo`
  - supports `create_time_ms`
  - supports `duration_ms`

## Bridge/cache architecture result

- page response
  -> `pageNetworkHook.ts`
  -> normalized `NetworkVideoMetadata`
  -> shared cache + DOM cache + `postMessage`
  -> `contentScript.ts` message listener
  -> merged `bridgedNetworkItems`
  -> extractor exact-id payload assembly

## Evidence detection shapes covered

- `aweme_list`
- nested `data.aweme_list`
- nested `data.list`
- recursive nested objects/arrays
- explicit `aweme_id` with useful aweme-like keys

## Tests run

- `npm run typecheck`
- `npm test`
- `npm run build`

## Verification result

- Typecheck: passed
- Extension tests: passed
- Build: passed

## Exact live retest steps

1. Run:
   - `cd apps/extension-douyin-capture`
   - `npm run build`
2. Reload the unpacked extension in the browser.
3. Refresh the target Douyin page completely.
4. Open a real Douyin profile/feed page with visible videos.
5. Run `Capture current page`.
6. Re-run Phase 5A-R live audit:
   - `cd apps/api`
   - `python tests/metadata_phase5a_real_live_audit.py`

## Expected live retest acceptance signals

- `raw_network_aweme` coverage > `0`
  or `raw_detail_aweme` coverage > `0`
- `raw_evidence_summary.has_network_aweme` or `has_detail_aweme` no longer all false
- `duration_seconds` coverage > `0` when `video.duration` is present
- `view_count` / `like_count` coverage > `0` when `statistics` is present

## Status

- audit: complete
- implementation: pending
- tests: pending
- live retest instructions: pending
