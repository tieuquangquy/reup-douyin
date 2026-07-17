# Phase 18I-K2 Tabbed Popup Layout Log

## Why popup moved to tabs

The popup was still too long because workflow actions, results, and technical diagnostics shared one scroll stack. This phase split the popup into three operator-oriented tabs so the main workflow stays short:

1. `Run`
2. `Results`
3. `Technical`

## What belongs in Run

- ready status chips
- stepper
- next action card
- primary action
- workflow buttons
- compact Mode / Batch / Speed settings
- compact save flow
- Stop / Resume / Reset

Run intentionally excludes queue tables, recent results tables, payload/request summaries, and raw debug state.

## What belongs in Results

- KPI summary cards
- queue preview
- recent extraction results
- recent backend save results
- Capture Inbox CTA

Results is for operator review of what happened, not for diagnostics or raw state.

## What belongs in Technical

- API base URL
- reconnect control
- technical summary rows
- full queue / extraction / backend result lists
- save detail rows
- debug details
- Copy Debug JSON
- Clear Legacy State

## Tab state behavior

- UI-only state in `douyinWholeProfileHarvestUiPrefs.active_tab`
- supported values:
  - `run`
  - `results`
  - `technical`
- default tab is `run`
- switching tabs does not call backend and does not change harvest state

## Tests run

- `npm --workspace @reup-douyin/extension-douyin-capture run test`
- `npm --workspace @reup-douyin/extension-douyin-capture run typecheck`
- `npm --workspace @reup-douyin/extension-douyin-capture run build`

## Remaining polish ideas

- add richer tab badges for failed result counts
- make queue preview remember its own collapsed state
- consider a dedicated Capture Inbox link button when a stable route is available
