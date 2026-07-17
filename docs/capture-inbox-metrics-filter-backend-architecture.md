# Capture Inbox Metrics + Filter Backend Architecture

## Problem
Capture Inbox currently exposes staged item metrics but list querying is limited to session/status pagination. The advanced filter panel requires backend filtering with schema parity to `/intake`.

## Canonical Schema Strategy

### Source of truth
- `/intake` filter source model: [`FilterConfigRequest`](apps/api/src/schemas/candidates.py:10), used in [`IntakeDiscoverRequest`](apps/api/src/schemas/intake.py:17).

### Capture Inbox alignment approach
- Introduce a Capture Inbox query schema derived from intake filter semantics with explicit mapping:
  - `from_date` -> `start_date`
  - `to_date` -> `end_date`
  - `speech` -> `has_speech`
  - `exclude_high_complexity` -> `exclude_high_processing_complexity`
- Keep all required requested fields available in Capture Inbox query contract:
  - from/to date
  - min/max views/likes/comments/shares/engagement/duration
  - speech
  - max_text_density
  - exclude_heavy_watermark
  - exclude_high_complexity
  - exclude_high_copyright_risk

## Backend Filtering Flow
1. Route receives scoped query request for one capture session.
2. Service loads base `CapturedItem` query under session scope and optional status/search.
3. Advanced filter adapter applies deterministic SQL/JSON filters against staged item canonical fields:
   - `posted_at` / metadata fallback for date
   - metrics from `metadata_json` numeric canonical keys
   - duration from column
   - content-signal flags from `metadata_json` where available
4. Missing metric/signal values are handled null-safe:
   - no crashes
   - deterministic exclusion only when threshold requires unavailable data.
5. Return filtered list + total count; no mutation/deletion of staged items.

## Metrics Response Exposure
- Continue exposing in [`CapturedItemResponse`](apps/api/src/schemas/capture_inbox.py:24):
  - `view_count`, `like_count`, `comment_count`, `share_count`, `engagement_rate`
- Preserve intake evaluation fields for tab/filter consistency.

## Service Boundary
- Add narrow helper/service in `apps/api` dedicated to Capture Inbox filter query composition (testable, deterministic, no UI concerns).

## Verification Targets
- API contract supports advanced filter payload.
- Result subsets match expected boundaries.
- Session scope safety preserved.
- Null/missing metrics do not crash.
- Raw staged items remain stored regardless of filtered visibility.
