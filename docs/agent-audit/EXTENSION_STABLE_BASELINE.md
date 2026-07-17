# Extension Stable Baseline

## Scope

This document records the current working baseline for the Douyin extension. It is audit-only and must be used as the safety reference before any cleanup implementation.

## Current known working behavior

- Operator opens a real Douyin profile page.
- Popup Scan Profile dispatches to the background scan route and returns accepted/success state.
- If the operator manually scrolls the Douyin profile grid to the bottom first, Scan Profile can discover all loaded videos on the tested profile.
- Calibration 4 Points works and produces ready calibration state.
- After calibration, expected good popup readiness is:
  - Calibration ready: yes.
  - Canonical calibration ready: yes.
  - Extraction ready: yes.
  - Backend session ready: yes.
  - Primary action: Start Collecting.
- Queue building works for the tested profile:
  - Profile normalized count can reach 46.
  - Profile queue total count: 46.
  - Pending count: 46.
- Backend session creation/reuse is ready.
- Remaining known issue is scan completeness when the profile was not pre-scrolled by the user; this is extension auto-scroll/discovery behavior, not backend, calibration, or database behavior.

## Protected canonical user flow

`Popup Scan Profile -> canonical whole-profile harvest controller -> content script scanner/autoscroll -> unique aweme target queue -> Calibration 4 Points -> Start Collecting -> canonical payload builder -> backend full-modal-harvest -> Capture Inbox`

Relevant protected files:

- [apps/extension-douyin-capture/src/popup.ts](../../apps/extension-douyin-capture/src/popup.ts)
- [apps/extension-douyin-capture/src/background.ts](../../apps/extension-douyin-capture/src/background.ts)
- [apps/extension-douyin-capture/src/contentScript.ts](../../apps/extension-douyin-capture/src/contentScript.ts)
- [apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts](../../apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts)
- [apps/extension-douyin-capture/src/wholeProfileHarvest/profileScanner.ts](../../apps/extension-douyin-capture/src/wholeProfileHarvest/profileScanner.ts)
- [apps/extension-douyin-capture/src/wholeProfileHarvest/targetValidation.ts](../../apps/extension-douyin-capture/src/wholeProfileHarvest/targetValidation.ts)
- [apps/extension-douyin-capture/src/wholeProfileHarvest/canonicalHarvest.ts](../../apps/extension-douyin-capture/src/wholeProfileHarvest/canonicalHarvest.ts)
- [apps/extension-douyin-capture/src/extensionBackendClient.ts](../../apps/extension-douyin-capture/src/extensionBackendClient.ts)

## Current good diagnostic states

- Scan accepted state writes a running scan workflow with action lock set to scan_profile in [apps/extension-douyin-capture/src/background.ts](../../apps/extension-douyin-capture/src/background.ts).
- Current scan engine diagnostic reports minimal_active_works_grid_scanner_22C11B in [apps/extension-douyin-capture/src/background.ts](../../apps/extension-douyin-capture/src/background.ts).
- Current content handler reports DOUYIN_SCAN_PROFILE_MINIMAL_22C11B and traceVersion 22C-11B in [apps/extension-douyin-capture/src/contentScript.ts](../../apps/extension-douyin-capture/src/contentScript.ts).
- Queue adapter reports scan_queue_adapter_22C11B and profile_queue_total_count in [apps/extension-douyin-capture/src/background.ts](../../apps/extension-douyin-capture/src/background.ts).
- Start Collecting requires calibrated four-point right rail state in [apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts](../../apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts).
- Backend full-modal-harvest guard allows only known callers and blocks debug/secrets/disallowed payload fields in [apps/extension-douyin-capture/src/extensionBackendClient.ts](../../apps/extension-douyin-capture/src/extensionBackendClient.ts).

## Files/functions likely involved in working paths

- Popup entry and primary action routing: [apps/extension-douyin-capture/src/popup.ts](../../apps/extension-douyin-capture/src/popup.ts)
- Popup action locking/error projection: [apps/extension-douyin-capture/src/popupActions.ts](../../apps/extension-douyin-capture/src/popupActions.ts)
- Background Scan Profile acceptance/finalization: [apps/extension-douyin-capture/src/background.ts](../../apps/extension-douyin-capture/src/background.ts)
- Content script minimal active works scan/autoscroll: [apps/extension-douyin-capture/src/contentScript.ts](../../apps/extension-douyin-capture/src/contentScript.ts)
- Profile URL resolution: [apps/extension-douyin-capture/src/wholeProfileHarvest/profileResolver.ts](../../apps/extension-douyin-capture/src/wholeProfileHarvest/profileResolver.ts)
- Target validation: [apps/extension-douyin-capture/src/wholeProfileHarvest/targetValidation.ts](../../apps/extension-douyin-capture/src/wholeProfileHarvest/targetValidation.ts)
- Controller state machine, scan, calibration preservation, collection: [apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts](../../apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts)
- Canonical payload/session/queue construction: [apps/extension-douyin-capture/src/wholeProfileHarvest/canonicalHarvest.ts](../../apps/extension-douyin-capture/src/wholeProfileHarvest/canonicalHarvest.ts)
- Storage key groups and reset key safety: [apps/extension-douyin-capture/src/storageKeys.ts](../../apps/extension-douyin-capture/src/storageKeys.ts)

## Manual regression checklist

Run before and after any cleanup implementation:

1. Load extension on a real Douyin profile.
2. Open popup and verify no stale busy/action lock state is shown.
3. Click Scan Profile once without calibration and verify scan is accepted and completes or reports a clear diagnostic.
4. On the known tested profile, manually scroll to bottom first, then click Scan Profile and verify 46 queued/pending items still appears.
5. Verify Scan Profile does not require calibration.
6. Run Calibration 4 Points and verify calibration ready/canonical calibration ready/extraction ready are all yes.
7. Click Start Collecting and verify backend session ready/session verified appears.
8. Verify one-item or next-10 safe collection uses the canonical route and does not show legacy runner target diagnostics.
9. Verify Reset Harvest preserves calibration.
10. Verify Reset Calibration and Factory Reset remain explicit and destructive only after confirmation.

## Non-goals for cleanup phase

- Do not delete files.
- Do not remove code without a rollback snapshot.
- Do not change backend or web app behavior.
- Do not change calibration semantics.
- Do not reconcile runtime marker drift in the same phase as route cleanup.
