# Capture Inbox Compact Media Action Card — Implementation Log

## Scope

Refactor only the Capture Inbox item card UI in [`apps/web/src/components/capture-inbox/CaptureInboxPage.tsx`](apps/web/src/components/capture-inbox/CaptureInboxPage.tsx) and supporting styles in [`apps/web/src/app/globals.css`](apps/web/src/app/globals.css) to a compact media-first card concept.

### In Scope

- Compact card anatomy around these zones:
  - Media/thumbnail zone
  - Overlay controls (selection/status)
  - Primary info row (short title + status)
  - Compact quick meta row
  - Compact actions row
- Preserve existing operator workflow semantics (selection, focus, action routing).
- Keep card-level actions concise and decision-focused.
- Shift verbose/secondary details to inspector/details consumption patterns rather than card body.
- Add/update focused source-contract tests in [`apps/web/src/test/capture-inbox.test.ts`](apps/web/src/test/capture-inbox.test.ts).

### Out of Scope

- No API/schema/backend/worker changes.
- No session ribbon/filter model redesign.
- No new feature workflow, persistence semantics, or queue behavior changes.
- No non-Capture-Inbox page redesign.

## Baseline Audit Notes

Current baseline identified in [`MediaTile()`](apps/web/src/components/capture-inbox/CaptureInboxPage.tsx:565):

- Card renders media first and includes top overlay controls.
- Card body still carries multiple metadata rows and visual weight that can be condensed.
- Action row uses contextual actions but requires compact hierarchy tuning for the card concept.
- Right inspector already exists and can absorb secondary/detail-heavy information.

Relevant supporting helpers currently in file:

- [`contextualActions()`](apps/web/src/components/capture-inbox/CaptureInboxPage.tsx:890)
- [`captionSnippet()`](apps/web/src/components/capture-inbox/CaptureInboxPage.tsx:906)
- [`metadataChipsForItem()`](apps/web/src/components/capture-inbox/CaptureInboxPage.tsx:960)
- [`RightInspector`](apps/web/src/components/capture-inbox/CaptureInboxPage.tsx:615)

## Implementation Plan

1. Update [`MediaTile()`](apps/web/src/components/capture-inbox/CaptureInboxPage.tsx:565) markup into compact card zones.
2. Tighten action hierarchy to compact row labels and prominence:
   - Details
   - Promote
   - Delete
3. Keep only compact, high-signal quick meta in-card.
4. Apply CSS density/spacing reductions and preserve accessibility in [`globals.css`](apps/web/src/app/globals.css).
5. Update tests in [`capture-inbox.test.ts`](apps/web/src/test/capture-inbox.test.ts) to enforce compact structure and action expectations.
6. Run validation commands and capture outputs.

## Risks and Mitigations

- **Risk:** Over-compression harms readability.
  - **Mitigation:** Preserve strong title/status contrast and maintain minimum touch target sizes.
- **Risk:** Action regressions from action-row rewrite.
  - **Mitigation:** Keep existing `onAction` wiring paths; verify via focused source-contract tests.
- **Risk:** CSS side effects on non-target components.
  - **Mitigation:** Scope selectors to Capture Inbox tile classes.

## Verification Plan

- Run focused test command:
  - `npx tsx apps/web/src/test/capture-inbox.test.ts`
- Run web typecheck:
  - `npm run typecheck --workspace apps/web`

## Implementation Results

Implemented compact media action card updates in [`apps/web/src/components/capture-inbox/CaptureInboxPage.tsx`](apps/web/src/components/capture-inbox/CaptureInboxPage.tsx):

- Refactored [`MediaTile()`](apps/web/src/components/capture-inbox/CaptureInboxPage.tsx:565) into compact-card anatomy:
  - media zone + existing overlay controls
  - compact primary row (`title + status`)
  - compact quick meta chip row
  - compact action row
- Added compact-card classing (`capture-inbox-compact-card`, `capture-inbox-compact-main`, `capture-inbox-tile-primary-row`, `capture-inbox-tile-primary-status`, `capture-inbox-tile-quick-meta`, `capture-inbox-compact-actions`).
- Reduced card-body verbosity by removing inline caption/source/id/next-action rows from the tile body.
- Replaced broad metadata chip helper with compact helper [`compactQuickMetaForItem()`](apps/web/src/components/capture-inbox/CaptureInboxPage.tsx:960).
- Tightened per-card action contract in [`contextualActions()`](apps/web/src/components/capture-inbox/CaptureInboxPage.tsx:890):
  - default compact row: `Details`, `Promote`, `Delete`
  - `Promote` remains readiness-gated (`disabled` when not ready)
  - promoted items preserve `Open candidate` affordance + `Details`

Implemented compact density styling in [`apps/web/src/app/globals.css`](apps/web/src/app/globals.css):

- Reduced tile/frame radius and spacing for tighter scan density.
- Added compact-row/status/quick-meta CSS selectors for new tile anatomy.
- Scoped styling changes to Capture Inbox tile classes only.

Updated focused source-contract assertions in [`apps/web/src/test/capture-inbox.test.ts`](apps/web/src/test/capture-inbox.test.ts):

- Removed stale expectations tied to old verbose card rows.
- Added compact anatomy/action assertions.
- Aligned resolver checks with compact quick-meta helper usage.

## Verification Results

Executed on 2026-04-28 (UTC):

1. `npx tsx apps/web/src/test/capture-inbox.test.ts`
   - **Pass**
   - Output: `capture inbox Media-first Triage Studio, canonical rendering, session ribbon, status strip, filter toolbar, right-side inspector, state sync, action hierarchy, and polish tests passed`
2. `npm run typecheck --workspace apps/web`
   - **Pass**
   - Output: `tsc --noEmit -p tsconfig.typecheck.json`

## Final Notes

- Scope respected: UI/UX card refactor only in web layer.
- No backend/API/worker changes were introduced.
