# Phase 17G Modal Whole-Profile Beta Test

## Scope

Phase 17G adds an isolated Advanced / Beta popup feature for validating this path:

1. Start on a Douyin profile modal URL shaped like `/user/{profile_id}?modal_id={aweme_id}`.
2. Resolve the modal URL back to the profile URL.
3. Run the existing harvest-plan profile scan from the resolved profile page.
4. Store only a beta test report in extension local storage.
5. Optionally dry-run probe the first 3 target modal videos without starting production Smart Capture & Harvest.

## Non-goals

- No crawler implementation.
- No production harvest start.
- No Tile Gallery writes from the dry-run itself.
- No changes to backend contracts.
- No changes to Smart Capture & Harvest queue ownership beyond adding an isolation option for beta reads.

## UI

The popup now includes an Advanced / Beta panel with:

- `Test Modal → Whole Profile Harvest`
- `Reset Modal Test`
- `Verify only`
- `Dry-run first 3 videos`

The result panel renders a summary and a copyable JSON report.

## Isolation behavior

The beta flow uses the same profile resolution and harvest-plan code paths as Smart Capture, but calls profile scanning with persisted Smart Capture state disabled. This avoids overwriting sync `lastCaptureSessionId`, sync `lastCaptureId`, and the canonical Smart Capture state while still validating whether the modal can resolve to a whole-profile target queue.

The beta report is stored under `douyinModalWholeProfileTestRun` only.

## Verification mode

`Verify only` resolves the profile, scans the profile, records total found, records target IDs, and reports whether a whole-profile target queue can be constructed.

## Dry-run mode

`Dry-run first 3 videos` performs the same profile resolution and target queue validation, then navigates the active tab to the first 3 target modal URLs and probes current modal metrics. It records pass/fail results with duration and right-rail counts when available. It does not send production harvest start messages and does not flush harvested metadata.

## Verification commands

- `npx tsc -p apps/extension-douyin-capture/tsconfig.json --noEmit`
- `npm --workspace @reup-douyin/extension-douyin-capture run test`
