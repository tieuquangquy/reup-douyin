# Review Board UX Fix Log

## Scope

This log tracks the narrow UX and delete-action hardening for `/selection/review-board`.

## Current UI Root Causes

- Review candidates render through the generic shared item card, which places checkbox, preview, metadata, and status in a loose header structure.
- Preview sizing is not specific to Review Board density, so cards can look sparse and visually unbalanced.
- Status is technically in the header, but it is not paired with destructive/cleanup tools and can feel detached from operator action hierarchy.
- Footer actions are all generated through one action row, making Keep, Details, Mark in review, and Reject visually close in priority.
- There is no per-item delete/remove action.

## Backend Boundary Findings

- Review Board renders `VideoCandidate` records through `/candidates`.
- Candidate status already supports `ARCHIVED`.
- Current list endpoint returns all statuses unless a status filter is provided; this means archiving alone would not hide candidates from the default Review Board unless list semantics are tightened.
- Reup Queue uses `video_candidate_id`, so delete must avoid hard-deleting canonical candidate/source data.

## Chosen Delete Semantics

- Use candidate-level safe archive/remove-from-board semantics.
- `Delete` means: set candidate status to `ARCHIVED` and mark metadata with review-board removal evidence.
- It does not delete `SourceVideo`, source profile, capture/raw records, queue records, exports, or handoff records.
- Default Review Board list excludes archived candidates unless the operator explicitly filters `ARCHIVED`.

## Implemented Changes

1. Added a focused `DELETE /candidates/{candidate_id}` endpoint returning an explicit delete response message.
2. Added candidate service archive semantics via `remove_from_review_board`.
3. Tightened default candidate listing to exclude `ARCHIVED` candidates unless the operator explicitly filters that status.
4. Added a web API helper for safe Review Board candidate delete.
5. Replaced the generic Review Board candidate item card with a compact horizontal card:
   - left rail: checkbox and preview
   - center: caption/title, source, score, next action, reason, metrics
   - header-right: status chip and Delete tool
   - footer: Keep/Send to Reup Queue, Mark in review, Reject, Details
6. Added per-item confirmation UI with explicit safe-delete copy.
7. Synced candidate list, summary counts, selected ids, and active detail drawer after delete success.
8. Added focused web source assertions and API unit tests.

## Verification

- `npx tsx apps/web/src/test/review-board.test.ts` passed.
- `npm --workspace @reup-douyin/web run typecheck` passed.
- `cd apps/api && python -m unittest tests.test_review_board_candidate_delete` passed.

## Guardrails

- No hard delete of upstream canonical data.
- No hidden Reup Queue side effects.
- No workflow redesign beyond the requested Review Board UX/action hierarchy.
- Keep Capture Inbox and Reup Queue changes out of scope except for visual language alignment through existing CSS patterns.
