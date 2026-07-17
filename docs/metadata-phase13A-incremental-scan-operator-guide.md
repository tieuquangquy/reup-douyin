# Phase 13A Incremental Scan Operator Guide

## Default Workflow

1. Open a Douyin profile page.
2. Leave Smart harvest mode set to `New + incomplete (default)`.
3. Click `Smart Capture & Harvest`.
4. Review the Details panel counts:
   - Total found
   - New
   - Incomplete
   - Already complete
   - Skipped
   - Harvest target
5. If Harvest target is greater than zero, the normal calibration/probe/harvest workflow continues.
6. If Harvest target is zero, the extension reports `No new or incomplete videos found.` and does not open modal harvest.

## Harvest Modes

- `New + incomplete (default)`: process only new or incomplete videos. Use this for repeated profile scans.
- `New only`: process only videos that do not exist in canonical storage.
- `Refresh all captured videos`: explicitly reprocess every captured unique video from the current profile scan.

## Retest Steps

1. Capture a Douyin profile with at least one visible video.
2. Confirm the Details panel shows scan counts and a Harvest target count.
3. Run Smart Capture & Harvest and confirm progress uses `X / Harvest target`, not the full profile count.
4. Capture the same profile again after videos are complete.
5. Confirm complete videos are listed as Already complete and skipped by the default mode.
6. Select `New only` and confirm only new videos are targeted.
7. Select `Refresh all captured videos` and confirm all captured unique `aweme_id`s are targeted.
8. For a scan with no new or incomplete targets, confirm no modal harvest starts and the status says `No new or incomplete videos found.`