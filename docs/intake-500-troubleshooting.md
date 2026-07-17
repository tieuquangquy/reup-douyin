# Intake 500 Troubleshooting

## Previous Failure

The reproduced generic 500 came from a Python `TypeError` in the canonical discovery flow:

```text
SourceIngestService.ingest_profile() got an unexpected keyword argument 'adapters'
```

This was a wiring bug between `IntakeDiscoveryService` and `SourceIngestService`.

## Expected Behavior After Fix

`/intake` should now either:

- complete successfully
- or return a structured error with:
  - `code`
  - `message`
  - `stage`
  - `diagnostics_id`

## How To Debug Future Intake Failures

1. Capture the UI error banner text.
2. Note the `diagnostics_id` if present.
3. Check the failing `stage`.
4. If a crawl session was created, inspect intake run history and fetch observability.
5. Confirm the selected Douyin account:
   - exists
   - is usable for live fetch
   - has valid session material

## Common Classified Failure Categories

- `account_resolution_failed`
- `imported_session_invalid`
- `missing_required_headers`
- `fetch_client_construction_failed`
- `login_required`
- `blocked_response`
- `parse_failed`
- `normalize_failed`
- `persistence_failed`
- `zero_videos`
- `zero_candidates`
- `unknown_server_error`

## V1 Limitations

- Real Douyin responses can still vary by session quality, network conditions, or anti-bot behavior.
- Manual imports still depend on the imported session material being complete enough for canonical fetch.
