# Phase 21D-3 Visual Polish Compact Control Panel Resume

## Phase

21D-3 — Visual polish compact control panel

## Completed changes

- Preserved the existing Phase 21D-0 popup root: `#scannerControlPanelRoot.scp-shell`.
- Moved the health status row inside the hero header without changing chip IDs or renderer wiring.
- Replaced the dark main `scp-*` styling with premium light control panel styling.
- Added a blue gradient hero with compact video badge and inline health chips.
- Reworked the primary action card, counters, settings, and bottom actions into compact white product UI sections.
- Added `.scp-alert[hidden] { display: none; }` so the hidden alert cannot appear as an empty brown/orange bar.
- Added static test coverage for inline hero chips, light styling, compact settings, compact bottom actions, hidden alert behavior, and render-time backend-call guardrails.

## Explicit non-goals preserved

- No scan profile logic changes.
- No calibration logic changes.
- No collect or extract logic changes.
- No backend save logic changes.
- No API contract changes.
- No root replacement.
- No V2 or legacy runtime changes.

## Validation status

Passed:

```bash
npm --workspace @reup-douyin/extension-douyin-capture run test
npm --workspace @reup-douyin/extension-douyin-capture run typecheck
npm --workspace @reup-douyin/extension-douyin-capture run build
```

## Manual retest focus

1. Open the extension popup on a Douyin profile page.
2. Confirm the main popup shows a light product UI, not a dark debug panel.
3. Confirm `Profile`, `API Idle`, `Cal needed`, and `Safe` appear as small inline hero chips.
4. Confirm there are no separate TAB/API/CALIB/SAFETY cards.
5. Confirm no empty brown/orange bar appears above the primary button when calibration is needed.
6. Confirm Mode, Batch, and Speed are compact.
7. Confirm Capture Inbox, Advanced, and Reset appear in one compact bottom row.
8. Confirm primary action, Capture Inbox, Advanced, Reset, and settings handlers still work.
