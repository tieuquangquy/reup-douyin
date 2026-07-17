# Douyin Grid Discovery Hydrate Architecture

## Decision

The extension capture pipeline must stop treating live Douyin profile-grid DOM as the primary metadata source. The grid is now trusted only for item discovery: `aweme_id`, source URL, optional safe share URL, and visible order.

Final item metadata must be assembled per `aweme_id` after deterministic hydration:

1. exact network JSON match for the same `aweme_id`,
2. narrow item-level detail/share hydrate for the same `aweme_id` when available,
3. item-local DOM fallback only for fields still missing.

## Why grid DOM is no longer primary metadata truth

The profile grid can expose duplicated or shared title, thumbnail, posted, and stats text across distinct visible video links. Even item-local selector fixes do not make the live profile grid a reliable source of canonical item metadata. Grid DOM is still useful to discover which videos are visible and in what order, but it must not be authoritative for thumbnail, title, posted, views, likes, or comments.

## Pipeline

### 1. Grid discovery only

Visible grid discovery scans `a[href*="/video/"]` links and creates lightweight records:

- `aweme_id`
- `source_url`
- `share_url` when it can be safely derived from the exact video link
- `visible_order`
- local card/text fallback diagnostics only, not primary metadata

Discovery is keyed by exact `aweme_id`. Links without a resolvable `aweme_id` are skipped instead of guessed.

### 2. Per-aweme hydrate

For each discovered item, metadata is resolved independently by exact `aweme_id`.

#### Priority 1: network JSON

The existing network cache already normalizes Douyin JSON records into per-aweme records with:

- title/desc
- thumbnail and cover URLs
- duration
- posted timestamp
- view/like/comment counts
- share URL

Only exact `aweme_id` matches are eligible. Network JSON overrides any grid-derived fallback field.

#### Priority 2: narrow detail hydrate

A detail hydrate record is also keyed by exact `aweme_id`. In this narrow implementation, detail hydrate is represented as an optional `NetworkVideoMetadata` source with `raw_source` such as `detail_hydrate`. This keeps the extension boundary deterministic without introducing a crawler or broad page traversal.

Future browser detail/share-page collection can feed the same exact-id hydrate list without changing final assembly.

#### Priority 3: item-local DOM fallback

DOM fallback remains only as a last resort and only from the exact discovered link/card. If network and detail hydrate lack a field, the fallback may provide missing title/thumbnail/posted/stats. If fallback is unavailable or unsafe, the field remains missing honestly.

## Canonical payload assembly

Final `VideoPayload` records are built only after discovery and hydrate are separated. Each payload is constructed independently from:

- one discovery record,
- optional exact-id network metadata,
- optional exact-id detail metadata,
- optional exact-id DOM fallback metadata.

No shared mutable metadata object may be reused across multiple `aweme_id` values. Arrays such as `url_list` are cloned per final item.

## Anti-corruption safeguards

- Exact `aweme_id` match is required for network/detail metadata.
- Network metadata overrides grid-derived fields when present.
- Detail hydrate fills only fields still missing after network metadata.
- DOM fallback fills only remaining missing fields and is marked as fallback provenance.
- Grid-only duplicated metadata bundles are not treated as authoritative.
- Failed hydrate leaves missing fields missing instead of copying another item's metadata.

## Non-goals

- No UI redesign.
- No backend/frontend rewrite.
- No full crawler.
- No broad page/detail traversal.
- No fake metadata generation.
