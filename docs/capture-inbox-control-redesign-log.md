# Capture Inbox Control Redesign Log

## 1) Current problems

- Batch bar presents as a heavy admin-style box and feels noisy for media triage.
- Selected count is repeated in each action label, reducing scan clarity.
- Tile select control is visually bulky and competes with thumbnail content.
- Ready/status chip is too dim on high-variance thumbnails.
- Overlay controls do not read as a compact moderation surface.

## 2) New visual hierarchy

- Keep thumbnail as visual hero.
- Make controls compact, floating, and contrast-safe.
- Put selection count in one anchored place in batch bar.
- Use hierarchy by tone and emphasis:
  - Primary: Promote
  - Secondary: Retry, Exclude
  - Destructive: Delete
  - Tertiary: Clear

## 3) New batch toolbar design

- Convert batch area into a compact sticky command bar style.
- Left side:
  - strong count line (e.g., `47 selected`)
  - smaller helper text (`Only eligible items will be affected.`)
- Right side action cluster:
  - `Promote` (primary)
  - `Retry` + `Exclude` (secondary)
  - `Delete` (danger)
  - `Clear` (lowest emphasis)
- Remove repeated per-button counts from labels.

## 4) New Select overlay design

- Replace bulky select treatment with minimal floating checkbox chip.
- Keep hit area comfortable but compact.
- Selected state remains explicit without becoming dominant.
- Keep selection semantics unchanged.

## 5) New Ready chip design

- Keep top-right compact status chip.
- Increase readability on bright/dark thumbnails via contrast-safe surface.
- Maintain compact size and moderation-tool tone.

## 6) Files changed

Planned edits in this task:

- `apps/web/src/components/capture-inbox/CaptureInboxPage.tsx`
- `apps/web/src/app/globals.css`
- `apps/web/src/test/capture-inbox.test.ts`
- `docs/capture-inbox-control-redesign-log.md`
- `docs/capture-inbox-control-redesign-resume.md`

## 7) Verification result

Completed successfully.

- Command: `npx tsx apps/web/src/test/capture-inbox.test.ts && npm run typecheck --workspace apps/web`
- Result:
  - `capture inbox Media-first Triage Studio, canonical rendering, session ribbon, status strip, filter toolbar, right-side inspector, state sync, action hierarchy, and polish tests passed`
  - `tsc --noEmit -p tsconfig.typecheck.json` passed
