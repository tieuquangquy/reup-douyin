# Douyin Capture Inbox Wording Cleanup Resume

## Current Status

Complete. Capture Inbox wording has been audited, normalized, implemented, tested, and documented.

## User Request

Cleanup and normalize all English wording across `/ops/extensions/douyin/capture-inbox` so the page reads clearly, concisely, and consistently for operators.

## Required Order

1. Audit wording across the whole page.
2. Create docs first.
3. Define normalized terminology list.
4. Update page-level copy.
5. Update summary/filter/action wording.
6. Update item/session/drawer wording.
7. Update empty/error/fallback text.
8. Update tests if needed.
9. Run verification.
10. Update docs.

## Completed Work

- Read `AGENTS.md`.
- Confirmed this was scoped to `apps/web`, `docs`, and focused tests.
- Audited Capture Inbox wording.
- Audited Review Board and Reup Queue tone references.
- Created the three required wording cleanup docs before implementation.
- Defined normalized terminology.
- Updated page-level wording.
- Updated summary, filter, and action wording.
- Updated item, session, and drawer wording.
- Updated empty, fallback, and confirm dialog wording.
- Updated focused source-based tests.
- Ran verification successfully.
- Updated docs with final implementation and verification results.

## Files Changed

- `apps/web/src/components/capture-inbox/CaptureInboxPage.tsx`
- `apps/web/src/test/capture-inbox.test.ts`
- `docs/douyin-capture-inbox-wording-cleanup-log.md`
- `docs/douyin-capture-inbox-wording-cleanup-resume.md`
- `docs/douyin-capture-inbox-wording-cleanup-user-guide.md`

## Normalized Terminology

Use these terms consistently:

- `Details`
- `Ready`
- `Needs action`
- `Preview pending`
- `Failed`
- `Promoted`
- `Not captured`
- `Pending`
- `Not analyzed yet`
- `Promote`
- `Retry enrich`
- `Retry preview`
- `Exclude`
- `Delete`

## Main Copy Changes

- Page description: shorter and operator-focused.
- Summary cards: shorter helper text and `Needs action` terminology.
- Filter section: `Find captured items`.
- Item fallback: `No thumbnail`.
- Drawer: `Details` / `Item details`.
- Drawer sections: `Source`, `Metadata`, `Outputs`, `Diagnostics`, `Raw details`.
- Empty states: shorter and actionable.
- Delete confirmations: shorter but still explicit about promoted records/items.
- Batch retry label: `Retry enrich selected`.

## Preserved Technical Text

The following wording was intentionally preserved because it helps diagnostics and support:

- `Diagnostics`
- `Raw details`
- `Action source URLs`
- `Latest raw action details`
- `Dedupe`
- `Readiness`
- JSON payload output
- raw session status enum values in the session filter

## Verification

Command run from `c:/Users/PC/Desktop/reup_douyin`:

```powershell
npx tsx apps/web/src/test/capture-inbox.test.ts && npm run typecheck --workspace apps/web
```

Result:

```text
capture inbox UX redesign, action hierarchy, and polish tests passed

> typecheck
> tsc --noEmit -p tsconfig.typecheck.json
```

## Known Issue Fixed During Verification

The first verification run failed because `Needs enrichment` still appeared in the summary helper text. It was replaced with `Needs follow-up or preview.`, and verification then passed.

## Next Step

No implementation work remains for this wording cleanup task.
