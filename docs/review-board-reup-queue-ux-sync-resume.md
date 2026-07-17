# Review Board + Reup Queue UX Sync Resume

## Current task

Unify Review Board and Reup Queue into the same operator workflow family as Capture Inbox.

## Guardrails

- Preserve Review Board semantics: review candidates, keep/reject/approve/in-review actions, approved handoff to Reup Queue, and existing candidate filtering/scoring behavior.
- Preserve Reup Queue semantics: lifecycle states, processing actions, media-prep handoff, export package handoff, publish handoff, and queue transitions.
- Do not alter backend logic unless required by compilation.
- Do not introduce new business features.
- Do not add a competing layout system.

## Files changed

- apps/web/src/components/review-board/ReviewBoardPage.tsx
- apps/web/src/components/reup-queue/ReupQueuePage.tsx
- apps/web/src/app/globals.css
- apps/web/src/test/review-board.test.ts
- apps/web/src/test/reup-queue.test.ts
- docs/review-board-reup-queue-ux-sync-log.md
- docs/review-board-reup-queue-ux-sync-resume.md
- docs/review-board-reup-queue-ux-sync-architecture.md
- docs/review-board-reup-queue-ux-sync-user-guide.md

## Audit findings to preserve during implementation

### Review Board

- Keep `enqueueReupCandidates` as the Reup Queue transition.
- Keep `bulkUpdateCandidateStatus` for keep/reject/in-review changes.
- Replace implicit first-candidate detail fallback with explicit active candidate id/open state.
- Use a right-side sticky inspector that can be closed and shows an empty prompt when closed or stale.
- Keep selected ids independent from active candidate id.

### Reup Queue

- Keep `runReupQueueAction` and `runReupQueueBatchAction` semantics.
- Keep status and media-prep lifecycle states unchanged.
- Decouple checkbox selection from active item focus.
- Remove active fallback to hidden/all items and first visible item.
- Keep operator bucket meaning if retained visually, but align rhythm with compact workspace grammar.

## Verification results

These commands passed:

```cmd
npx tsx apps/web/src/test/review-board.test.ts
npx tsx apps/web/src/test/reup-queue.test.ts
npm run typecheck --workspace apps/web
```

## Final state

Review Board and Reup Queue now use compact status strips, clean filter bars, media-aware item previews, explicit right-side sticky inspectors, decoupled selection/focus behavior, normalized action hierarchy, and selected-item batch bars while preserving existing backend workflow semantics.
