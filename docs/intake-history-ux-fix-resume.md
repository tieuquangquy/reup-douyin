# intake-history-ux-fix-resume.md

## Current Step
- Finalization step for `/intake` run-history UX compression and handoff summary.

## Done
- Re-audited constraints from [`AGENTS.md`](AGENTS.md).
- Audited existing run-history architecture docs and current UI composition in [`IntakePage`](apps/web/src/components/intake/IntakePage.tsx:44).
- Implemented compact run-history behavior in [`RunHistoryPanel`](apps/web/src/components/intake/IntakePage.tsx:1081):
  - default compact rendering,
  - profile-group summary cards,
  - max 5 groups shown by default,
  - secondary full-history toggle area.
- Kept existing quick actions and detail hooks intact:
  - [`onSelectRun`](apps/web/src/components/intake/IntakePage.tsx:1093)
  - [`onApplyRun`](apps/web/src/components/intake/IntakePage.tsx:1094)
- Updated i18n labels in:
  - [`apps/web/src/lib/i18n/en.json`](apps/web/src/lib/i18n/en.json)
  - [`apps/web/src/lib/i18n/vi.json`](apps/web/src/lib/i18n/vi.json)
- Ran web verification successfully:
  - [`npm run typecheck --workspace apps/web`](apps/web/package.json)

## Behavior After Fix
- Main `/intake` sidebar now stays compact and scan-friendly.
- Run history now emphasizes operator-relevant summary first (recent grouped view) instead of long raw list.
- Full history remains accessible through explicit expand action in the same panel.
- Troubleshooting and compare flows continue to use selected run ids unchanged.

## Key Files To Continue
- [`apps/web/src/components/intake/IntakePage.tsx`](apps/web/src/components/intake/IntakePage.tsx)
- [`apps/web/src/lib/i18n/en.json`](apps/web/src/lib/i18n/en.json)
- [`apps/web/src/lib/i18n/vi.json`](apps/web/src/lib/i18n/vi.json)
- [`docs/intake-history-ux-fix-log.md`](docs/intake-history-ux-fix-log.md)
- [`docs/intake-history-ux-fix-resume.md`](docs/intake-history-ux-fix-resume.md)
