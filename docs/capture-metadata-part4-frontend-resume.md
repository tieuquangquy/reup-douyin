# Capture Metadata Part 4 Frontend Resume

Date: 2026-04-29
Status: Completed

## Scope lock

- Part 4 only: frontend wiring in `apps/web` for canonical Time + Performance + Processing fit fields exposed by Capture Inbox API.
- No extension changes.
- No backend persistence/API changes.
- Keep compact card compact; surface richer details in inspector.
- Preserve honest processing-fit null semantics (`null` => unknown/unavailable).

## Audit summary

### Type layer

- `apps/web/src/types/capture-inbox.ts` partially covers canonical fields but lags Part 3 backend exposure.
- Missing frontend type coverage for new first-class provenance and processing-fit semantic fields.
- `posted_source` union needs `detail_hydrate` compatibility.

### UI layer

- `apps/web/src/components/capture-inbox/CaptureInboxPage.tsx` already has:
  - compact quick/metric helpers,
  - advanced filter panel controls,
  - `buildAdvancedFilterPayload(...)` mapping and apply/reset flow.
- Gaps are primarily:
  - explicit inspector rows for provenance + processing-fit semantics,
  - final type alignment to consume backend response safely,
  - tests to lock intended behavior.

## Planned implementation order

1. Update frontend types in `apps/web/src/types/capture-inbox.ts`.
2. Keep tile compact helpers minimal; only tune if needed for canonical subset clarity.
3. Expand inspector metadata sections in `apps/web/src/components/capture-inbox/CaptureInboxPage.tsx` to expose richer canonical/provenance/processing-fit details.
4. Verify/tighten advanced filter payload mapping contract in `buildAdvancedFilterPayload(...)`.
5. Add focused tests in Capture Inbox frontend test files.
6. Run frontend verification tests and record evidence.
7. Finalize Part 4 docs with completion status and result summary.

## Implementation summary

- Part 4 frontend scope implemented in `apps/web` only.
- Type contract now matches Part 3 backend exposure for canonical provenance + processing-fit semantics.
- Compact card remains compact while adding concise engagement rate signal (`ER`).
- Right inspector now surfaces richer canonical provenance/processing-fit rows with honest null semantics (`Unknown`).
- Advanced-filter mapping remains aligned with backend contract without backend edits.

## Verification status

- Focused verification commands (from repo root):
  - `npx tsx apps/web/src/test/capture-inbox.test.ts`
  - `npx tsx apps/web/src/test/capture-inbox-canonical.test.ts`
- Results:
  - capture-inbox source/structure assertions passed.
  - canonical resolver behavior assertions passed.
