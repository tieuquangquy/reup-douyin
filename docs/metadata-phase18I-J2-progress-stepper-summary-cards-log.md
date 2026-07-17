# Phase 18I-J2 Progress Stepper + Summary Cards Log

## Why raw Progress list was replaced

The old Progress area rendered a long raw key/value dump. Operators had to parse:

- state flags
- backend sub-status fields
- queue preview blobs
- layer booleans
- raw phase/status strings

That made the popup hard to scan even after Phase 18I-J1 fixed readiness correctness.

## What changed

- Added canonical progress view model:
  - `apps/extension-douyin-capture/src/wholeProfileHarvest/viewModel.ts`
- Replaced raw main Progress list with:
  - 4-step workflow stepper
  - Next Action card
  - Summary cards
  - collapsible Details block
- Kept readiness/action gating from Phase 18I-J1 unchanged.

## Stepper status rules

- Verify Profile
  - done: verified targets exist
  - active: verifying/scanning
  - failed: verify/profile scan failed
  - todo: not scanned
- Dry-run
  - done: dry-run usable
  - active: dry-running
  - warning: completed with warnings
  - failed: dry-run failed
  - todo: not run
- Extract Metrics
  - done: extraction completed
  - active: extraction running
  - warning: extracted with some failures
  - failed: extraction failed
  - todo: dry-run done but extraction not started
- Flush
  - done: backend flush completed
  - active: flush running
  - warning: completed with warnings
  - failed: flush failed
  - todo: extraction exists but flush not done

## Summary cards

- Profile Scan
  - targets
  - accepted/rejected
  - complete/new/incomplete/unknown
  - scan rounds
  - stop reason
- Dry-run Summary
  - mode
  - pass/fail
  - sample size
  - completed time
- Extraction Summary
  - mode
  - batch
  - speed
  - extracted/failed/pending
  - current target
  - last checkpoint
- Backend Flush
  - session
  - payload guard
  - one-item flush
  - batch flush
  - flushed/failed
- Safety
  - captcha/checkpoint
  - consecutive errors
  - last delay
  - tab health

## Details / Advanced split

Main Progress no longer shows:

- raw long profile URL
- raw phase/status dump
- queue preview blob
- recent result blob
- legacy state dump

These now live in:

- `Details` collapsible area inside Progress
- existing popup `Details` / `Advanced Diagnostics`

## Queue preview rendering

- Rendered as list rows, not one long multiline blob
- first 5 rows only
- `+N more` shown when queue is longer

## Tests run

- `npm --workspace @reup-douyin/extension-douyin-capture run test`
- `npm --workspace @reup-douyin/extension-douyin-capture run typecheck`
- `npm --workspace @reup-douyin/extension-douyin-capture run build`

## Next UX phase

- tighten spacing between action controls and progress cards
- reduce duplicated guidance between action helper text and next-action card
