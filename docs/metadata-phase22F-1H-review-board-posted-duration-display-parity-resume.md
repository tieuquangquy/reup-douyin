# Phase 22F-1H Review Board Posted and Duration Display Parity Resume

## Status

Implemented and validated.

## Scope Completed

- Audited the active Posted/Duration path before implementation.
- Backend now exposes camelCase aliases and debug source/value fields for posted and duration display.
- Frontend adapter now preserves Capture Inbox `source_metadata.posted_display` verbatim and exposes `postedSource` / `durationSource`.
- Review Board card now shows Duration when available.
- Details/diagnostics now expose posted/duration provenance.
- Raccoon fixture tests were added for `114浣熊与黑熊` with Posted `23:00:00 2/4/2026` and Duration `12:14`.

## Files Changed

- `apps/api/src/schemas/candidates.py`
- `apps/api/src/api/routes/candidates.py`
- `apps/api/tests/test_phase22f_review_candidate_contract.py`
- `apps/web/src/lib/reviewCandidateMetadata.ts`
- `apps/web/src/types/review-board.ts`
- `apps/web/src/components/review-board/ReviewBoardPage.tsx`
- `apps/web/src/test/review-candidate-metadata.test.ts`
- `apps/web/src/test/review-board.test.ts`
- `docs/metadata-phase22F-1H-review-board-posted-duration-display-parity-log.md`
- `docs/metadata-phase22F-1H-review-board-posted-duration-display-parity-resume.md`

## Root Causes

- Posted mismatch: Review Board card could fall back to `source_video.posted_at`, parse it as a JavaScript `Date`, and render `toLocaleDateString()`, causing locale/timezone formatted output like `03/04/2026` instead of the Capture Inbox `posted_display` text.
- Missing Duration: Review Board card primary metadata row did not render duration, even when `duration_text` was available in source metadata.

## Validation Run

```cmd
cd apps/api
python -m unittest tests.test_phase22f_review_candidate_contract
python -m compileall src

npm --workspace @reup-douyin/web run test
npm --workspace @reup-douyin/web run typecheck
npm --workspace @reup-douyin/web run build
```

## Manual Retest

1. Restart the API and web app so `22F-1H` code is running.
2. Open Review Board.
3. Find the candidate whose caption contains `114浣熊与黑熊`.
4. Confirm the card shows `Posted 23:00:00 2/4/2026`.
5. Confirm the card shows `Duration 12:14`.
6. Open Details and confirm posted/duration source diagnostics point to `source_metadata.posted_display` and `source_metadata.duration_text`.
7. Confirm score, estimated views, likes, comments, shares, thumbnail, caption, and review status are unchanged.
