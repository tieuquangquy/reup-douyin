# Metadata Phase 18B Extension Whole Profile Harvest State Machine Log

## Scope

Implemented the canonical Phase 18B Whole Profile Harvest state machine in the Douyin capture extension.

## Completed

- Added canonical state storage under `douyinWholeProfileHarvest` with schema `phase18b_whole_profile_harvest_state_machine`.
- Added reusable controller, profile resolver, scanner, target validation, dry-run, progress, and error modules under `apps/extension-douyin-capture/src/wholeProfileHarvest`.
- Wired popup product actions to the canonical controller for Verify Profile, Dry-run First/Last/Random, Stop, Resume, Reset, Copy Debug JSON, and progress rendering.
- Kept legacy full-modal/staged harvest entrypoints quarantined behind guarded or maintenance-only paths; Phase 18B Run Harvest remains explicitly not implemented until Phase 18C.
- Added Phase 18B tests for state writes, dry-run sampling, reset semantics, and progress summaries.

## Non-goals

- No crawler implementation.
- No production harvest/flush implementation.
- No backend contract changes.
- No queue/database/schema changes.
- No UI business flow beyond canonical popup wiring for Phase 18B controls.

## Verification

Verification commands are tracked in the matching resume document and should include extension typecheck/build/test before handoff.
