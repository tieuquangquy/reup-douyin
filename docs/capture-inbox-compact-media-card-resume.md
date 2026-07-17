# Capture Inbox Compact Media Action Card — Resume

## Objective

Implement a compact media-first item card in Capture Inbox that reduces per-card height and cognitive load while preserving existing selection and action workflows.

## Scope Lock

- Target only Capture Inbox item card UI and immediate supporting styles/tests.
- Primary implementation files:
  - [`apps/web/src/components/capture-inbox/CaptureInboxPage.tsx`](apps/web/src/components/capture-inbox/CaptureInboxPage.tsx)
  - [`apps/web/src/app/globals.css`](apps/web/src/app/globals.css)
  - [`apps/web/src/test/capture-inbox.test.ts`](apps/web/src/test/capture-inbox.test.ts)
- No backend/API/worker/domain model changes.

## Target Card Anatomy

1. Media/thumbnail zone (dominant visual area).
2. Overlay controls (compact select + status chip).
3. Primary info row:
   - concise title snippet
   - status badge
4. Quick meta row:
   - only high-signal compact metadata needed for triage decisions
5. Actions row:
   - `Details` (secondary)
   - `Promote` (primary)
   - `Delete` (danger)

## Content Allocation Rules

- Keep only decision-critical metadata on card.
- Move verbose identifiers, diagnostics, and long text details to inspector panel.
- Preserve existing action handlers and item focus semantics.

## Verification Commands

- `npx tsx apps/web/src/test/capture-inbox.test.ts`
- `npm run typecheck --workspace apps/web`

## Status

- Docs-first completed.
- Compact Media Action Card implementation completed in [`CaptureInboxPage.tsx`](apps/web/src/components/capture-inbox/CaptureInboxPage.tsx), [`globals.css`](apps/web/src/app/globals.css), and focused assertions in [`capture-inbox.test.ts`](apps/web/src/test/capture-inbox.test.ts).
- Verification completed:
  - `npx tsx apps/web/src/test/capture-inbox.test.ts` (pass)
  - `npm run typecheck --workspace apps/web` (pass)
