# Douyin Capture Inbox UX Redesign Resume Notes

## Resume Point

Continue from a docs-first redesign of `/ops/extensions/douyin/capture-inbox`. The target is an operator-first staging workspace, not a backend workflow rewrite.

## Files Expected To Change

- `apps/web/src/components/capture-inbox/CaptureInboxPage.tsx`
- `apps/web/src/test/capture-inbox.test.ts`
- `docs/douyin-capture-inbox-ux-redesign-log.md`
- `docs/douyin-capture-inbox-ux-redesign-resume.md`
- `docs/douyin-capture-inbox-ux-redesign-architecture.md`
- `docs/douyin-capture-inbox-ux-redesign-user-guide.md`

## Existing Surfaces

- Route: `/ops/extensions/douyin/capture-inbox`.
- Component: `CaptureInboxPage`.
- Types: `CaptureSession`, `CaptureSessionDetail`, `CapturedItem`, `CapturedItemStatus`, and `CaptureInboxAction`.
- API client functions: `fetchCaptureInboxSessions`, `fetchCaptureInboxSession`, and `runCaptureInboxAction`.

## Design Direction

- Header should clearly identify Douyin Capture Inbox, current session/profile context, primary CTA, and secondary navigation/actions.
- Summary cards should be clickable filters.
- Main item cards should avoid raw diagnostics and only show thumbnail, title/caption snippet, status badge, short source/video id, metadata summary, next action, and contextual buttons.
- Right-side detail panel should contain Overview, Source, Metadata, Media / Preview, and Diagnostics sections.
- Diagnostics must be collapsed by default.
- Batch action bar should appear only when items are selected.

## Constraints

- Do not rewrite Capture Inbox backend behavior.
- Do not expose secrets, cookies, raw credentials, or private local paths.
- Do not render fake zeroes for missing metadata; use honest phrases such as `Not captured`, `Pending`, or `Not analyzed yet`.
- Keep Review Board as the only promoted canonical review surface.

## Verification Plan

- Update focused source tests for summary cards, filters, contextual actions, batch bar, detail panel sections, and honest metadata labels.
- Run `npx tsx apps/web/src/test/capture-inbox.test.ts`.
- Run `npm run typecheck`.
