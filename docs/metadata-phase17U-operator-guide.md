# Phase 17U Operator Guide

## Goal

Use Run Staged Harvest to convert a verified Modal Whole Profile target queue into finalized backend capture items safely.

This guide applies only to the Phase 17U staged production harvest path.

## Before you start

Confirm:

- the backend API is running,
- the extension base URL points to the backend,
- the Douyin tab is logged in and usable,
- the target profile is open in a modal video URL,
- right-rail calibration has been completed,
- no unrelated safe harvest run is already active.

## Required live flow

1. Open any modal URL from the intended Douyin profile.
2. Open the extension popup.
3. In the advanced Modal Whole Profile area, choose Verify only.
4. Click Test Modal → Whole Profile Harvest.
5. Wait until the verified target count is shown.
6. Choose Dry-run random 3.
7. Click Test Modal → Whole Profile Harvest again.
8. Confirm all three dry-run targets open by direct modal URL and extract expected detail metrics.
9. Click Run Staged Harvest.
10. Watch the harvest progress panel until the run finishes or stops for operator action.

## Expected messages

### Missing verified queue

```text
Run Verify only first.
```

Meaning: Run Verify only on the current profile before production harvest. Phase 17U intentionally does not auto-scan when the verified queue is missing.

### Missing calibration

```text
calibration_missing
```

Meaning: Complete right-rail calibration before production harvest.

### All targets already complete

```text
skipped_existing_complete
```

Meaning: Harvest-plan classification found no eligible targets after skipping complete backend items.

### Backend schema rejection

```text
backend_schema_rejected
```

Meaning: The backend rejected the finalized payload schema. Stop and inspect diagnostics before retrying. Do not continue producing writes until the schema issue is fixed.

## What Run Staged Harvest does

Run Staged Harvest:

- reuses the verified target queue from Verify only,
- checks that the current profile matches the verified profile,
- checks calibration,
- asks the backend harvest-plan endpoint which verified targets are new or incomplete,
- skips complete items by default,
- opens each target using direct `modal_id` navigation,
- extracts detail metrics from the modal,
- attaches profile-card evidence where available,
- flushes finalized-only batches to the backend,
- updates progress after backend outcomes are known.

## Metrics collected per finalized target

The staged harvest expects calibrated detail extraction for:

- duration,
- like count,
- comment count,
- favorite count,
- share count.

If detail extraction cannot validate the target identity, the item should fail or pause rather than creating a bad finalized backend item.

## Evidence attached when available

The staged harvest carries profile-card evidence from the verified queue, including:

- source URL,
- profile-card text fields,
- candidate validation marker,
- target index,
- profile-card source URL,
- backend profile-card evidence returned by harvest-plan.

View/post evidence is included only when it is truthfully available in the verified evidence or backend evidence payload.

## Stop and resume

Use Stop Harvest if:

- Douyin shows a captcha/login wall,
- the modal does not change correctly,
- metrics look wrong,
- backend diagnostics show repeated failures,
- you need to pause the local run.

To resume:

1. Keep or return to the same Douyin profile/modal context.
2. Click Resume Harvest.
3. Confirm progress continues from remaining targets.

Already completed targets should not be repeated during normal resume.

## Backend-write safety rules

- Dry-run random 3 does not write finalized backend items.
- Run Staged Harvest writes only finalized items.
- Backend complete items are skipped by default.
- Backend 422 schema rejection pauses the run.
- Capture Inbox and Tile Gallery should be trusted only after backend success.

## Recommended first live retest

Use a small profile or a profile with a known verified queue.

1. Verify only.
2. Dry-run random 3.
3. Run Staged Harvest.
4. Stop after the first backend flush.
5. Confirm committed count and backend inbox records.
6. Resume.
7. Confirm remaining targets continue without duplicate writes.
8. Confirm complete backend items are skipped in a second staged run.

## Troubleshooting

### Button is disabled

Check whether another popup action is running. Wait for the action to finish or reopen the popup.

### Staged harvest starts but no eligible targets remain

The backend may already mark all verified targets complete. This is expected when `skip_existing_complete` is true.

### Resume opens the wrong profile

Return to a modal URL on the same verified profile. If the profile is uncertain, run Verify only again.

### Metrics look shifted or incorrect

Recalibrate the right rail, rerun Dry-run random 3, then run staged harvest again.

### Backend rejects schema

Keep the paused run state, capture the backend error body, fix the schema mismatch, rerun verification commands, then resume or restart from Verify only.
