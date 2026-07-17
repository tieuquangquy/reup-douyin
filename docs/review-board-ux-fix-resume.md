# Review Board UX Fix Resume

## Goal

Fix the broken-looking `/selection/review-board` layout, make candidate cards compact and operator-friendly, and add a safe per-item Delete action.

## Audit Completed

- Read repository rules in `AGENTS.md`.
- Audited `apps/web/src/components/review-board/ReviewBoardPage.tsx`.
- Audited `apps/web/src/test/review-board.test.ts`.
- Audited shared Ops Console item-card primitives in `apps/web/src/components/ops-console/OpsShared.tsx`.
- Audited Review Board CSS areas in `apps/web/src/app/globals.css`.
- Audited web API and types in `apps/web/src/lib/api.ts` and `apps/web/src/types/review-board.ts`.
- Audited candidate API route and service in `apps/api/src/api/routes/candidates.py` and `apps/api/src/services/candidate_service.py`.
- Confirmed `CandidateStatus.ARCHIVED` already exists.

## Implementation Completed

1. Created docs before code changes.
2. Added backend candidate remove/archive behavior and response contract.
3. Added web API helper for per-candidate delete.
4. Replaced generic Review Board candidate card structure with a compact Review Board-specific row-card.
5. Added header-right status and Delete tool.
6. Added confirm UI with clear safe copy.
7. Synced local list, summary, selected ids, and active detail state after delete.
8. Added focused web/API tests.
9. Ran verification successfully.
10. Updated docs with actual results.

## Verification Results

- `npx tsx apps/web/src/test/review-board.test.ts` passed.
- `npm --workspace @reup-douyin/web run typecheck` passed.
- `cd apps/api && python -m unittest tests.test_review_board_candidate_delete` passed.

## Non-Goals

- No hard deletion of `SourceVideo`, source profiles, raw capture records, export records, queue records, or publish records.
- No new Review Board workflow.
- No hidden send-to-queue behavior.
- No broad redesign of Capture Inbox or Reup Queue.
