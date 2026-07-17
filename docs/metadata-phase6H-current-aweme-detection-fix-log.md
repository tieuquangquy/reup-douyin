# Phase 6H Current Aweme Detection Fix Log

## Problem

Full Modal Harvest could report:

- `Current aweme = not detected`
- `Harvested = 0`
- `Pending = 0`
- `Stopped reason = idle`

even when the operator had already opened a real Douyin video modal.

## Root cause

The extension start action returned popup progress too early.

- `runHarvestController(...)` returned `controller.progress` immediately.
- The background `controller.start()` loop had not yet updated `current_aweme_id`.
- So the popup rendered a stale pre-loop state.

The URL detector already supported `modal_id` and `/video/{id}`, but there was no start-time bootstrap or detector diagnostics.

## Fix strategy

- Bootstrap current aweme detection before returning start/resume progress.
- Run one immediate extraction pass for the current modal when possible.
- Persist detector diagnostics into progress/state.
- Keep the existing background harvest architecture intact.

## Scope

- `apps/extension-douyin-capture` only
- focused tests/docs only
- no backend changes
