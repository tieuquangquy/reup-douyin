# Extension Protected Paths

## Purpose

This file defines code paths that should not be modified during the first cleanup implementation unless there is a focused task, backup snapshot, and manual regression run.

## Code paths not to touch yet

### Scan Profile accepted route

Protected files:

- [apps/extension-douyin-capture/src/popup.ts](../../apps/extension-douyin-capture/src/popup.ts)
- [apps/extension-douyin-capture/src/background.ts](../../apps/extension-douyin-capture/src/background.ts)
- [apps/extension-douyin-capture/src/contentScript.ts](../../apps/extension-douyin-capture/src/contentScript.ts)

Do not change:

- Popup Scan Profile dispatch behavior.
- Background route acceptance names.
- Background asynchronous scan execution and accepted-state persistence.
- Content handler DOUYIN_SCAN_PROFILE_MINIMAL_22C11B.
- Queue adapter output fields used by popup diagnostics.

### Queue finalization and target detail adaptation

Protected file:

- [apps/extension-douyin-capture/src/background.ts](../../apps/extension-douyin-capture/src/background.ts)

Do not change:

- Unique aweme ordering.
- Queue item shape.
- profile_queue_total_count and profile_batch_pending_count diagnostics.
- stop reason compatibility.
- Storage compaction unless specifically testing storage quota behavior.

### Calibration capture and preservation

Protected files:

- [apps/extension-douyin-capture/src/contentScript.ts](../../apps/extension-douyin-capture/src/contentScript.ts)
- [apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts](../../apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts)
- [apps/extension-douyin-capture/src/wholeProfileHarvest/calibration.ts](../../apps/extension-douyin-capture/src/wholeProfileHarvest/calibration.ts)
- [apps/extension-douyin-capture/src/storageKeys.ts](../../apps/extension-douyin-capture/src/storageKeys.ts)

Do not change:

- Four required points: like, comment, favorite, share.
- Calibration readiness checks.
- Calibration storage hydration.
- Reset Harvest calibration preservation.

### Start Collecting and backend session preflight

Protected files:

- [apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts](../../apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts)
- [apps/extension-douyin-capture/src/wholeProfileHarvest/canonicalHarvest.ts](../../apps/extension-douyin-capture/src/wholeProfileHarvest/canonicalHarvest.ts)
- [apps/extension-douyin-capture/src/extensionBackendClient.ts](../../apps/extension-douyin-capture/src/extensionBackendClient.ts)

Do not change:

- Calibration required before collection.
- Capture session create/reuse behavior.
- Allowed runner targets.
- Full-modal-harvest guard rules.
- Payload sanitization and no-secret leakage guards.

### Reset and storage keys

Protected files:

- [apps/extension-douyin-capture/src/extensionReset.ts](../../apps/extension-douyin-capture/src/extensionReset.ts)
- [apps/extension-douyin-capture/src/storageKeys.ts](../../apps/extension-douyin-capture/src/storageKeys.ts)
- [apps/extension-douyin-capture/src/popup.ts](../../apps/extension-douyin-capture/src/popup.ts)

Do not change:

- Reset Harvest preserving calibration.
- Reset Calibration clearing calibration only after explicit user action.
- Factory Reset confirmation copy and destructive scope.
- Legacy clear state not clearing calibration.

## Invariants to preserve

- Scan Profile must not require calibration.
- Calibration must be required for Start Collecting.
- A successful scan must produce a unique aweme queue.
- Queue count must not be capped to 10 during scan finalization.
- Backend session readiness must not imply collection has completed.
- Backend payload must not include debug, raw state, secrets, headers, cookies, tokens, or raw storage.
- Legacy runner targets must not become reachable through popup primary action.
- Reset Harvest must not wipe calibration.
- Existing action locks must be released on failure or terminal success.
- Diagnostic names used by popup must stay stable until UI consumers are updated.

## Risky files/functions

Highest risk:

- [apps/extension-douyin-capture/src/contentScript.ts](../../apps/extension-douyin-capture/src/contentScript.ts): many generations of scanner/probe/harvest/calibration logic share one message listener.
- [apps/extension-douyin-capture/src/background.ts](../../apps/extension-douyin-capture/src/background.ts): scan acceptance, storage mutation, queue finalization, CDP helpers, auth sync.
- [apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts](../../apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts): central state machine, legacy migration, calibration preservation, collection routes.
- [apps/extension-douyin-capture/src/popup.ts](../../apps/extension-douyin-capture/src/popup.ts): user-facing primary action and reset controls.

Medium risk:

- [apps/extension-douyin-capture/src/wholeProfileHarvest/canonicalHarvest.ts](../../apps/extension-douyin-capture/src/wholeProfileHarvest/canonicalHarvest.ts): payload shape and sanitization.
- [apps/extension-douyin-capture/src/extensionBackendClient.ts](../../apps/extension-douyin-capture/src/extensionBackendClient.ts): backend guard and timeout classification.
- [apps/extension-douyin-capture/src/storageKeys.ts](../../apps/extension-douyin-capture/src/storageKeys.ts): reset and migration blast radius.

Lower risk for first cleanup:

- Documentation-only marker maps.
- Adding comments or tests around legacy routes without changing behavior.
- Adding explicit audit docs.

## Manual tests required before and after cleanup

1. Scan Profile on known profile after manual bottom scroll still queues all loaded videos.
2. Scan Profile on unscrolled profile still does not fail earlier than before.
3. Popup primary action changes to Start Collecting only after scan and calibration readiness.
4. Four-point calibration still persists across popup close/open.
5. Reset Harvest preserves calibration and clears queue/progress as expected.
6. Clear Legacy State does not clear calibration.
7. Start Collecting creates/reuses backend session and starts canonical safe route.
8. Backend full-modal-harvest receives guarded final payload only.
9. No legacy runner target is reported as active_runner_target.
10. Existing extension tests related to reset, popup cleanup, payload guards, and network cache are run where feasible.
