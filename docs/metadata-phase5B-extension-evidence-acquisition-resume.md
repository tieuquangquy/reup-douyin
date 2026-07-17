# Metadata Phase 5B Extension Evidence Acquisition Resume

## Current step

- Fix page-world evidence acquisition and bridge so exact-id raw aweme evidence reaches Capture Inbox payloads.

## Done

- Read Phase 5A-R live acceptance result.
- Audited extension evidence path:
  - `public/manifest.json`
  - `src/contentScript.ts`
  - `src/pageNetworkHook.ts`
  - `src/networkCache.ts`
  - `src/extractor.ts`
  - `src/popupTransport.ts`
- Confirmed root causes:
  - `hook_runs_too_late`
  - `page_world_to_content_world_bridge_missing`
  - `network_cache_not_read_by_extractor`
  - `payload_attachment_missing`

## In progress

- None

## Final outcome

- Injection moved to `document_start`
- Page-world hook now publishes normalized aweme evidence into the shared cache + bridge
- Content script now merges bridged evidence before extractor assembly
- Isolated-world network normalizer aligned with page hook for numeric/string id handling and wider aweme shapes

## Tests run

- `npm run typecheck`
- `npm test`
- `npm run build`

## Verification

- Passed locally for typecheck, focused tests, and extension build

## Next exact task

- Perform the live operator retest and rerun Phase 5A-R against a newly captured real session.

## Key files to continue

- `apps/extension-douyin-capture/public/manifest.json`
- `apps/extension-douyin-capture/src/contentScript.ts`
- `apps/extension-douyin-capture/src/pageNetworkHook.ts`
- `apps/extension-douyin-capture/src/networkCache.ts`
- `apps/extension-douyin-capture/src/extractor.ts`
