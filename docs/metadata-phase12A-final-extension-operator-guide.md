# Phase 12A Final Extension Operator Guide

## Purpose

This guide describes the final Phase 12A Douyin extension workflow for local operator capture and calibrated Smart Capture & Harvest.

## Normal buttons

The popup intentionally shows only production actions.

Primary:

1. `Smart Capture & Harvest`

Calibration:

2. `Start Right Rail Calibration`
3. `Probe Current Modal Metrics`
4. `Show Calibration`
5. `Clear Calibration`

Control:

6. `Resume Harvest`
7. `Stop Harvest`
8. `Flush Pending`
9. `Show Progress`

Advanced:

10. `Capture current page only`

Legacy CDP/debug actions are not part of normal operation.

## First-time setup per layout

1. Open Douyin in the tab where the extension content script is active.
2. Open a video modal.
3. Click `Start Right Rail Calibration`.
4. Click the five requested points in order:
   1. Like count.
   2. Comment count.
   3. Favorite count.
   4. Share count.
   5. Next video/down arrow button.
5. If the layout changes, recalibrate.

The stored calibration version is `phase12a_calibrated_five_point_workflow`.

## Smart Capture & Harvest from profile page

1. Open the Douyin profile page.
2. Click `Smart Capture & Harvest`.
3. The extension captures the page and creates/updates a Capture Inbox session.
4. If no modal is open, the popup enters `modal_required`.
5. Open the first video modal.
6. Click `Resume Harvest` or run `Smart Capture & Harvest` from the modal.
7. The extension probes the current modal.
8. If Probe is PASS, harvesting starts.

## Smart Capture & Harvest from modal page

1. Open the target Douyin video modal.
2. Confirm five-point calibration exists. If unsure, click `Show Calibration`.
3. Click `Probe Current Modal Metrics`.
4. Confirm Probe PASS.
5. Click `Smart Capture & Harvest` or `Resume Harvest`.
6. Keep the modal open while the harvest is running.

## What is extracted

For each modal item, the production path extracts:

- `aweme_id` from current modal/video identity.
- `duration_seconds` from the active video element duration.
- Like count from calibrated point.
- Comment count from calibrated point.
- Favorite count from calibrated point.
- Share count from calibrated point.

Accepted PASS sources are only:

- `calibrated_point_dom`
- `calibrated_point_ocr`
- `mixed_calibrated_point`

## Navigation behavior

After extracting and queueing/flushing the current item, the extension clicks the calibrated `next_video_button` point and waits for the `modal_id` to change. If no next point exists, Smart Capture & Harvest blocks and asks you to recalibrate with five points. If no next video is available, pending items flush and the harvest stops safely.

## Progress panel

Use `Show Progress` to view:

- Current phase.
- Current index.
- Current `aweme_id`.
- Harvested/updated/failed/flushed counts.
- Last extracted metrics.
- Current navigation/probe/flush state.
- Error or stopped reason when applicable.

## Viewport behavior

Douyin page viewport comes from the content script. The popup does not use its own small popup dimensions as the page viewport. If the content-script viewport is unavailable, refresh the Douyin tab and retry. A valid content-script viewport should not show stale `viewport_changed_significantly` warnings.

## Troubleshooting

- `Next video point missing. Recalibrate with five points.`: rerun calibration and click the next/down button as the fifth point.
- `content_script_viewport_unavailable`: refresh the Douyin tab, wait for the page to load, then retry.
- Probe WARN/FAIL: confirm modal is open, video duration is available, and the calibrated count points still land on visible count labels.
- Stale probe: rerun Probe on the current modal; stored PASS from a different `modal_id` is not reused.

## Live retest steps

1. Reload the unpacked extension from `apps/extension-douyin-capture/dist`.
2. Open a Douyin profile page.
3. Confirm only the ten production buttons render.
4. Click `Smart Capture & Harvest`.
5. Confirm profile capture completes and state becomes `modal_required`.
6. Open the first video modal.
7. Click `Start Right Rail Calibration` and select all five points.
8. Click `Probe Current Modal Metrics` and confirm PASS.
9. Click `Resume Harvest`.
10. Confirm one item extracts with duration and all four metrics.
11. Confirm the extension clicks the calibrated next point.
12. Confirm harvesting continues only after `modal_id` changes.
13. Click `Show Progress` and confirm phase/index/metrics are updated.
14. Click `Stop Harvest` or let it finish; confirm pending items are flushed safely.