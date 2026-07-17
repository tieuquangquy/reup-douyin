# Phase 17O Modal Test Scan Runner Wiring Resume

## Current State

Phase 17O wires Modal Whole Profile Test profile scanning through a standardized content-script message with a ping probe and direct same-context fallback.

## Expected Runtime Behavior

1. Modal test reaches `scanning_profile` after no-reload profile readiness succeeds.
2. `profile_card_scan_status` and `profile_scan_status` become `starting`.
3. Popup sends `REUP_DOUYIN_MODAL_TEST_SCAN_PROFILE_PING`.
4. If ping fails, popup reconnects/injects content script once and pings again.
5. If handler is still missing, run fails with `profile_scan_handler_not_registered` and handler diagnostics.
6. If handler exists, popup records `scanner_invocation_mode = content_script_message`, marks scan statuses `running`, and sends `REUP_DOUYIN_MODAL_TEST_SCAN_PROFILE`.
7. Content script runs `collectProfileCardsUntilStable()` and returns cards, counts, and diagnostics.
8. If same-context fallback is needed, popup records `scanner_invocation_mode = direct_same_context` and executes the direct scan.
9. Successful card scan transitions to `building_harvest_plan`; verify-only calls `/douyin-extension/harvest-plan` but not full modal harvest.

## Retest Steps

1. Reload the unpacked extension in Chrome.
2. Open a Douyin modal URL on a profile page.
3. Open the extension popup.
4. In Advanced / Beta, run `Test Modal → Whole Profile Harvest` in verify-only mode.
5. Confirm runtime shows `profile_card_scan_status = starting` briefly, then `running` after scanner invocation.
6. Confirm `scanner_invocation_mode` is `content_script_message` or `direct_same_context`.
7. Confirm `scan_rounds` becomes at least `1` and selector attempts are present.
8. Confirm cards found transition to `building_harvest_plan`, then `completed` when harvest-plan returns targets.
9. Confirm verify-only does not create visible Capture Inbox items or start full-modal-harvest.
