# Phase 10C Smart Capture & Harvest Log

## Scope

- App: `apps/extension-douyin-capture`
- Goal: combine `Capture current page` and calibrated full-modal harvest into one operator action
- Non-goals:
  - backend normalizer changes
  - CDP/debug restoration
  - captcha bypass

## Why Combine Capture And Harvest

The operator workflow had become correct but still split across two manual phases:

1. capture the profile session
2. start calibrated modal harvest with the correct session binding

Phase 10C makes that one production workflow while keeping the same backend flush path and calibrated-point extractor.

## Internal Two-Phase Behavior

`Smart Capture & Harvest` still performs two internal phases:

1. run capture and persist `capture_session_id` / `capture_id`
2. run calibrated probe and modal harvest against that explicit session

## State Machine

- `idle`
- `capturing_profile`
- `capture_ready`
- `calibration_required`
- `modal_required`
- `probing`
- `harvesting`
- `flushing`
- `completed`
- `paused`
- `failed`

## Session Binding

After capture succeeds, the popup stores:

- `latest_capture_session_id`
- `latest_capture_id`
- `captured_item_count`
- `captured_at`
- `profile_url`

Harvest start/resume now passes explicit:

- `capture_session_id`
- `capture_id`

The content script uses those explicit values before falling back to stored defaults.

## Buttons In Normal UI

- `Smart Capture & Harvest`
- `Capture current page only`
- `Start Right Rail Calibration`
- `Show Calibration`
- `Clear Calibration`
- `Probe Current Modal Metrics`
- `Resume Harvest`
- `Stop Harvest`
- `Flush Pending`
- `Show Progress`

## Hidden From Normal UI

- Detect current page
- Attach CDP to Current Douyin Tab
- Detach CDP
- Show CDP Status
- Probe Current Modal via CDP
- Attach CDP and Refresh Current Modal

## Tests Run

- `cd apps/extension-douyin-capture && npm run typecheck`
- `cd apps/extension-douyin-capture && npm test`

## Verification Result

- typecheck passed
- extension tests passed
- build/dist resolution passed
