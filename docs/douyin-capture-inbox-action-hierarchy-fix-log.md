# Douyin Capture Inbox Action Hierarchy Fix Log

## Scope

Normalize action hierarchy, icon usage, labels, and action presentation in Capture Inbox so it matches the interaction model already used by Review Board and Reup Queue.

## Touched areas

- `apps/web/src/components/capture-inbox/CaptureInboxPage.tsx`
- `apps/web/src/test/capture-inbox.test.ts`
- `docs/douyin-capture-inbox-action-hierarchy-fix-log.md`
- `docs/douyin-capture-inbox-action-hierarchy-fix-resume.md`
- `docs/douyin-capture-inbox-action-hierarchy-fix-user-guide.md`

## Non-goals

- No backend business logic changes.
- No capture, promotion, retry, exclude, delete, or queue semantics changes.
- No whole-page redesign.
- No new icon dependency.
- No auto-publish or worker behavior changes.

## Audit findings

### Review Board

- Uses shared Ops Console primitives and action tones.
- Primary actions are explicit state transitions such as `Keep`, `Keep selected`, and `Send to Reup Queue`.
- Destructive actions use `tone: "danger"` or `className="danger"`, such as `Reject` and `Reject selected`.
- Secondary actions use default button/link styling, such as `Details`, `Mark in review`, and `Reset`.
- Filter action hierarchy uses `Apply` as primary and `Reset` as secondary/default.
- No icon-heavy pattern is used.

### Reup Queue

- Uses shared Ops Console primitives and action tones.
- Main lifecycle actions use primary styling.
- Destructive workflow actions such as `CANCEL` and `MARK_BLOCKED` are rendered with `danger` styling.
- Utility/open actions are grouped separately from lifecycle actions.
- Active filter buttons use `className={filter === entry.key ? "primary" : undefined}`.
- No shared icon component or icon library usage was found in audited Reup Queue action areas.

### Shared Ops action primitives

- `OpsItemAction` supports `tone: "primary" | "secondary" | "danger"`.
- `OpsActionRow` maps primary to `button.primary`, danger to `button.danger`, and secondary to default styling.
- `OpsBatchActionBar` uses `OpsActionRow`, preserving the same button hierarchy.
- No icon field exists in `OpsItemAction`.

### Capture Inbox before fix

- Header promote CTA lacked explicit primary styling.
- Filter selected state used `selected`, unlike Reup Queue's primary active-filter style.
- Item card action row manually rendered buttons instead of using the shared `OpsActionRow` mapping.
- Item card action buttons did not apply primary/danger classes from `tone` because of manual rendering.
- Details labels were inconsistent: `Open details drawer`, `View more in details`, `View error`, `View details`, and `Details`.
- Failed retry action used `Retry` instead of the requested `Retry enrich` label.
- Session delete was already correctly placed inside the compact overflow menu and visually destructive.

## Normalized hierarchy adopted

1. Primary
   - Main progression/recovery action in the current context.
   - Capture Inbox examples: `Promote ready items`, `Promote`, `Promote selected`, and `Retry enrich` when it is the main recovery action.

2. Secondary
   - Useful contextual action that does not permanently remove or skip work.
   - Capture Inbox examples: `Details`, `Retry preview`, `Open source profile`, `Refresh session`, and `Go to Review Board`.

3. Tertiary/subtle
   - Low-priority utility, dense diagnostics, raw details, or long-text disclosure.
   - Capture Inbox examples: `Show more`, `Show less`, raw details sections, auxiliary source/preview/share opens.

4. Destructive
   - Permanently removes staged local records or explicitly excludes/skips staging work.
   - Capture Inbox examples: `Delete staged item`, `Delete selected`, `Delete session`, `Exclude`, and `Exclude selected`.

## Icon rules adopted

- Do not introduce a new icon library.
- Do not add icons to every action.
- Preserve `⋯` only as the established overflow-menu affordance for compact session rows.
- Use text labels as the primary affordance because Review Board and Reup Queue rely on text plus tone, not icons.
- If future shared icon support is added, the same semantic icon must be reused consistently and placed before the label.

## Implementation completed

- Applied `className="primary"` to the header `Promote ready items` CTA.
- Changed Capture Inbox status filter active style from `selected` to `primary` to match Reup Queue.
- Imported and used `OpsActionRow` for Capture item card actions.
- Preserved `tone` mapping so `Promote` becomes primary and `Exclude` / `Delete staged item` become destructive through shared action rendering.
- Normalized item detail affordances to `Details`.
- Removed `View error`, `View details`, `Open details drawer`, and `View more in details` as action labels.
- Changed failed item recovery from `Retry` to `Retry enrich`.
- Updated failed next-action copy to `Open details, then retry enrich or exclude.`
- Kept session delete inside the session overflow menu only.
- Kept bulk actions on `OpsBatchActionBar` with `Promote selected` primary and `Exclude selected` / `Delete selected` destructive.
- Added focused source tests for hierarchy, labels, destructive distinctness, shared batch/action rows, and no noisy icon plumbing.

## Verification

Passed:

```powershell
npx tsx apps/web/src/test/capture-inbox.test.ts && npm run typecheck --workspace apps/web
```

Output:

```text
capture inbox UX redesign, action hierarchy, and polish tests passed

> typecheck
> tsc --noEmit -p tsconfig.typecheck.json
```

## Remaining inconsistencies

- Reup Queue header buttons currently rely on default styling for top-level package/handoff actions. Capture Inbox now follows the clearer Review Board-style explicit primary tone for its main CTA without changing Reup Queue.
- Capture Inbox still uses the existing `⋯` glyph for session overflow. This is intentional because no shared icon system exists in the audited sibling workflows.
