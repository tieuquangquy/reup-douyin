# Phase 21B-2 — Classification DB Lookup Log

## Scope

Phase 21B-2 connects `POST /douyin-extension/profile-video-classification` to existing backend persistence records while keeping the endpoint read-only.

## Existing models inspected

- `CapturedItem` in `apps/api/src/models/capture_inbox.py` stores Capture Inbox rows.
- `SourceVideo` in `apps/api/src/models/ingestion.py` stores canonical source videos.
- Both domains use `source_video_external_id` as the Douyin video identity that corresponds to a candidate `aweme_id`.

## Lookup behavior

The endpoint now extracts unique non-empty candidate `aweme_id` values and queries existing Douyin records by `source_video_external_id` from:

1. `captured_items`
2. `source_videos`

The lookup does not create sessions, items, source videos, or review records. It performs only SQLAlchemy `select(...)` queries.

## Classification mapping

`map_capture_inbox_item_to_classification_record(...)` maps existing Capture Inbox rows into the pure classification helper record format. Direct columns provide identity, URL, caption, duration, thumbnail, and timestamps. `metadata_json` provides `duration_text`, engagement counts, and optional status fields.

`map_source_video_to_classification_record(...)` maps canonical `SourceVideo` rows using direct columns and `metadata_json`.

## Duplicate record policy

If more than one existing record matches an `aweme_id`, the service prefers records in this order:

1. Complete records.
2. Failed records.
3. Incomplete records.
4. Skipped records.
5. Matching profile URL when available.
6. Capture Inbox records over canonical records as a tie-breaker.
7. Newer timestamp as a final tie-breaker.

## Endpoint diagnostics

Successful lookup responses include:

```json
{
  "contract_only": false,
  "db_lookup_enabled": true,
  "lookup_candidate_count": 57,
  "existing_match_count": 44,
  "duplicate_candidate_count": 0,
  "invalid_candidate_count": 0,
  "profile_scope": "profile_url",
  "read_only": true
}
```

## Failure behavior

Lookup failures return HTTP 500 with:

```json
{"code": "profile_video_classification_lookup_failed"}
```

The endpoint intentionally does not silently classify every candidate as `new` when database lookup fails.
