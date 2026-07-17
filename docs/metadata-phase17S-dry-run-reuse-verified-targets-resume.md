# Phase 17S Dry-Run Reuse Verified Targets Resume

## Current Phase 17S State

The Modal Whole Profile beta runtime now separates verification from dry-run detail extraction.

## Runtime Cache

A successful Verify Only run stores a reusable queue in `douyinModalWholeProfileTestRun`:

```json
{
  "verified_profile_url": "https://www.douyin.com/user/...",
  "verified_at": "2026-05-04T00:00:00.000Z",
  "verified_targets": ["aweme_id"],
  "verified_target_details": [
    {
      "aweme_id": "aweme_id",
      "index": 1,
      "profile_card_evidence": {}
    }
  ],
  "verified_target_count": 1,
  "verified_scan_diagnostics": {}
}
```

## Resume Rules

- Verify Only remains the only normal path that scans the profile and builds the harvest-plan queue.
- Dry-run modes first load and normalize the verified target cache.
- If the cache is valid and profile-matched, dry-run resumes at sampling/detail extraction and displays `Using verified target queue. No profile rescan.`
- If the cache is missing or profile-mismatched, dry-run displays `Verifying profile before dry-run...` and runs verification before sampling.
- If verification fails before dry-run, the failure reason is `verify_failed_before_dry_run`.

## Sampling State Mapping

- `verify_only` maps to `dry_run_sampling_mode = null`.
- `dry_run_first_n` maps to `first_n`.
- `dry_run_last_n` maps to `last_n`.
- `dry_run_random_n` maps to `random_n`.
- `dry_run_specific_ids` maps to `specific_ids`.
- Persisted stale state where `dry_run_sampling_mode = verify_only` is normalized when a dry-run mode is selected.

## Operator-Safe Failure Reasons

- `no_verified_targets`
- `verify_failed_before_dry_run`
- `invalid_specific_ids`
- `dry_run_sample_empty`

`profile_scan_start_failed` should only appear when the verify pipeline itself actually fails to start scanning, not when a reusable verified queue exists.
