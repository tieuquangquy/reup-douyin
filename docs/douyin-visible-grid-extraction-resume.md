# Douyin Visible Grid Extraction Resume

## Current objective

Hard-fix the extension-side visible Douyin profile-grid extraction path so each visible card can produce stable normalized metadata before backend/frontend follow-up work.

## Scope for this part

Allowed:

- `apps/extension-douyin-capture`
- extension extraction tests
- docs for the extraction path

Not allowed in this part:

- Capture Inbox UI redesign
- backend/API/frontend polish
- full crawler
- media download pipeline
- fabricated metadata

## Audit summary

Read and audited:

- `AGENTS.md`
- `apps/extension-douyin-capture/public/manifest.json`
- `apps/extension-douyin-capture/src/types.ts`
- `apps/extension-douyin-capture/src/contentScript.ts`
- `apps/extension-douyin-capture/src/background.ts`
- `apps/extension-douyin-capture/src/popup.ts`
- `apps/extension-douyin-capture/src/popupTransport.ts`
- `apps/extension-douyin-capture/src/extractor.ts`
- `apps/extension-douyin-capture/src/extractor.test.ts`

Key findings:

1. Current visible card detection uses `/video/` anchors and scored ancestors.
2. Current thumbnail extraction is DOM-only and broad, but does not expose a single winning source type or normalize emitted URLs strongly enough.
3. Current metadata extraction is DOM-only and can miss compact/icon grid overlays.
4. The extension does not currently observe page network JSON at all.
5. There is no page-side aweme cache to prefer exact network metadata over DOM fallback.
6. There is no minimal retry/read-after-render step for lazy-loaded card poster attributes.
7. Existing diagnostics are aggregate only and do not provide a representative safe debug item.

## Files expected to change

- `apps/extension-douyin-capture/src/types.ts`
- `apps/extension-douyin-capture/src/extractor.ts`
- `apps/extension-douyin-capture/src/contentScript.ts`
- `apps/extension-douyin-capture/src/popupTransport.ts`
- `apps/extension-douyin-capture/src/extractor.test.ts`
- `docs/douyin-visible-grid-extraction-log.md`
- `docs/douyin-visible-grid-extraction-resume.md`
- `docs/douyin-visible-grid-extraction-architecture.md`

## Completed implementation

1. Implemented network JSON hook/cache and content-script bridge.
2. Implemented explicit-priority thumbnail helper with URL normalization and winning source diagnostics.
3. Improved DOM metadata extraction by preserving visible duration, posted, and raw metric text while allowing network exact values to win where available.
4. Merged network cache values over DOM fallback in normalized extension video output.
5. Added safe debug logging and aggregate diagnostics for thumbnail, metadata, and network match coverage.
6. Updated focused extension tests, including network normalizer coverage and Node-safe source-level invariants for extraction/merge behavior.
7. Ran extension verification successfully.
8. Updated docs with final results.

## Verification result

- Passed: `npm run test --workspace apps/extension-douyin-capture`
- Covered by that command: extractor tests, popup action tests, popup transport tests, TypeScript build, static asset copy, and dist module resolution checks.

## Remaining follow-up outside Part 1

- Validate on a live Douyin profile page with the browser extension loaded and inspect safe console diagnostics for thumbnail/source coverage.
- Backend/frontend follow-up may consume the richer extension fields, but this part intentionally did not redesign Capture Inbox or add crawler/media-download behavior.
