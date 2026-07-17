# Phase 17C Safe Runner Operator Guide

## What Changed

Douyin modal harvest now uses the content-script Safe Runner. The popup is a controller and status panel only. Closing or reopening the popup must not stop the run.

## Starting a Run

1. Open the Douyin profile tab.
2. Confirm the extension is connected.
3. Confirm four-point right-rail calibration exists.
4. Run Smart Capture & Harvest.
5. The popup should show `Runtime: Safe Runner`.
6. The runner opens target modals directly with `?modal_id=<aweme_id>` and advances target by target.

## Expected Progress

A healthy run should move through specific phases, for example:

- Opening target modal
- Waiting for target modal
- Extracting target metrics
- Flushing target to backend
- Marking target updated after backend commit
- Safe Runner advancing queue

The runner should not sit on generic `Harvesting...` for normal target processing.

## Pauses That Are Expected

Only these pause reasons should be treated as valid:

- `operator_stop`
- `backend_flush_failed`
- `content_script_unavailable`
- `calibration_invalid`
- `captcha_required`
- `consecutive_failures`
- `harvest_loop_inactive`

If the backend is down, pending metrics are preserved and the run pauses with `backend_flush_failed`. Start the backend and resume/retry flush from the popup.

## Live Retest Steps

1. Start backend locally.
2. Load/reload the unpacked extension build.
3. Open a Douyin profile with at least several target videos.
4. Run Capture current page or Smart Capture & Harvest so the backend returns a target queue.
5. Confirm the popup title includes `Runtime: Safe Runner`.
6. Confirm Chrome local storage has `douyinSafeHarvestRun` with schema `phase17c_safe_runner`.
7. Watch targets advance from 1 to 2 to 3 without clicking Resume after each success.
8. Close the popup during the run, wait several targets, reopen it, and confirm progress is still running from the canonical state.
9. Stop once and confirm pause reason is `operator_stop`.
10. Resume and confirm it continues at the first pending target.
11. Turn backend off for one target and confirm pause reason is `backend_flush_failed` with pending preserved.
12. Turn backend back on, resume/retry, and confirm the run completes as `completed` or `completed_with_warnings`.
