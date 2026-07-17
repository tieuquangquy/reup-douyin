# Phase 17V Operator Guide

## Purpose

Use `Whole Profile Staged Harvest V2` when you already verified a Douyin profile queue and want finalized items written to Capture Inbox without legacy Harvest / Smart Capture conflicts.

## Preconditions

- Douyin page is available in the active tab.
- Modal whole-profile `Verify only` has completed successfully.
- `Verified target count` is greater than zero.
- Right-rail `Calibrate 4 Points` is valid.
- Backend API is reachable at the configured API base URL.

## Steps

1. In the extension popup, open `Advanced / Beta`.
2. Select `Verify only` and run `Test Modal → Whole Profile Harvest` if no verified queue exists.
3. Confirm the verified queue exists and belongs to the current profile.
4. Run `Calibrate 4 Points` if prompted.
5. In `Limit first N writes`, keep `first 3` for a safe first production write test, or choose `first 1`, `first 5`, or `all`.
6. Click `Run Staged Harvest V2`.
7. Monitor `Whole Profile Staged Harvest V2`.
8. After `Flushed` increases and backend response is shown, refresh Capture Inbox if needed.

## Expected progress panel

The V2 panel reports:

- Status
- Phase
- Current target
- Current aweme
- Updated
- Skipped
- Failed
- Flushed
- Last backend status
- Last backend response short
- Last error

Rows show per-target outcome, aweme id, duration, likes, comments, favorites, and shares when extraction succeeds.

## Important warnings

- Do not start legacy Smart Capture / Harvest while V2 is running. The extension blocks those starts with `Whole Profile Staged Harvest V2 is running. Stop it before using legacy Harvest.`
- V2 does not create visible Capture Inbox rows locally. Rows appear only after backend `/douyin-extension/full-modal-harvest` accepts finalized payloads.
- V2 does not fake posted text or views. It writes calibrated detail metrics and verified profile-card evidence only.
