# Phase 17S Dry-Run Sampling Operator Guide

## Purpose

Use Modal Whole Profile dry-run modes to validate detail extraction against a verified profile target queue without creating backend writes or visible Capture Inbox items.

## Recommended Workflow

1. Open a Douyin modal URL for the target profile.
2. Run `verify_only` from the Modal Whole Profile beta panel.
3. Confirm the panel shows a verified target queue with a non-zero verified target count and a verification timestamp.
4. Select one dry-run mode:
   - `dry_run_first_n` samples the first verified targets.
   - `dry_run_last_n` samples the last verified targets.
   - `dry_run_random_n` samples deterministically from verified targets only.
   - `dry_run_specific_ids` samples only IDs that exist in the verified target queue.
5. Run the beta action again and review sampled indexes, sampled aweme IDs, pass/fail rows, and queue behavior.

## Expected Reuse Message

When a valid verified target queue exists, the panel should show:

```text
Using verified target queue. No profile rescan.
```

In this path, dry-run should not navigate back to the profile for scanning, should not start the profile scanner, should not call harvest-plan again, and should not show `profile_scan_start_failed`.

## Expected Fallback Message

When no valid verified queue exists, the panel should show:

```text
Verifying profile before dry-run...
```

The extension will run the same verification pipeline first. If verification succeeds, it stores verified targets and continues into dry-run sampling. If verification fails, the dry-run failure reason should be `verify_failed_before_dry_run`.

## Specific IDs

For `dry_run_specific_ids`, enter IDs separated by spaces, commas, or newlines. IDs not present in the verified target queue are reported as `invalid_specific_ids`; they are not opened as modal targets.

## No-Write Guarantee

Dry-run detail extraction does not call full-modal-harvest and does not create backend Capture Inbox items. It writes only the isolated `douyinModalWholeProfileTestRun` state for diagnostics and operator review.
