# Douyin Capture Inbox Action Hierarchy User Guide

## What changed conceptually

Capture Inbox now uses the same action hierarchy as Review Board and Reup Queue:

1. Primary actions move work forward or perform the most important recovery step.
2. Secondary actions inspect, retry a narrower step, refresh, or navigate without destructive impact.
3. Tertiary actions expose supporting information such as long text, raw details, or auxiliary links.
4. Destructive actions remove staged records or explicitly exclude work.

## Primary actions

Use primary actions when the operator is ready to move staged capture work forward.

Examples:

- `Promote ready items`
- `Promote`
- `Promote selected`
- `Retry enrich` when a failed or incomplete item needs the main recovery path

## Secondary actions

Use secondary actions to inspect or support the primary workflow without changing business state destructively.

Examples:

- `Details`
- `Retry preview`
- `Open source profile`
- `Refresh session`
- `Go to Review Board`

## Tertiary actions

Use tertiary actions for low-priority detail disclosure and auxiliary references.

Examples:

- `Show more`
- `Show less`
- Raw details sections
- Share, preview, thumbnail, and diagnostic links in the detail drawer

## Destructive actions

Use destructive actions only when intentionally removing staged Capture Inbox records or explicitly excluding work.

Examples:

- `Delete staged item`
- `Delete selected`
- `Delete session`
- `Exclude`
- `Exclude selected`

Destructive delete actions still require confirmation where the workflow already requires confirmation.

## Icon behavior

Capture Inbox intentionally does not add broad icon usage. Review Board and Reup Queue primarily use text labels plus button tone, so Capture Inbox follows that same pattern.

The only compact icon-like affordance is the `⋯` overflow control on Capture session rows. It exists to keep the session list compact while keeping `Delete session` available in a predictable place.

## Operator workflow

1. Use summary cards or status filters to narrow staged items.
2. Use `Details` on a card to open the detail drawer.
3. Use `Promote` or `Promote selected` for ready items.
4. Use `Retry enrich` or `Retry preview` for incomplete items.
5. Use `Exclude` only for items that should be skipped from staging.
6. Use `Delete staged item`, `Delete selected`, or session overflow `Delete session` only when staged local records should be removed.
7. Continue approved work in Review Board, then Reup Queue.

## Updated label rules

Use these labels consistently in Capture Inbox:

- `Details`
- `Delete staged item`
- `Delete selected`
- `Delete session`
- `Retry enrich`
- `Retry preview`
- `Promote`
- `Promote selected`

Avoid older duplicate labels such as `Open details drawer`, `View more in details`, `View error`, `View details`, or generic failed-state `Retry`.

## Notes

- This guide describes interaction hierarchy only.
- It does not change capture, promotion, retry, deletion, exclusion, backend, queue, or publishing behavior.
