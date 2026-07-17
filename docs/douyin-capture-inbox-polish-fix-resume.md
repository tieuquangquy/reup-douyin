# Douyin Capture Inbox Polish Fix Resume

## Current task

Hard-fix and polish `/ops/extensions/douyin/capture-inbox` after the first card redesign pass.

## Required outcomes

- Deleted staged items must immediately disappear from the UI and summary counts must reflect the remaining current items.
- Thumbnail rendering must use real captured thumbnail/cover/poster fields when present and keep an honest placeholder only when none exists.
- `Open details drawer` and `Details` buttons must visibly open the same detail inspector.
- Long titles/captions must be clamped on cards, with full text available in the detail inspector.
- Capture Sessions must become compact and scannable.
- Item Detail panel must become compact and operator-friendly while retaining diagnostics behind a collapsed section.

## Files expected to change

- `apps/web/src/components/capture-inbox/CaptureInboxPage.tsx`
- `apps/web/src/app/globals.css`
- `apps/web/src/test/capture-inbox.test.ts`
- `apps/api/src/services/capture_inbox_service.py`
- `docs/douyin-capture-inbox-polish-fix-log.md`
- `docs/douyin-capture-inbox-polish-fix-resume.md`
- `docs/douyin-capture-inbox-polish-fix-user-guide.md`

## Root-cause summary

- Stale count: persisted reconciliation was trusted over the actual item list, and backend deletion reconciled before deleted rows were flushed out of the loaded collection.
- Missing thumbnail: resolver was too shallow and did not inspect metadata/nested raw image fields or image-like preview URLs.
- Broken drawer: state changed, but desktop layout did not have a meaningful open/closed drawer presentation.

## Verification plan

Run:

```cmd
npm run typecheck --workspace apps/web && npx tsx apps/web/src/test/capture-inbox.test.ts
```

If backend test coverage is added, run the focused API tests documented in the final log.

## Current status

Implemented and verified.

Verification passed:

```cmd
npm run typecheck --workspace apps/web && npx tsx apps/web/src/test/capture-inbox.test.ts
```
