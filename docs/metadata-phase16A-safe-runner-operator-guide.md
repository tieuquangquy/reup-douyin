# Metadata Phase 16A — Safe Runner Operator Guide

## What changed for operators
- Harvest controls continue to work as before.
- Internally, SAFE command pathways are now first-class.
- Reset operations continue to reinitialize safe idle state.

## Operator-facing behavior
- Start/Resume/Stop/Reset buttons continue to operate from popup workflows.
- Progress remains visible with existing harvest panel behavior.
- If harvest is paused, resume behavior is unchanged from prior phase.

## Diagnostics
- SAFE runtime state is persisted under storage key: `douyinSafeHarvestRun`.
- Legacy keys may still exist for compatibility but are no longer the preferred canonical surface.

## Recommended checks after upgrade
1. Start a harvest and verify progress updates.
2. Stop and resume once.
3. Reset harvest state and confirm idle state appears.
4. Run extension test suite if validating locally.
