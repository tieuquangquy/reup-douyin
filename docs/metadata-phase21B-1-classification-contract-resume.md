# Phase 21B-1 Classification Contract Resume

## Completed scope

Implemented the backend-only Douyin profile video classification contract for Phase 21B-1.

## Endpoint path

- `POST /douyin-extension/profile-video-classification`

## Request schema

- `schema_version: douyin_profile_video_classification.v1`
- `profile_url`
- optional `sec_uid`
- `collection_mode`
- `candidates`
- `include_unknown`
- `dry_run`

## Response schema

- `schema_version: douyin_profile_video_classification_result.v1`
- `database_lookup_status`
- `total_candidates`
- `counts`
- `targets`
- `collect_aweme_ids`
- `skip_aweme_ids`
- `diagnostics`

## Classification rules

The pure helper classifies candidates as `new`, `incomplete`, `complete`, `failed`, `skipped`, or `unknown`. Required complete metadata is duration plus like/comment/favorite/share counts. Posted text/date and view count are not required for complete in this phase.

## Collection mode behavior

Default `new_incomplete_failed` collects `new`, `incomplete`, and `failed`. `refresh_all` also collects `complete`. `skipped` stays skipped. `unknown` follows `include_unknown`, except `failed_only` skips unknown.

## Read-only and DB status

The endpoint is read-only and returns `database_lookup_status: not_implemented_contract_only`. It uses an empty existing index and does not create or mutate capture inbox items, scan sessions, source videos, or database rows.

## Files touched

- `apps/api/src/schemas/douyin_extension.py`
- `apps/api/src/services/douyin_profile_classification_service.py`
- `apps/api/src/api/routes/douyin_extension.py`
- `apps/api/tests/test_douyin_profile_video_classification.py`
- `docs/metadata-phase21B-1-classification-contract-log.md`
- `docs/metadata-phase21B-1-classification-contract-resume.md`

## Next phase

`21B-2 — connect classification endpoint to real database records.`
