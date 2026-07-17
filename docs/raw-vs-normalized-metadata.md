# Raw Vs Normalized Metadata

The ingest layer keeps raw payloads and normalized canonical fields separate.

## Raw Payload

Raw payloads are stored for debugging, audit, and parser evolution:

- `source_profiles.raw_payload_json`
- `source_videos.raw_payload_json`
- `video_metric_snapshots.raw_payload_json`
- `crawl_sessions.raw_payload_json`

Business logic should not depend on raw payload shape. Douyin may change field names or nesting without notice.

## Normalized Fields

Canonical downstream fields live on typed columns:

- `source_profiles.source_platform`
- `source_profiles.source_profile_external_id`
- `source_profiles.profile_url`
- `source_profiles.display_name`
- `source_profiles.handle`
- `source_videos.source_video_external_id`
- `source_videos.source_url`
- `source_videos.caption`
- `source_videos.posted_at`
- `source_videos.duration_seconds`
- `video_metric_snapshots.view_count`
- `video_metric_snapshots.like_count`
- `video_metric_snapshots.comment_count`
- `video_metric_snapshots.share_count`
- `video_metric_snapshots.favorite_count`

Flexible but normalized metadata, such as hashtags, thumbnail URL, raw visibility, and adapter notes, is stored in `metadata_json`.

## Fields That May Be Missing

Douyin payloads may omit or change:

- exact posted time
- duration
- thumbnail URL
- metric counts
- hashtag shape
- visibility/status fields
- stable handle values

These fields are nullable by design. Downstream filtering and scoring must handle missing values explicitly.

## Rule For Future Code

Use normalized tables for product behavior. Use raw payloads only for debugging, adapter tests, and parser migrations.

