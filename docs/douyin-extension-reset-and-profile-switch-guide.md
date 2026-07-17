# Douyin Extension Reset and Profile Switch Guide

## Reset Options

Use Reset current run when the same profile collection is stuck or paused and you want to keep the current queue/session plan. This preserves queue, classification, Capture Inbox session linkage, settings, and calibration.

Use Rescan this profile when the same Douyin profile needs a fresh local collection plan. This clears local scan results, classification, queue, counters, progress, and session linkage, then asks you to scan the profile again. It does not delete backend Capture Inbox data.

Use Start new profile when switching to another Douyin profile. This clears old local profile state and visible counters so the next scan builds a new collection plan for the active profile. Calibration and settings are preserved.

Full local reset dev only is reserved for development cleanup and should not be used for normal profile switching.

## Safe Collection Guard

Before Start Collecting, the extension verifies that the active tab profile still matches the scanner state. If the profile changed, collection is blocked with:

`Profile changed. Scan this profile before collecting.`

This prevents reusing the old queue or old Capture Inbox session for a different Douyin profile.

## Expected New Profile Flow

1. Open the new Douyin profile tab.
2. Click Reset.
3. Choose Start new profile.
4. Confirm the local profile state clear.
5. Click Scan Profile to build the new collection plan.
6. Use Batch Next 10 / Start Collecting only after the new profile scan completes.
