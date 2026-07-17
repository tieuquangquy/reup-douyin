# Phase 21B-2 — Classification DB Lookup Resume

## Completed scope

Phase 21B-2 connected the profile-video classification endpoint to existing read-only Capture Inbox and canonical video records.

## Files changed

- `apps/api/src/services/douyin_profile_classification_service.py`
- `apps/api/src/api/routes/douyin_extension.py`
- `apps/api/tests/test_douyin_profile_video_classification.py`
- `apps/api/tests/test_douyin_profile_video_classification_db_lookup.py`
- `docs/metadata-phase21B-2-classification-db-lookup-log.md`
- `docs/metadata-phase21B-2-classification-db-lookup-resume.md`

## Canonical key

Candidate `aweme_id` maps to stored `source_video_external_id`.

The lookup reads both:

- `CapturedItem.source_video_external_id`
- `SourceVideo.source_video_external_id`

## Endpoint state

`POST /douyin-extension/profile-video-classification` now:

1. Injects a SQLAlchemy database session.
2. Looks up existing Douyin records by candidate `aweme_id`.
3. Maps rows into classification records.
4. Calls the pure `classify_douyin_profile_candidates(...)` helper.
5. Returns `database_lookup_status = "ok"` when lookup succeeds.
6. Returns HTTP 500 with `profile_video_classification_lookup_failed` when lookup fails.

## Read-only guarantee

The service uses `select(...)` and `db.scalars(...)` only. It does not call `add`, `flush`, `commit`, `delete`, or mutation services in the classification path.

## Follow-up notes

No schema migration was required. No Capture Inbox UI, extension runner, extension popup, V2/legacy runtime, or review route was changed.
