# Phase 22D-6A Promote to Review Board Hardening Log

## Existing Promote Flow Audit

1. Individual Promote frontend path: `CaptureInboxPage.tsx` builds `contextualActions(item)`, renders `MediaTile` -> `TileActionGrid`, and calls `runAction("promote_now", [item.id])` through `runCaptureInboxAction`.
2. Bulk Promote frontend path: selected visible items flow through `BatchActionBar` -> `BulkActionConfirmationDialog` -> `confirmBulkAction()`, which maps bulk `promote` to the existing `promote_now` action and calls the same `runAction()` path.
3. Backend endpoint: `POST /capture-inbox/sessions/{capture_session_id}/actions` in `apps/api/src/api/routes/capture_inbox.py`.
4. Service function: `CaptureInboxService.promote(...)` in `apps/api/src/services/capture_inbox_service.py`.
5. Review Board table/model/entity: `VideoCandidate` (`video_candidates`) in `apps/api/src/models/review.py`; candidates point at canonical `SourceVideo` rows.
6. Existing Review Board creation path: promotion reuses `SourceIngestService.ingest_profile()` and `CandidateEvaluationService.apply()` instead of creating a separate Review Board handoff.
7. Existing duplicate prevention: `SourceVideo` is unique by `(source_platform, source_video_external_id)` and `VideoCandidate.source_video_id` is unique.
8. Capture Inbox status marker: `CapturedItem.status = PROMOTED`, `promoted_source_video_id`, `promoted_video_candidate_id`, `promoted_crawl_session_id`, and `metadata_json` diagnostics.
9. Current failure cases before hardening: no explicit skipped/failed response fields, frontend/backend promote eligibility drift, duplicate candidates could be structurally prevented but not reported as per-item skips, and promoted-at/review-board diagnostics were incomplete.

## Handoff Contract

Promotion now preserves available identity, content, performance, and status metadata in the adapter payload used by canonical ingest:

- Identity: `capture_item_id`, `capture_session_id`, `aweme_id`, `source_video_external_id`, `source_url`, `video_url`, `profile_url`.
- Content: `caption`, `title`, `thumbnail_url`, `duration_text`, `duration_seconds`, `posted_at`, `posted_display`.
- Performance: `estimated_views_display`, `estimated_views_mid`, `like_count`, `comment_count`, `share_count`, `favorite_count`, `engagement_score`, `engagement_rate`, `reup_score`, `reup_score_level`.
- Status/source: `review_board_status = pending_review`, `source = douyin_capture_inbox`, plus session-level `promotion_model = capture_inbox_to_canonical_review`.

Older items are not required to have every optional metric, but hard eligibility requires enough review metadata to avoid blank Review Board entries.

## Duplicate Prevention Behavior

- Existing `SourceVideo` is detected by `promoted_source_video_id`, `existing_source_video_id`, `source_video_external_id`/aweme ID, and `source_url`/`share_url`.
- Existing `VideoCandidate` for that `SourceVideo` is treated as an existing Review Board entry.
- Duplicate promotions are not re-ingested and are returned as skipped with reason `already_promoted`.
- Safe duplicate sync marks the Capture Inbox item as promoted and stores the existing `review_board_item_id`.

## Eligibility Rules

Individual and bulk promote share the same backend service rules. Promotable items must:

- Not be `PROMOTED`, `FAILED`, `EXCLUDED`, or `DUPLICATE`.
- Have status `READY`, `ENRICHED`, or `PREVIEW_MISSING`.
- Have source identity via `source_url`, `share_url`, or aweme/source external ID.
- Have a thumbnail from the item or raw payload.
- Have caption/title/description metadata.

Ineligible items are skipped per item with reason `already_promoted`, `status_failed`, `status_excluded`, `status_duplicate`, `not_ready`, or `missing_metadata`.

## Bulk Promote Behavior

Bulk Promote still sends selected item IDs to the existing `promote_now` endpoint. The backend validates each item, promotes eligible rows, skips ineligible rows with reasons, prevents duplicate Review Board entries, and returns:

```json
{
  "promoted_item_ids": [],
  "skipped": [{ "item_id": "...", "reason": "..." }],
  "failed": [{ "item_id": "...", "reason": "..." }]
}
```

The API uses `affected_item_ids` for promoted/synced item IDs and exposes `skipped`/`failed` arrays. The frontend uses backend promote messages for Bulk Promote summaries, refreshes the Capture Inbox list, and clears selection after bulk completion.

## Status Sync Behavior

Successful promotion stores:

- `CapturedItem.status = PROMOTED`
- `promoted_source_video_id`
- `promoted_video_candidate_id`
- `promoted_crawl_session_id`
- `metadata_json.review_status = promoted`
- `metadata_json.promoted_at`
- `metadata_json.promoted_to_review_board_id`
- `metadata_json.review_board_handoff_verified`
- `metadata_json.review_board_item_id`
- `metadata_json.review_board_duplicate_detected`

## Tests Run

- `python -m unittest tests.test_douyin_extension_capture_service tests.test_capture_inbox_metadata_status` passed.
- `python -m compileall src scripts` passed.
- `npm --workspace @reup-douyin/web run typecheck` passed.
- `npm --workspace @reup-douyin/web run build` passed.
- `npx tsx apps/web/src/test/capture-inbox.test.ts && npx tsx apps/web/src/test/capture-inbox-canonical.test.ts && npx tsx apps/web/src/test/capture-inbox-filter-metadata.test.ts` passed.
- `npm --workspace @reup-douyin/web run test` still fails before Capture Inbox tests on the pre-existing Windows duplicated path issue: `apps\web\apps\web\src\components\review-board\ReviewBoardPage.tsx`.

## Remaining Limitations

- First-class DB columns named `promoted_at`, `review_status`, and `promoted_to_review_board_id` do not exist; Phase 22D-6A stores those values in `metadata_json` to avoid a migration outside the hardening scope.
- Duplicate detection by `capture_item_id` is represented through the Capture Inbox row itself and persisted promoted foreign keys; canonical tables do not currently store `capture_item_id` as a unique DB column.
