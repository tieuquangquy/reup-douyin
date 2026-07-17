# Phase 22A Start Collecting Diagnostics Resume

## Completed
- Added persisted [`pause_diagnostics`](apps/extension-douyin-capture/src/wholeProfileHarvest/state.ts:356) and [`collect_trace`](apps/extension-douyin-capture/src/wholeProfileHarvest/state.ts:357) to harvest state.
- Appended bounded collection trace entries from [`checkpointTarget()`](apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts:1570).
- Persisted pause snapshots from [`pauseHarvest()`](apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts:1604), including captcha evidence and queue progress.
- Surfaced collection diagnostics in Advanced details via [`setDetailSummary()`](apps/extension-douyin-capture/src/popup.ts:1503).
- Added `collect_diagnostics` to copied debug JSON in [`copyWholeProfileDebugJsonFromPopup()`](apps/extension-douyin-capture/src/popup.ts:1535).
- Added regression coverage in [`wholeProfileHarvest.test.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts:308) and [`wholeProfileHarvest.test.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts:805).
- Passed validation:
  - [`npm run extension:test`](package.json:24)
  - `npx tsc -p apps/extension-douyin-capture/tsconfig.json --noEmit`

## Current behavior
- Start Collecting now leaves a durable per-run breadcrumb trail in [`collect_trace`](apps/extension-douyin-capture/src/wholeProfileHarvest/state.ts:357).
- Paused harvest runs now preserve structured pause context in [`pause_diagnostics`](apps/extension-douyin-capture/src/wholeProfileHarvest/state.ts:356).
- Advanced details expose whether collect diagnostics exist, what the latest event was, and current queue progress.
- Copy Debug JSON now includes a dedicated `collect_diagnostics` payload for operator troubleshooting.

## Non-goals preserved
- No Capture Inbox UI redesign.
- No backend API or storage contract changes.
- No expansion into broader worker/job durability beyond the existing extension harvest state.

## If work resumes later
1. If operators need richer debugging, consider rendering the last few [`collect_trace`](apps/extension-douyin-capture/src/wholeProfileHarvest/state.ts:357) entries directly in the Advanced panel instead of summary-only fields.
2. If backend-assisted troubleshooting becomes necessary, add a narrowly scoped diagnostics field to the extension/backend contract rather than leaking raw state.
3. Re-check retention size if collection sessions become longer; the current trace is intentionally bounded in [`checkpointTarget()`](apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts:1599).
