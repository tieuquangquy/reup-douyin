# Metadata Phase 3 Backend Normalizer Architecture

## Objective

Implement a deterministic backend normalizer for Capture Inbox that converts Phase 2 raw evidence into canonical metadata usable for Time / Performance / Processing-fit decisions.

Normalization inputs per staged item:
- `raw_network_aweme`
- `raw_detail_aweme`
- `raw_dom_snapshot`
- `raw_evidence_summary`
- optional existing canonical fields from payload

Normalization outputs:
- Canonical fields:
  - `posted_at`, `posted_text`
  - `duration_seconds`, `duration_text`
  - `view_count`, `like_count`, `comment_count`, `share_count`, `engagement_rate`
- Source fields:
  - `posted_source`, `duration_source`, `view_count_source`, `like_count_source`, `comment_count_source`, `share_count_source`, `engagement_rate_source`
- Status fields:
  - `metadata_status`, `time_status`, `performance_status`, `processing_fit_status`
- Missing reasons:
  - `metadata_missing_reason`, `time_missing_reason`, `performance_missing_reason`, `processing_fit_missing_reason`

## Placement

New service module in `apps/api`:
- [`CaptureMetadataNormalizer`](../apps/api/src/services/capture_metadata_normalizer.py)

Integration point:
- [`CaptureInboxService._build_item()`](../apps/api/src/services/capture_inbox_service.py:703)

## Deterministic Priority Rules

### Time
1. `raw_network_aweme.create_time`
2. `raw_detail_aweme.create_time`
3. `raw_dom_snapshot.visible_text` only for reliable posted text fallback
4. missing

Rules:
- Parse unix seconds to ISO datetime.
- Reject numeric fragments as posted text (e.g. `13.0`).
- No synthetic/fake timestamps.

### Duration
1. `raw_network_aweme.video.duration`
2. `raw_detail_aweme.video.duration`
3. safe duration-shaped fallback from DOM text
4. missing

Rules:
- Handle milliseconds vs seconds safely.
- Keep `duration_seconds` numeric.
- Derive `duration_text` from seconds when possible.

### Performance
1. `raw_network_aweme.statistics`
2. `raw_detail_aweme.statistics`
3. constrained DOM fallback (count-labeled and item-local only)
4. missing

Map:
- `play_count -> view_count`
- `digg_count -> like_count`
- `comment_count -> comment_count`
- `share_count -> share_count`

Rules:
- counts are non-negative integers.
- reject arbitrary numeric fragments.
- `engagement_rate = (like + comment + share) / view` only when `view > 0` and at least one interaction exists.

## Source Vocabulary

Preferred backend source labels:
- `network_json`
- `detail_hydrate`
- `dom_snapshot`
- `existing_canonical`
- `missing`

Compatibility mapping for existing response schema literals can be applied at API hydration boundary where needed.

## Status Rules

- `time_status`: captured if `posted_at` or reliable `posted_text`, else missing; failed only on hard normalization error.
- `performance_status`: captured if any trustworthy count exists, else missing; failed on normalization error.
- `processing_fit_status`: captured if `duration_seconds` exists, else missing; failed on normalization error.
- `metadata_status`:
  - `complete` if all three groups captured
  - `partial` if mixed captured/missing
  - `missing` if all missing
  - `failed` on hard normalization failure
  - `pending_hydration` reserved when not attempted in legacy rows/workflows

## Missing Reason Vocabulary

Deterministic reason keys:
- `no_network_or_detail_evidence`
- `no_create_time`
- `no_video_duration`
- `no_statistics`
- `invalid_create_time`
- `invalid_duration`
- `invalid_statistics`
- `dom_fallback_not_confident`
- `normalization_error`

## Persistence Plan

In `_build_item`:
1. Read Phase 2 evidence from payload.
2. Run normalizer.
3. Write canonical values to existing columns when available:
   - `posted_at`, `duration_seconds`
4. Write canonical/status/source/reason fields into `metadata_json`.
5. Preserve Phase 2 raw evidence fields in `metadata_json`.

No extension changes. No hydration job changes.

## API Exposure Plan

Expose in `CapturedItemResponse` via hydrated fields from `metadata_json`:
- canonical metadata
- status/source/reason fields
- `raw_evidence_summary` (compact)

Do not elevate full raw aweme blobs to list-level primary fields.
