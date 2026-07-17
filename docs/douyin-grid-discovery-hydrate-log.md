# Douyin Grid Discovery Hydrate Log

## Scope

Architecture correction for extension capture: use the live profile grid for discovery only, then hydrate metadata per exact `aweme_id` with network JSON first, optional detail hydrate second, and item-local DOM fallback last.

Allowed scope:

- `apps/extension-douyin-capture`
- focused capture pipeline tests
- docs for the architecture and resume trail

## Audit before patching

### 1. Where grid discovery previously happened

- `apps/extension-douyin-capture/src/extractor.ts`
  - `extractVideos(document, networkItems)` called `collectVideoLinks(document)`.
  - `collectVideoLinks(document)` scanned `a[href*="/video/"]` and filtered Douyin `/video/{id}` URLs.
- `apps/extension-douyin-capture/src/popupTransport.ts`
  - direct execute-script fallback had a mirrored `extractVideos()` and `collectVideoLinks()`.

### 2. Where grid metadata extraction previously happened

Previous extraction mixed discovery and metadata extraction in the same loop:

- `extractor.ts` `extractVideos()` resolved each link and immediately called:
  - `nearestCard(link)`
  - `cardText(card, link)`
  - `titleFromCard(card, link, text)`
  - `thumbnailFromCard(card, link)`
  - `extractDuration(text)`
  - `extractPosted(text)`
  - `extractMetrics(text)`
- `popupTransport.ts` direct fallback did the same inline work.

### 3. Which fields came directly from grid DOM

Grid DOM previously contributed, when network data was missing:

- `title`
- `desc`
- `thumbnail_url`
- `poster_url`
- `cover_url`
- `url_list`
- `thumbnail_source_type`
- `thumbnail_source_types`
- `duration_text`
- `duration_seconds`
- `posted_text`
- `posted_at`
- `view_count`
- `view_count_text`
- `like_count`
- `like_count_text`
- `comment_count`
- `comment_count_text`
- `statistics.share_count`
- `statistics.favorite_count`

These fields were derived from card text/media inside the same loop that discovered `aweme_id` and URL.

### 4. Where final payload items were assembled

- `extractor.ts` final content-script payload item assembly happened in `mergeDomAndNetworkVideo(input, networkInput)`.
- `popupTransport.ts` final direct fallback payload items were assembled inline inside the mirrored `extractVideos()` loop.

### 5. Whether the network cache already contains enough per-aweme data

Yes for many fields. `networkCache.ts` normalizes exact `aweme_id` records into `NetworkVideoMetadata` containing:

- `title` / `desc`
- `share_url`
- `thumbnail_url`, `cover_url`, `origin_cover`, `dynamic_cover`, `url_list`
- `duration_text`, `duration_seconds`
- `posted_at`
- `view_count`, `like_count`, `comment_count` and text variants
- `raw_source`

Network normalization requires explicit `aweme_id`, which is correct for anti-corruption.

### 6. Minimal detail-hydrate mechanism

No live crawler/detail fetch was added in this task. The narrow mechanism is an optional exact-id detail hydrate metadata list in the same `NetworkVideoMetadata` shape. A detail hydrate record must have the same `aweme_id` and can use `raw_source` such as `detail_hydrate`. It fills only fields still missing after network JSON.

## Implemented split

The mixed capture code is now split into:

1. discovery-only
   - visible link scan
   - exact `aweme_id`
   - `source_url` / safe `share_url`
   - `visible_order`
2. hydrate-by-aweme-id
   - exact network metadata map
   - exact detail hydrate metadata map
   - item-local DOM fallback snapshot
3. final canonical payload build
   - one output object per discovered `aweme_id`
   - exact `aweme_id` checks for network and detail metadata
   - cloned arrays and metadata objects
   - provenance diagnostics

## Files/functions changed

- `apps/extension-douyin-capture/src/extractor.ts`
  - Added `GridDiscoveryRecord`, `DomFallbackMetadata`, and `HydratedItem`.
  - Refactored `extractVideos(document, networkItems, detailHydrateItems)` into discovery, hydrate, and final assembly phases.
  - Added exported `discoverGridVideos(document)` for discovery-only scans.
  - Added `buildDomFallbackMetadata(discovery)` for last-resort item-local DOM fallback.
  - Replaced `mergeDomAndNetworkVideo()` with `buildCanonicalVideoPayload(item)`.
  - Added `exactHydrateForDiscovery()` and `thumbnailFromHydrate()`.
- `apps/extension-douyin-capture/src/popupTransport.ts`
  - Mirrored the direct execute-script fallback structure with nested `discoverGridVideos()`, `buildDomFallbackMetadata()`, and `buildCanonicalVideoPayload()`.
  - Kept direct fallback DOM-only because this path has no network cache input, but made the split explicit and diagnostic-safe.
- `apps/extension-douyin-capture/src/types.ts`
  - Extended `PostedSource` with `detail_hydrate`.
- `apps/extension-douyin-capture/src/extractor.identity.test.ts`
  - Added discovery-only assertions.
  - Added network-primary assertions for three distinct `aweme_id` values.
  - Added exact-id detail hydrate fallback assertions.
- `apps/extension-douyin-capture/src/extractor.test.ts`
  - Updated source-shape assertions from DOM-primary/merge expectations to discovery/hydrate/canonical assembly expectations.
- `docs/douyin-grid-discovery-hydrate-architecture.md`
  - Added architecture decision and pipeline design.
- `docs/douyin-grid-discovery-hydrate-log.md`
  - This implementation and verification log.
- `docs/douyin-grid-discovery-hydrate-resume.md`
  - Updated with completion state.

## Anti-corruption safeguards

- Discovery records do not expose title, thumbnail, or stats as primary metadata.
- Final payload assembly requires exact `aweme_id` matches for network and detail metadata.
- Network JSON wins over detail hydrate and DOM fallback.
- Detail hydrate fills missing fields after network JSON and before DOM fallback.
- DOM metadata remains last-resort and item-local.
- Final diagnostics include:
  - `has_network_metadata`
  - `has_detail_hydrate_metadata`
  - `has_dom_fallback_metadata`
  - `rejected_network_identity_mismatch`
  - `rejected_detail_identity_mismatch`
  - `grid_metadata_primary: false`
- Missing fields remain missing instead of being filled from another item's metadata bundle.

## Tests

Passed:

```cmd
npx --workspace apps/extension-douyin-capture tsx src/extractor.identity.test.ts
npx --workspace apps/extension-douyin-capture tsx src/extractor.test.ts
npx --workspace apps/extension-douyin-capture tsx src/popupTransport.test.ts
npm --workspace apps/extension-douyin-capture run typecheck
npm --workspace apps/extension-douyin-capture test
```

## Verification

Verified by focused tests and full extension test suite:

1. Three distinct `aweme_id` values no longer receive duplicated title/thumbnail from grid DOM when exact network JSON exists.
2. Final payload items are built per discovered `aweme_id` after hydrate resolution.
3. Network JSON is the primary metadata source where available.
4. Detail hydrate fills missing fields only for the exact target `aweme_id`.
5. Grid DOM is discovery plus last-resort fallback, with `grid_metadata_primary: false` diagnostics.
6. Missing fields are preserved as missing values instead of copied from another item.
