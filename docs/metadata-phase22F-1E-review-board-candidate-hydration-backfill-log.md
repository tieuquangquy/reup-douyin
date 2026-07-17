# Phase 22F-1E Log

- Goal: backfill and self-heal Review Board candidates from Capture Inbox metadata without forcing delete/re-promote flows.
- Root cause: some legacy `video_candidates` rows never received canonical `reup_score`, estimated views, duration, posted text, thumbnail, and engagement metrics even though matching `captured_items` rows already held that metadata.
- Backend work:
  - Added `CandidateEvaluationService.hydrateReviewCandidateFromCaptureItem()` to match Review Board candidates back to Capture Inbox items and fill missing candidate metadata safely.
  - Added persistent `GET /candidates` self-heal via `_hydrate_stale_candidates_from_capture_inbox()` so stale rows are hydrated before response serialization.
  - Added `review_board_hydration_summary` to `CandidateListResponse` and `GET /candidates`.
  - Added per-candidate debug exposure for hydration attempt, match key, capture item id, updated fields, skip reason, score source, estimated views source, and metrics source.
  - Reused hydration helper from duplicate promotion sync in `CaptureInboxService` so existing Review Board candidates are enriched through the same path.
  - Added dry-run/apply script at `scripts/backfill_review_board_candidates_from_capture_inbox.py`.
- Matching priority implemented:
  1. `candidate.capture_item_id == captured_item.id`
  2. `candidate.source_capture_item_id == captured_item.id`
  3. `candidate.aweme_id == captured_item.aweme_id`
  4. `candidate.source_video_external_id == captured_item.source_video_external_id`
  5. `candidate.source_url == captured_item.source_url`
  6. `candidate.video_url == captured_item.video_url`
  7. candidate aweme id inside captured item URL
  8. candidate URL containing captured item aweme id
  9. normalized thumbnail plus caption exact match as weak fallback
- Hydration rules implemented:
  - Fill missing or empty candidate metadata from Capture Inbox metadata.
  - Preserve explicit zeroes such as `0` likes/comments/shares.
  - Do not fake estimated views if Capture Inbox metadata is also missing them.
  - Preserve candidate review status, decisions, and notes.
  - Weak thumbnail/caption matches only fill missing fields and do not replace already present non-null values.
- Frontend work:
  - Kept visible score on canonical `reup_score` via `reviewCandidateDisplayScore()`.
  - Kept estimated views rendering on canonical hydrated fields.
  - Extended Review Board visible diagnostics with hydration provenance from backend debug payloads.
- Test coverage added:
  - Service/schema tests for hydration by `capture_item_id` and `aweme_id`.
  - Preservation tests for approved/rejected status, notes, and explicit zeroes.
  - Missing estimated views regression coverage.
  - Non-hydratable summary/debug coverage.
  - Frontend source tests for 22F-1E hydration debug exposure.
- Validation planned/executed from repo root:
  - `python -m unittest tests.test_phase22f_review_candidate_contract` from `apps/api`
  - `python -m compileall src` from `apps/api`
  - `npm --workspace @reup-douyin/web run test -- --runInBand`
  - `npm --workspace @reup-douyin/web run typecheck`
  - `npm --workspace @reup-douyin/web run build`
