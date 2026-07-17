# Douyin Serial Factor Fix Architecture

## Purpose

This document records the factor-by-factor repair architecture for the Douyin capture pipeline. The workflow is intentionally serial and verification-gated.

## Pipeline Boundaries

1. Extension DOM extraction identifies visible cards and parses `aweme_id` from video hrefs.
2. Extension network observation normalizes Douyin JSON into item metadata keyed by `aweme_id`.
3. Extension merge creates canonical video payloads.
4. API schemas validate accepted fields.
5. Backend staging persists canonical fields and per-item metadata.
6. API responses expose canonical fields to the web app.
7. Frontend renders canonical fields with stable item identity.

## Factor Gates

### Factor 1 — Identity / aweme_id Mapping

Allowed architecture:

- canonical item store keyed by `aweme_id`;
- DOM/network merge only when both sides have the same non-empty `aweme_id`;
- no merge by position, list index, title, profile URL, source URL alone, share URL alone, thumbnail URL, or object position;
- no reused mutable network object across different IDs;
- suspicious duplicate identity payload diagnostics.

Factor 1 status: passed. Behavioral verification now proves three distinct visible DOM IDs do not receive metadata by network list order, missing ID, mismatched ID, or shared `url_list` object reference.

### Factor 2 — Thumbnail Extraction and Binding

Allowed architecture:

- network JSON thumbnail candidates are normalized per network item and keyed by `aweme_id`;
- DOM thumbnail candidates are extracted from the visible card/link for that same DOM `aweme_id`;
- merge order is matching network thumbnail first, same-item DOM fallback second, then `null`;
- no thumbnail merge by position, title, profile URL, source URL alone, thumbnail URL, or shared object position;
- backend and frontend may resolve aliases, but only from the same captured item payload/record.

Factor 2 status: passed. Behavioral verification now proves three distinct visible DOM IDs receive distinct matching network thumbnails, a fourth same-ID item uses DOM fallback when matched network metadata has no thumbnail, and unmatched/missing-ID network thumbnails do not fan out.

### Factor 3 — Duration + Posted

Allowed architecture:

- network duration and posted values are normalized per network item and keyed by `aweme_id`;
- DOM duration and posted candidates are extracted from the visible card/link for that same DOM `aweme_id`;
- merge order is matching network duration/posted first, same-item DOM fallback second, then `null`;
- default midnight network posted timestamps are rejected before fallback;
- no duration or posted merge by position, title, profile URL, source URL alone, shared object position, or placeholder timestamp.

Factor 3 status: passed. Behavioral verification now proves distinct visible DOM IDs receive distinct matching network duration/posted values, default midnight posted timestamps fall back to DOM text, a fourth same-ID item uses DOM fallback when matched network metadata lacks duration/posted values, and unmatched/missing-ID network duration/posted values do not fan out.

### Factor 4 — Views / Likes / Comments

Allowed architecture:

- network JSON view, like, and comment counts are normalized per network item and keyed by `aweme_id`;
- DOM metric candidates are extracted from the visible card/link text for that same DOM `aweme_id`;
- merge order is matching network stats first, same-item DOM metric fallback second, then `null`;
- top-level canonical count fields and nested `statistics` count fields must agree for view, like, and comment counts;
- no stats merge by position, title, profile URL, source URL alone, shared object position, or missing network identity;
- backend and frontend may resolve stats aliases, but only from the same captured item payload/record.

Factor 4 status: passed. Behavioral verification now proves distinct visible DOM IDs receive distinct matching network view/like/comment counts, a fourth same-ID item uses DOM metric fallback when matched network metadata has no stats, nested `statistics` remains consistent with canonical fields, and unmatched/missing-ID network stats do not fan out.

### Factor 5 — Preview / Source Link / Media Asset Statuses

Allowed architecture:

- preview status is derived from true thumbnail/preview image evidence, not from requested status alone;
- source-link status is derived from true source/share URL evidence, not from requested status alone;
- media asset status is separate from preview/source-link capture status and must not become `ready` during extension capture unless real generated media asset evidence exists;
- legacy `media_status` remains a compatibility projection: `ready` for real ready media assets, `source_link_captured` for source-link-only captures, otherwise `missing`;
- frontend resolvers render preview, source-link, and media-asset states separately without collapsing source-link capture into media readiness.

Factor 5 status: passed. Backend verification now proves requested `ready` statuses are rejected when evidence is absent: preview becomes `missing`, source link becomes `missing`, media asset becomes `not_generated`, and legacy media status becomes `missing`; frontend verification preserves the separate labels.

### Factor 6 — Backend Persistence + API Response Correctness

Allowed architecture:

- backend staging must persist canonical item identity, thumbnail, duration, posted, stats, and separated status fields on the same captured item;
- metadata alias fallback must use explicit presence semantics, so legitimate zero values are preserved instead of treated as missing;
- API response hydration must expose canonical capture inbox fields directly, without making the frontend guess primary values from raw blobs;
- promotion adapter payload projection must preserve canonical zero stats and duration values;
- response serialization must instantiate per-item response models and must not reuse mutable metadata across items.

Factor 6 status: passed. Backend verification now proves zero duration and zero view/like/comment counts persist into `metadata_json`, merged item-local `statistics`, and `CapturedItemResponse` fields; adapter projection now uses explicit presence fallback for stats.

### Factor 7 — Frontend Rendering Correctness and Stale Reuse Prevention

Allowed architecture:

- UI tiles, filters, and inspector panels must render canonical API response fields through item-local resolver calls;
- React gallery tiles must use stable captured item IDs as keys;
- active inspector state must be derived from captured item IDs and reset item-scoped UI state when the active item changes;
- action diagnostic panes must clear previous raw/source details before each new action response;
- metric fallback order must prefer direct canonical response fields, then canonical metadata/raw keys, then legacy alternate aliases;
- frontend must not use cross-item caches or shared mutable metadata to resolve thumbnails, duration, posted text, stats, or statuses.

Factor 7 status: passed. Audit verified stable `key={item.id}` rendering, item-local resolver usage in the gallery and inspector, active item invalidation, and per-action diagnostics clearing. The narrow fix changed nested metric fallback order so canonical raw `statistics.view_count` / `statistics.like_count` win over legacy `play_count` / `digg_count` aliases. Frontend verification now covers zero-value rendering, canonical nested stat precedence, and distinct per-item thumbnail/duration/posted/stats/status rendering.

## Non-Goals

- No crawler implementation.
- No worker/video processing implementation.
- No publishing integration.
- No UI redesign.
- No database schema migration unless a later factor proves it is required.
