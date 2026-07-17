# Phase 18I-K3 Compact Run Tab One-Screen Log

## Why Run tab was compacted

After the 3-tab split, the `Run` tab still carried too much vertical weight. Operators still had to scroll past workflow help, settings, buttons, save rows, and other supporting content before they could act.

This phase keeps `Run` focused on:

1. current readiness
2. current workflow step
3. the single next action
4. current settings
5. compact counters

## What remains in Run

- compact ready-status area at the top of the popup
- mini stepper
- next action card
- one primary action
- compact settings row
- compact metrics row
- compact secondary actions
- compact save area
- alert only when needed

## What moved to Results

- queue preview
- recent extraction results
- recent backend save results
- summary KPI cards
- Capture Inbox CTA

## What moved to Technical

- connection raw details
- API URL
- reconnect control
- payload/data-check details
- backend request/response summaries
- full queue and result lists
- legacy/debug summary

## One-primary-action rule

Only one large primary button remains visible for the recommended next step. Secondary actions stay compact and muted.

## Tests run

- `npm --workspace @reup-douyin/extension-douyin-capture run test`
- `npm --workspace @reup-douyin/extension-douyin-capture run typecheck`
- `npm --workspace @reup-douyin/extension-douyin-capture run build`

## Remaining polish ideas

- reduce save rows further when session/data check are still locked
- optional iconography for mini stepper states
- optional compact floating results badge when extraction is running
