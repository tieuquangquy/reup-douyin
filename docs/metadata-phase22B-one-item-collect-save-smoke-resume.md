# Phase 22B — One-item Collect + Save Smoke Resume

## What Phase 22B Does

Start Collecting now uses a one-item smoke path for the active scanner collect flow. It processes exactly one pending queue item, saves it through the existing Capture Inbox backend ingest path, verifies the item through session readback, and stops.

## Files Changed

- `apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts`
  - Adds `getFirstPendingCollectTarget(state)`.
  - Routes Start Collecting into `one_item_smoke_test` with `batch_limit = 1`.
  - Adds one-item open/extract/build/guard/save/verify orchestration.
- `apps/extension-douyin-capture/src/wholeProfileHarvest/canonicalHarvest.ts`
  - Adds full-modal Capture Inbox payload builder.
  - Adds stricter one-item payload guard.
  - Updates payload summary support for full-modal request envelopes.
- `apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts`
  - Updates runtime fixture to support full-modal request envelopes.
  - Adds Phase 22B target selection, one-item Start Collecting, payload builder, and guard assertions.

## Retest Steps

1. Scan a Douyin profile with at least one new/incomplete/failed queued target.
2. Ensure calibration is complete.
3. Click Start Collecting.
4. Confirm the extension processes exactly one target.
5. Confirm backend save succeeds through `POST /douyin-extension/full-modal-harvest`.
6. Confirm readback succeeds through `GET /douyin-extension/capture-sessions/{capture_session_id}/items`.
7. Open Capture Inbox and confirm the session no longer shows `0 captured`.

## Important Constraints Preserved

- Capture Inbox frontend UI was not touched.
- Backend code was not touched.
- No fake metrics are generated.
- The runner does not mark a target saved without backend success.
- The ingest payload does not send `capture_session_source`.
- Full batch collection remains out of scope for this phase.

## Commands To Run

```bash
npm --workspace @reup-douyin/extension-douyin-capture run test
npm --workspace @reup-douyin/extension-douyin-capture run typecheck
npm --workspace @reup-douyin/extension-douyin-capture run build
```

Backend validation is not required unless backend code is changed.
