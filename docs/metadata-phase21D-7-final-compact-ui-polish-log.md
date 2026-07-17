# Phase 21D-7 Final Compact UI Polish Log

Date: 2026-05-07

## Scope

Phase 21D-7 was limited to final compact UI polish for the Douyin Scanner popup before backend classification work. The change stayed inside popup markup, popup styling, UI-only view-model labels, tests, and documentation.

## Settings collapsed behavior

- Collection settings now start collapsed on popup initialization.
- The collapsed row keeps the title `Collection settings` and summary `New + incomplete · Next 10 · Safe`.
- The collapsed action is `Edit`.
- Clicking `Edit` locally expands the `Mode`, `Batch`, and `Speed` selects.
- The expanded action becomes `Done`.
- Clicking `Done` collapses the settings again.
- Expansion is intentionally local-only for this polish pass: popup initialization forces collapsed state and no longer persists settings expansion.
- Existing option save handlers for Mode, Batch, and Speed were preserved.

## API wording change

- The user-facing API chip changed from `API idle` to `API not checked`.
- Ready and offline wording remains `API ready` and `API offline`.
- Backend/scanner calls were not added during render.

## Empty state polish

- The pre-scan empty state copy changed to `Scan a profile to build the collection plan.`
- The empty state now uses the lighter `scanner-hint` treatment.
- The hint was removed from the heavier card grouping and now uses smaller padding, a lighter border, and muted text.

## Footer polish

- `Capture Inbox` is secondary blue and matches the footer button scale.
- `Advanced` is neutral.
- `Reset` uses a danger ghost style with transparent background and reduced visual weight.
- Footer button height and shadow were reduced so the primary scanner action remains dominant.

## Non-goals honored

- No scan-profile logic changes.
- No calibration logic changes.
- No collect/extract logic changes.
- No backend save logic changes.
- No API contract changes.
- No backend calls during render.
- No queue table, debug section, backend details, payload/data check, save session controls, or test first/last buttons were added to the main screen.

## Tests run

- `npm --workspace @reup-douyin/extension-douyin-capture run test` passed.
- `npm --workspace @reup-douyin/extension-douyin-capture run typecheck` passed.
- `npm --workspace @reup-douyin/extension-douyin-capture run build` passed.

## Next phase recommendation

Recommended next phase: 21B backend data model + classification endpoint.
