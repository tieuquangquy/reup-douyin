# Phase 17E Modal Operator Guide

## Goal

Use a currently open Douyin profile modal to test the current video and start Smart Capture & Harvest even when the popup shows Session: missing.

## Preconditions

- You are on a supported Douyin tab.
- The URL is a profile modal URL such as:
  - https://www.douyin.com/user/PROFILE_ID?modal_id=AWEME_ID
- Backend shows yes for Smart Capture & Harvest.
- Detector shows ready.
- Content script is ready.
- Four-point calibration is saved for the modal layout.

## Test Current Video

1. Open the popup while the Douyin video modal is visible.
2. Confirm Page shows modal and Detector shows ready.
3. Click Test Current Video.
4. Expected result:
   - The popup shows Test status PASS.
   - Current aweme and Target aweme match the URL modal_id.
   - Duration seconds, Like, Comment, Favorite, and Share are populated.
   - Data integrity shows passed.

Test Current Video does not create a Capture Inbox item, does not require a capture session, does not require a harvest plan, and does not flush to the backend.

## Smart Capture & Harvest from a Modal with Missing Session

1. Stay on the modal URL.
2. Click Smart Capture & Harvest.
3. Expected bootstrap:
   - Popup shows Preparing harvest plan from this modal's profile.
   - The extension strips modal_id from the URL to resolve the profile URL.
   - The extension builds a harvest plan through the harvest-plan endpoint.
   - The extension returns to the original modal URL.
   - If targets exist, harvest starts using the stored target queue.
   - If no targets exist, the popup shows No new or incomplete videos found.

## Common Messages

- modal_id_missing: The current URL/document does not expose a modal id. Open a video modal from the profile grid.
- Calibrate 4 Points first: Calibration is missing or invalid. Run Calibrate 4 Points on the modal video.
- modal_metrics_timeout: The modal id or metrics did not become stable in time. Wait for the modal to load and try Test Current Video again.
- data_integrity_mismatch: The before/after/extracted aweme ids did not match the current modal id. Do not proceed with harvest until the modal is stable.
- calibrated_point_read_failed: Calibrated point extraction could not read all required metrics. Recalibrate the four points and retry.

## Live Retest Checklist

1. Open a Douyin modal URL with modal_id.
2. Verify the popup reports Page: modal, Backend: yes, Detector: ready, Session: missing, Calibration: calibrated.
3. Click Test Current Video.
4. Confirm PASS and populated duration/like/comment/favorite/share metrics.
5. Click Smart Capture & Harvest.
6. Confirm the popup prepares a harvest plan from the modal profile and does not show capture-session missing.
7. Confirm the extension returns to the original modal URL after profile queue resolution.
8. Confirm harvest starts when targets exist, or completed noop is shown when there are no eligible targets.
