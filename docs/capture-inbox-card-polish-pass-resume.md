# Capture Inbox Card Polish Pass — Resume

## Objective (strict)

Refine **only** these 3 Capture Inbox item card UI points:
1. Redesign Select pill to compact single-line control.
2. Remove duplicated `Ready` meaning on lower card while keeping overlay `Ready` badge.
3. Reduce on-card metadata to only 3–4 high-value chips.

## Scope lock

Only web card-level files:
- [`apps/web/src/components/capture-inbox/CaptureInboxPage.tsx`](apps/web/src/components/capture-inbox/CaptureInboxPage.tsx)
- [`apps/web/src/app/globals.css`](apps/web/src/app/globals.css)
- [`apps/web/src/test/capture-inbox.test.ts`](apps/web/src/test/capture-inbox.test.ts)

No backend/API/extraction/selection semantics/page-layout redesign.

## Planned execution order

1. Redesign Select pill visual/structure (single compact chip).
2. Remove duplicated lower Ready meaning; keep top-right overlay badge.
3. Simplify quick meta to: Duration, Posted, Views, Preview.
4. Keep technical details accessible in inspector if needed.
5. Update focused tests for exactly these points.
6. Run focused tests + typecheck.

## Verification commands

- `npx tsx apps/web/src/test/capture-inbox.test.ts`
- `npm run typecheck --workspace apps/web`

## Status

- Docs-first completed.
- Implementation completed for all 3 scoped UI polish items only.
- Focused verification completed:
  - `npx tsx apps/web/src/test/capture-inbox.test.ts` ✅
  - `npm run typecheck --workspace apps/web` ✅
