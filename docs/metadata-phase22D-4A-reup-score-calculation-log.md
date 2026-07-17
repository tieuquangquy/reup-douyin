# Phase 22D-4A Reup Score Calculation Log

## Audit
- Normalized Capture Inbox metadata is exposed by `apps/api/src/schemas/capture_inbox.py` and hydrated from backend metadata/raw payload fields.
- Backend engagement is calculated in `apps/api/src/services/douyin_metadata_normalization.py` as likes + comments + shares + favorites, with rate based on `estimated_views_mid` first and `view_count` second.
- Frontend normalization/fallback metadata lives in `apps/web/src/lib/captureInboxFilterMetadata.ts`, including estimated views fallbacks and metadata health flags.
- Tile Gallery cards and right inspector live in `apps/web/src/components/capture-inbox/CaptureInboxPage.tsx` via `MediaTileGallery`, `MediaTile`, and `RightInspector`.
- Sort options and `compareItems` live in `apps/web/src/components/capture-inbox/CaptureInboxPage.tsx`.

## Calculation Location
- Added frontend shared helper `apps/web/src/lib/captureInboxReupScore.ts`.
- The helper uses backend score fields when a complete backend score object is present.
- If backend score fields are missing, it calculates a frontend fallback from normalized item metadata.
- Backend was not modified in this phase to avoid save endpoint or persistence changes.

## Formula
- Score range is clamped and rounded from 0 to 100.
- Components:
  - Performance: 0-25 from estimated views midpoint.
  - Engagement: 0-25 from engagement rate, falling back to engagement score.
  - Shareability: 0-15 from share count.
  - Duration fit: 0-15 for review-friendly durations.
  - Recency: 0-10 from posted date age.
  - Metadata quality: 0-10 from missing metadata count.
  - Penalty: negative, clamped to -30.

## Penalties
- Missing thumbnail: -8.
- Missing duration: -5.
- Missing posted: -4.
- Missing all metrics: -10.
- Duplicate: -20.
- Failed item: -20.
- `metadata_status` failed: -20.
- Needs action statuses: -8.
- Estimated views missing: -5.

## UI
- Tile Gallery cards now show a compact Reup Score pill near the existing overlay status controls.
- Right inspector now includes Reup Score details with score, components, penalty, and reasons.
- Added `Highest Reup Score` sort with fallback to engagement score and recently captured time.

## Tests
- Added helper assertions in `apps/web/src/test/capture-inbox-filter-metadata.test.ts`.
- Added source-inspection assertions in `apps/web/src/test/capture-inbox.test.ts`.
