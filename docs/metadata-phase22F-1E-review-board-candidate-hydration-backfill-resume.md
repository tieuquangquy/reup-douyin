# Phase 22F-1E Resume

## Scope

Continue Phase 22F-1E only: hydrate/backfill Review Board candidate metadata from Capture Inbox metadata without changing the Review Board UI, Douyin extension crawler, batch collection, or Reup Score formula.

## Implemented

- Backend hydration helper: `CandidateEvaluationService.hydrateReviewCandidateFromCaptureItem()`.
- Persistent `GET /candidates` self-heal across non-archived candidates.
- `review_board_hydration_summary` on `CandidateListResponse`.
- Per-candidate 22F-1E debug fields in `review_candidate_debug`.
- Duplicate Capture Inbox promotion sync now reuses the hydration helper.
- Safe dry-run backfill script: `scripts/backfill_review_board_candidates_from_capture_inbox.py` with optional `--apply`.
- Backend regression tests in `apps/api/tests/test_phase22f_review_candidate_contract.py`.
- Frontend `ReviewBoardPage` diagnostics now expose hydration provenance from `candidate.review_candidate_debug`.
- Frontend tests check hydration debug source fields in `apps/web/src/test/review-board.test.ts`.
- Log doc: `docs/metadata-phase22F-1E-review-board-candidate-hydration-backfill-log.md`.

## Important Files

- `apps/api/src/services/candidate_service.py`
- `apps/api/src/schemas/candidates.py`
- `apps/api/src/api/routes/candidates.py`
- `apps/api/src/services/capture_inbox_service.py`
- `apps/api/tests/test_phase22f_review_candidate_contract.py`
- `apps/web/src/components/review-board/ReviewBoardPage.tsx`
- `apps/web/src/types/review-board.ts`
- `apps/web/src/test/review-board.test.ts`
- `scripts/backfill_review_board_candidates_from_capture_inbox.py`

## Matching Rules

Hydration matches candidates to Capture Inbox items by this priority:

1. `capture_item_id`
2. `source_capture_item_id`
3. `aweme_id`
4. `source_video_external_id`
5. `source_url`
6. `video_url`
7. aweme id inside captured item URL
8. candidate URL containing captured item aweme id
9. normalized thumbnail plus caption exact match as weak fallback

## Safety Rules

- Fill missing/null/empty candidate metadata only.
- Preserve explicit `0` values.
- Never fake estimated views.
- Preserve candidate status, decisions, notes, and operator workflow data.
- Weak matches do not overwrite existing non-null candidate metadata.

## Validation Commands

Run from repo root unless noted:

```bash
cd apps/api
python -m unittest tests.test_phase22f_review_candidate_contract
python -m compileall src
```

```bash
npm --workspace @reup-douyin/web run test -- --runInBand
npm --workspace @reup-douyin/web run typecheck
npm --workspace @reup-douyin/web run build
```

## Manual Retest

1. Restart the API after backend code changes.
2. Open `/selection/review-board`.
3. Find the card with caption prefix `205海洋，生命的起源`.
4. Confirm it no longer shows `Score Unscored` when a matching Capture Inbox item has `reup_score`.
5. Confirm `Est. Views` uses the Capture Inbox estimated views display/range when present.
6. Confirm likes/comments/shares remain `205/21/13` and posted/duration/thumbnail fields are preserved or hydrated.
7. Inspect dev diagnostics and confirm trace `22F-1E`, hydration match key, capture item id, updated fields, and score/views/metrics sources are present.

## Known Notes

- Windows CMD does not support heredoc commands; use `python -c`, direct test commands, or file edits instead.
- The dry-run script prints per-candidate match/hydration results and rolls back unless `--apply` is passed.
