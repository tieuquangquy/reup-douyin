# Phase 22F-1G Review Board Metadata Contract

Phase 22F-1G locks the metadata contract between Capture Inbox snapshots, the backend candidate API, and the Review Board card/inspector.

## Contract Flow Audit

- Capture Inbox source model/schema: `apps/api/src/models/capture_inbox.py` stores `CapturedItem.metadata_json`, `raw_payload_json`, `posted_at`, `duration_seconds`, `thumbnail_url`, `source_url`, `profile_url`, and promotion ids.
- Capture Inbox card semantics: `apps/web/src/lib/captureInboxCanonical.ts` resolves visible posted/duration/views/thumbnail values; exact posted display is mirrored by `getCaptureInboxPostedDisplayExact` in `apps/api/src/services/capture_inbox_service.py`.
- Promote path: `CaptureInboxService.promote`, `_mark_item_promoted_to_review_board`, `buildCaptureInboxSourceMetadataSnapshot`, and `mapCaptureInboxItemToReviewCandidateMetadata` snapshot Capture Inbox metadata into `source_metadata`.
- Candidate DB model/schema: `apps/api/src/models/review.py` stores candidate status, internal candidate `score`, and candidate `metadata_json`; review decisions/status/notes must not be overwritten by hydration/backfill.
- Candidate API: `apps/api/src/api/routes/candidates.py` returns `CandidateDetailResponse` for normal `GET /candidates`; debug hydration semantics are exposed in `review_board_api_debug`, `review_board_hydration_summary`, and each candidate's `review_candidate_debug`.
- Candidate serializer: `apps/api/src/schemas/candidates.py` flattens canonical `source_metadata` fields into response fields while preserving `candidate.score` as an internal field only.
- Backfill path: `scripts/backfill_review_board_candidates_from_capture_inbox.py` calls `CandidateEvaluationService.hydrateReviewCandidateFromCaptureItem` in dry-run by default and only writes with `--apply`.
- Frontend adapter/UI: `apps/web/src/lib/reviewCandidateMetadata.ts` resolves Review Board metadata; `apps/web/src/components/review-board/ReviewBoardPage.tsx` renders visible score through `reviewCandidateDisplayScore(candidate)` and renders posted display verbatim.

## Locked Fields

The protected contract fields are:

```json
{
  "reup_score": "visible Review Board score; never candidate.score",
  "estimated_views_display": "preferred visible estimated views text",
  "estimated_views_min": "range fallback lower bound",
  "estimated_views_max": "range fallback upper bound",
  "estimated_views_mid": "sort/fallback midpoint",
  "duration_text": "preferred visible duration",
  "duration_seconds": "duration fallback/source",
  "posted_display": "visible posted string copied from Capture Inbox semantics",
  "posted_at": "raw timestamp/provenance; not date-only display fallback when display exists",
  "thumbnail_url": "Review Board preview image",
  "like_count": "source metric; explicit 0 preserved, missing stays null",
  "comment_count": "source metric; explicit 0 preserved, missing stays null",
  "share_count": "source metric; explicit 0 preserved, missing stays null",
  "caption/title": "visible text identity",
  "source_url/video_url": "source video reference",
  "profile_url": "source profile reference",
  "aweme_id": "Douyin item identity",
  "capture_item_id/source_capture_item_id": "Capture Inbox identity/linkage",
  "review_status": "review status metadata; must be preserved",
  "decision_status": "decision metadata; must be preserved",
  "notes": "operator notes metadata; must be preserved"
}
```

## Display Rules

- Review Board visible score uses canonical `reup_score` only.
- Internal `candidate.score` is retained for diagnostics/filter history but must not render as Reup Score.
- Missing score renders `Unscored`, not `0`.
- Missing estimated views render `—`, not `0`.
- If `estimated_views_display` exists, frontend shows it exactly.
- If `estimated_views_display` is missing but min/max exist, frontend may render the real min/max range.
- Missing/null metrics stay null and must not become fake `0`; explicit captured zero remains zero.
- Normal `GET /candidates` and debug hydration metadata must have the same field semantics.
- Promote/backfill/hydration must not overwrite review status, decisions, notes, approved/rejected state, or create duplicate candidates.

## Regression Fixtures

- Full fish sample: `183珊瑚礁拥有自己的生态链`, `reup_score=42`, estimated views `3.7K-18.3K`, metrics `183/12/13`, posted `23:00:00 28/3/2026`, duration `13:37`.
- Legacy nested metadata: canonical fields may live under source video `metadata_json.source_metadata` and must normalize into the same API/frontend semantics.
- Truly missing metadata: score/views/metrics stay null and render as `Unscored`/`—`, never fake zero.

## Manual QA Checklist

1. Promote a Capture Inbox item with score/views/duration/posted/metrics and confirm Review Board immediately shows the same values.
2. Refresh the browser and confirm score remains the Capture Inbox `reup_score`, not internal `candidate.score`.
3. Restart backend and frontend, clear `.next`, reload Review Board, and confirm metadata is unchanged.
4. Call normal `GET /candidates` and compare candidate fields to `review_candidate_debug`; score/views/metrics/posting semantics must match.
5. Run `python scripts/check_review_board_metadata_contract.py --limit 200`; it must exit 0 with no violations.
6. Run `python scripts/backfill_review_board_candidates_from_capture_inbox.py` first as dry-run; verify it reports planned updates without committing.
7. If applying backfill, run with `--apply`, then repeat the smoke check and confirm approved/rejected statuses, decisions, and notes are preserved.
8. Inspect a candidate with no score/views and confirm visible score is `Unscored`, estimated views is `—`, and no missing metric appears as fake `0`.

## Validation Commands

```bash
cd apps/api && python -m unittest tests.test_phase22f_review_candidate_contract
cd apps/api && python -m compileall src
npm --workspace @reup-douyin/web run test -- review-candidate-metadata
npm --workspace @reup-douyin/web run test -- review-board
npm --workspace @reup-douyin/web run typecheck
python scripts/check_review_board_metadata_contract.py --limit 200
```
