# Phase 21D-16 Popup Live State Update Resume

## Current Phase

Phase 21D-16 — Fix popup realtime state update after Scan Profile click.

## Implemented

- The active popup state source remains canonical Whole Profile Harvest state in `chrome.storage.local[WHOLE_PROFILE_HARVEST_STATE_KEY]`.
- The popup now keeps `latestWholeProfileHarvestState` as a live local cache.
- Scan Profile click now applies and persists an optimistic running state before awaiting the long workflow.
- The currently open popup rerenders from the optimistic state immediately, which should show `Scanning Profile` and `Scanning...` without closing/reopening.
- The popup subscribes to `chrome.storage.onChanged` and watches `WHOLE_PROFILE_HARVEST_STATE_KEY`.
- Storage updates are normalized, passed through stale recovery, cached locally, and rendered live.
- The popup also listens for optional `douyinScanner:stateChanged` runtime messages.
- Storage and runtime listeners are removed on popup unload.
- Double clicks are guarded by `wholeProfileHarvestActionInFlight` and `getDouyinScannerBusyState`.
- Stale running scanner locks are recovered on popup state reads/live updates by marking running scan/classification steps failed, clearing action locks, recording `last_action_result: "stale_recovered"`, and persisting the recovered state.
- Tests were added/updated in popup and controller coverage.

## Files Changed

- `apps/extension-douyin-capture/src/popup.ts`
- `apps/extension-douyin-capture/src/chrome.d.ts`
- `apps/extension-douyin-capture/src/popupWorkflow.test.ts`
- `apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts`
- `docs/metadata-phase21D-16-popup-live-state-update-log.md`
- `docs/metadata-phase21D-16-popup-live-state-update-resume.md`

## Validation So Far

- `npm --workspace @reup-douyin/extension-douyin-capture run test` passed.

## Remaining Final Validation

Run these before final completion if not already done separately:

```text
npm --workspace @reup-douyin/extension-douyin-capture run typecheck
npm --workspace @reup-douyin/extension-douyin-capture run build
```

## Manual Retest Steps

1. Load the extension build.
2. Open a supported Douyin profile tab.
3. Open the extension popup.
4. Click Scan Profile once.
5. Confirm the same open popup immediately changes to `Scanning Profile` and the primary button changes to `Scanning...`.
6. Keep the popup open and confirm phases/progress update through waiting/scanning/classification.
7. Confirm final scan/classification success and queue counts appear without reopening.
8. Double-click Scan Profile and confirm only one workflow starts.
9. Simulate or preserve a scanner running state older than two minutes, reopen the popup, and confirm the stale lock is unblocked with recovery diagnostics.
