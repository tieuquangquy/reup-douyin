# intake-history-ux-fix-log.md

## Step
- UX compression pass for `/intake` run history to reduce sidebar vertical overload while preserving fast operator actions and full-history access.

## Time Started
- 2026-04-22 (UTC)

## Findings
- [`RunHistoryPanel`](apps/web/src/components/intake/IntakePage.tsx:1081) previously rendered every run as a full card, causing long scroll and lower scan speed on [`/intake`](apps/web/src/components/intake/IntakePage.tsx:690).
- Existing data from [`fetchIntakeRuns(12)`](apps/web/src/components/intake/IntakePage.tsx:137) is already ordered for recency and sufficient for compact summarization without backend changes.
- Existing run-detail and compare panels are already linked to selected run ids, so compacting history can stay UI-only with minimal disruption.

## Decisions Made
- Keep backend unchanged and implement compact behavior only in [`apps/web/src/components/intake/IntakePage.tsx`](apps/web/src/components/intake/IntakePage.tsx).
- Show grouped profile summary cards with max 5 groups by default.
- Keep full run list accessible via explicit secondary interaction (toggle expand/collapse) inside the same panel.
- Preserve existing actions: view details + reuse source.

## Files Touched
- [`apps/web/src/components/intake/IntakePage.tsx`](apps/web/src/components/intake/IntakePage.tsx)
  - Refactored [`RunHistoryPanel`](apps/web/src/components/intake/IntakePage.tsx:1081) to:
    - group by profile identity,
    - show compact group summary,
    - default to 5 groups,
    - expose full-history toggle section.
- [`apps/web/src/lib/i18n/en.json`](apps/web/src/lib/i18n/en.json)
  - Added compact-history labels and summary text keys.
- [`apps/web/src/lib/i18n/vi.json`](apps/web/src/lib/i18n/vi.json)
  - Added Vietnamese compact-history labels and summary text keys.

## Verification Notes
- Typecheck passed:
  - [`npm run typecheck --workspace apps/web`](apps/web/package.json)
- Initial interpolation usage was incompatible with current [`useT`](apps/web/src/lib/i18n.tsx) signature, then fixed by composing strings in UI with primitive translation keys.

## Status
- UX-fix implementation complete and compile-verified.
