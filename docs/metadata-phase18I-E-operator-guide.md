# Phase 18I-E Operator Guide

## Before running

1. Open the target Douyin profile page in the active tab.
2. Click **Verify Profile** and confirm verified targets are present.
3. Complete the required calibration state before starting harvest.
4. Keep the tab on a valid Douyin page with the extension content script active.
5. Expect this phase to stay extraction-only: no backend record creation, no capture-session creation, and no Capture Inbox side effects.

## Run Harvest

Click **Run Harvest** in the Whole Profile Harvest panel. The active Phase 18I-E queue continues to use:

- mode: `new_and_incomplete`
- batch limit: `10`
- speed: `safe`
- execution path: `real_modal_extraction_no_backend`

The run opens direct modal targets from the verified profile queue, extracts finalized modal metrics, checkpoints each processed target locally, and keeps all progress in [`douyinWholeProfileHarvest`](apps/extension-douyin-capture/src/wholeProfileHarvest/state.ts:529).

## Safety scheduler behavior

During Phase 18I-E, the queue intentionally slows itself down and may pause even when no extraction error has happened yet:

- randomized waits happen between targets based on the selected speed policy from [`delayPolicyForSpeed()`](apps/extension-douyin-capture/src/wholeProfileHarvest/canonicalHarvest.ts:174)
- scheduled pauses occur after a configured number of processed targets
- consecutive extraction failures are tracked and can trigger a safety stop/pause boundary
- stop requests are honored during waits and pauses, so the operator can halt without allowing another target to start

## What the popup shows

The popup progress summary now exposes Phase 18I-E safety state from [`wholeProfileProgressSummary()`](apps/extension-douyin-capture/src/wholeProfileHarvest/progress.ts:3), including:

- harvest pause message
- resume availability
- last safety event
- captcha/checkpoint summary
- captcha evidence text
- consecutive error counters
- processed-since-last-pause count
- scheduled pause status
- active delay status
- tab health status
- resume check status

If the harvest is paused for safety reasons, the popup banner uses the operator-facing pause message from [`runWholeProfileControllerAction()`](apps/extension-douyin-capture/src/popup.ts:356) instead of generic success text.

## Captcha, checkpoint, login, or abnormal traffic

If Douyin shows a captcha, login wall, checkpoint, abnormal traffic warning, or access-denied page, the run pauses.

Operator steps:
1. Stay in the same active Douyin tab.
2. Solve the captcha/checkpoint/login requirement manually.
3. Confirm the tab is back on the expected Douyin profile/modal context.
4. Click **Resume Harvest**.

Do not reset the harvest unless you intentionally want to discard the current local queue checkpoint state.

## Tab health pause

The run also pauses if the tab is no longer considered safe for extraction. Common reasons include:

- the content script is missing
- the tab navigated away from the expected Douyin page
- the active page context is unsupported for the next extraction step

When this happens:
1. Return the active tab to the expected Douyin page.
2. Make sure the extension can access the page again.
3. Use **Resume Harvest** after the tab looks healthy.

## Resume

Resume continues only from persisted local harvest state. It uses the queued checkpoint and `resume_from_index` rather than legacy runtime memory or V2 staged harvest state.

This means you can stop for operator action, resolve the issue, and continue from the next pending target instead of restarting the entire profile queue.

## Stop

Click **Stop Harvest** if you need to halt intentionally. The run is expected to move into a paused state with resume still available for pending queue work. Because stop is checked during waits and safety pauses, you do not need to race the scheduler before the next target begins.
