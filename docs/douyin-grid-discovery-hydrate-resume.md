# Douyin Grid Discovery Hydrate Resume

## Current task

Stop using live Douyin profile-grid DOM as the primary metadata source. Refactor extension capture so profile grid discovers items only, then metadata is hydrated per exact `aweme_id`.

## Scope guardrails

- Extension capture pipeline only unless a minimal consumer adjustment is strictly required.
- No UI redesign.
- No backend/frontend broad rewrite.
- No full crawler.
- No fake metadata.
- No broad grid selector patching as the primary strategy.

## Audit summary

Previous `extractVideos()` mixed discovery and metadata extraction:

- discovery: `collectVideoLinks()` and `videoIdFromUrl(link.href)`
- grid metadata: `nearestCard()`, `cardText()`, `titleFromCard()`, `thumbnailFromCard()`, `extractDuration()`, `extractPosted()`, `extractMetrics()`
- final assembly: `mergeDomAndNetworkVideo()` in the content-script path, inline object creation in direct execute-script fallback

The network cache already provides exact `aweme_id` metadata through `NetworkVideoMetadata`, including title, thumbnail/cover URLs, duration, posted timestamp, stats, and share URL.

## Implemented

1. Added discovery-only records keyed by exact `aweme_id`.
2. Moved item-local DOM extraction into explicit fallback snapshot creation.
3. Added exact-id hydrate buckets:
   - network JSON primary
   - detail hydrate secondary
   - DOM fallback tertiary
4. Build final `VideoPayload` only after hydrate resolution.
5. Added safeguards against shared metadata bundles and shared object references.
6. Mirrored the split architecture in the direct execute-script fallback.
7. Added focused tests proving discovery-only behavior, network-primary metadata binding, detail hydrate fallback, and no grid DOM fan-out for three distinct IDs.

## Changed files

- `apps/extension-douyin-capture/src/extractor.ts`
- `apps/extension-douyin-capture/src/popupTransport.ts`
- `apps/extension-douyin-capture/src/types.ts`
- `apps/extension-douyin-capture/src/extractor.identity.test.ts`
- `apps/extension-douyin-capture/src/extractor.test.ts`
- `docs/douyin-grid-discovery-hydrate-architecture.md`
- `docs/douyin-grid-discovery-hydrate-log.md`
- `docs/douyin-grid-discovery-hydrate-resume.md`

## Verification completed

Passed:

```cmd
npx --workspace apps/extension-douyin-capture tsx src/extractor.identity.test.ts
npx --workspace apps/extension-douyin-capture tsx src/extractor.test.ts
npx --workspace apps/extension-douyin-capture tsx src/popupTransport.test.ts
npm --workspace apps/extension-douyin-capture run typecheck
npm --workspace apps/extension-douyin-capture test
```

## Resume state

Task complete. The extension capture path now treats grid DOM as discovery plus last-resort fallback, while canonical metadata is bound per exact `aweme_id` with network JSON first and detail hydrate second.
