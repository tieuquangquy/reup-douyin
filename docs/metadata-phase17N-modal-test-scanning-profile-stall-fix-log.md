# Phase 17N Modal Test Scanning Profile Stall Fix Log

## Root Cause

The Phase 17M transition correctly moved ready same-context profile diagnostics from `waiting_profile_ready` to `scanning_profile`, but the scanner execution remained delegated to the older completion path. That path persisted `scanning_profile` and then ran profile scanning without durable per-round heartbeat/progress fields. If scanner execution stalled or popup state was reopened while progress was missing, the UI could remain at `Scanning profile...` with `Scan rounds: unknown` and `Scroll container: no`.

A stale global detector banner could also remain visible even though same-context diagnostics already proved the active Modal Whole Profile Test was on a profile page with `modal_id` absent.

## Same-Context Direct Scanner Behavior

When no-reload modal close succeeds and diagnostics show same-context/profile/no-modal readiness, the Modal Whole Profile Test now starts `runModalWholeProfileScanInContentScript(runId)` directly instead of forcing another global detector reconnect. The direct runner validates the active tab URL against `expected_profile_url`, starts the scan phase, and executes `scanModalWholeProfileCardsInPage` in the active content-script context.

## Scan Heartbeat And Progress

The profile scanner now supports an `on_round` progress callback. Each round updates the isolated `douyinModalWholeProfileTestRun` runtime with:

- `scan_heartbeat_at`
- `scan_rounds`
- `total_cards_found_so_far`
- `last_round_new`
- `scroll_container_status`
- per-round scan diagnostics including selector attempts and visible/candidate counts

This makes popup rendering deterministic during `scanning_profile` and avoids indefinite `unknown` progress.

## Timeout Behavior

The direct scanner is wrapped by `withTimeout` with a 45 second hard cap. Popup resume/stall handling also treats missing or stale heartbeat after 12 seconds as `profile_scan_stalled`.

Failure reasons added for this phase include:

- `profile_scan_stalled`
- `profile_scan_timeout`
- `profile_scan_runner_not_started`
- `harvest_plan_failed`

## Stale Detector Banner Suppression

The popup continues suppressing stale global detector errors when an active Modal Whole Profile Test has same-context profile diagnostics with `modal_id_present = false`. The UI shows the modal test phase/progress or precise scan failure instead of the stale detector banner.

## Harvest-Plan Transition

When cards are found, the test transitions to `building_harvest_plan`, builds a `douyin_extension_harvest_plan.v1` payload in `refresh_all` mode, posts `/douyin-extension/harvest-plan`, and completes the isolated verify run if targets are returned. Verify-only still does not call full-modal-harvest or create production Smart Capture state.

## Tests Run

Pending final command run in this task:

```cmd
npm --workspace @reup-douyin/extension-douyin-capture run test
npm --workspace @reup-douyin/extension-douyin-capture run typecheck
npm --workspace @reup-douyin/extension-douyin-capture run build
```

## Live Retest Steps

1. Reload the unpacked `apps/extension-douyin-capture` extension.
2. Open a Douyin modal URL with `/user/{profile_id}?modal_id={aweme_id}`.
3. Open Advanced / Beta in the popup.
4. Click `Test Modal → Whole Profile Harvest`.
5. Confirm the test advances from modal close to `Scanning profile...`.
6. Confirm `Scan rounds`, `Last round new`, and `Scroll container` update during scan.
7. Confirm no stale `Could not execute the Douyin detector in this tab.` banner appears when same-context profile diagnostics exist.
8. Confirm the run either completes after harvest-plan or fails with a precise scan/harvest-plan reason.
