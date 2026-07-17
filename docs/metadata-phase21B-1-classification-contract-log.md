# Phase 21B-1 Classification Contract Log

## Endpoint path

- `POST /douyin-extension/profile-video-classification`

## Request schema

Schema version: `douyin_profile_video_classification.v1`

The endpoint accepts a profile URL, optional `sec_uid`, `collection_mode`, candidate videos, `include_unknown`, and `dry_run`. Candidate videos preserve profile-scan evidence such as `aweme_id`, video/source URLs, thumbnail URL, caption, posted text/date, and optional view count.

## Response schema

Schema version: `douyin_profile_video_classification_result.v1`

The response returns `database_lookup_status`, total candidate count, classification counts, target rows, collect/skip aweme ID lists, and diagnostics.

## Classification rules

- Empty or invalid `aweme_id` is classified as `unknown` with reason `invalid_aweme_id`.
- Missing existing record is classified as `new` with reason `not_found_in_existing_index`.
- Existing `metadata_status` of `failed` or `error` is classified as `failed` with reason `previous_collect_failed`.
- Existing `metadata_status` of `skipped` is classified as `skipped` with reason `previously_skipped`.
- Existing records with duration plus like/comment/favorite/share counts are classified as `complete` with reason `already_complete`.
- Existing records missing required detail metadata are classified as `incomplete` with reason `missing_required_metadata`.
- Duplicate candidate `aweme_id` values keep the first target row and increment `duplicate_candidate_count`.

## Collection mode behavior

- `new_incomplete_failed` collects `new`, `incomplete`, and `failed`.
- `new_and_incomplete` is treated as a backward-compatible alias for `new_incomplete_failed`.
- `new_only` collects only `new`.
- `failed_only` collects only `failed`.
- `refresh_all` collects `new`, `incomplete`, `failed`, and `complete`.
- `skipped` remains skipped in all modes for this phase.
- `unknown` is collected only when `include_unknown` is true, except `failed_only` keeps unknown skipped.

## Read-only phase rationale

Phase 21B-1 is contract-only so the extension and backend can agree on the request/response shape before database-backed lookup is connected. The endpoint does not create capture sessions, capture inbox items, source videos, scan sessions, or migrations.

## DB lookup status

The endpoint returns `database_lookup_status: not_implemented_contract_only` and calls the pure helper with an empty existing index. Real database lookup is intentionally deferred to avoid changing persistence behavior in this phase.

## Next phase

`21B-2 — connect classification endpoint to real database records.`
