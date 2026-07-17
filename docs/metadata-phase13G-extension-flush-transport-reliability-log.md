# Phase 13G Extension Flush Transport Reliability Log

## Scope

Phase 13G is limited to the Douyin capture extension backend flush path. It improves localhost API transport reliability, diagnostics, retry behavior, and pending item preservation.

## Root Cause

The live `Failed to fetch` error came from extension-side backend transport rather than modal navigation or metric extraction. Harvested metrics were already extracted successfully, but localhost flush failures were surfaced as generic fetch errors without durable pending queue diagnostics or a clear operator recovery action.

## Changes

- Added centralized extension backend transport in `apps/extension-douyin-capture/src/extensionBackendClient.ts`.
- Routed background service-worker backend posting through the centralized client in `apps/extension-douyin-capture/src/background.ts`.
- Preserved backend post diagnostics through content-script flush failures in `apps/extension-douyin-capture/src/contentScript.ts`.
- Added persistent full modal harvest pending flush queue helpers in `apps/extension-douyin-capture/src/flushQueue.ts`.
- Extended shared extension types with backend error codes, retryability, next action, and pending queue state in `apps/extension-douyin-capture/src/types.ts`.
- Updated `FullModalHarvestController` in `apps/extension-douyin-capture/src/modalHarvest.ts` so extracted items are queued before flush, retryable backend failures pause with pending items preserved, and duplicate finalizer retry cycles are avoided.
- Updated popup progress diagnostics in `apps/extension-douyin-capture/src/popupProgress.ts` so flush failures show backend-specific recovery guidance rather than navigation guidance.
- Audited `apps/extension-douyin-capture/public/manifest.json`; localhost permissions were present and root `https://douyin.com/*` was added.
- Audited API CORS in `apps/api/src/main.py` and `apps/api/src/core/settings.py`; no API CORS change was required for this phase because extension transport now uses the background service worker with localhost host permissions.

## Verification

- `npm --workspace @reup-douyin/extension-douyin-capture run typecheck` passed during integration.
- `npm --workspace @reup-douyin/extension-douyin-capture run test` passed after the duplicate retry-cycle fix. The test script also ran the extension build and distribution module-resolution check.

## Non-Goals

- No metric extraction changes.
- No calibrated point workflow changes.
- No Capture Inbox web UI changes.
- No CDP/debug workflow reintroduction.
- No fake successful flush responses.
- No dropping pending items on failed backend transport.
