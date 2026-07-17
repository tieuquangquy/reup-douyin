# Crawl Fail Runbook

## Symptoms

- `CRAWL_PROFILE` job is `FAILED` or `RETRYABLE`.
- Crawl session status is `FAILED`.
- No new `SourceVideo` rows after submitting profile ingest.

## Common Causes

- Invalid or unsupported profile URL.
- Adapter normalization failed.
- Mock/live adapter returned unexpected payload.
- Persistence error while upserting profile/video.

## Checks

- `GET /jobs/{job_id}` for `error_code` and failed step.
- `GET /crawl-sessions/{crawl_session_id}` for `error_message`, `raw_summary_json`, `result_summary_json`.
- Confirm `source_platform = DOUYIN`.
- Check adapter docs: `docs/source-adapter-architecture.md`.

## Immediate Handling

- For `invalid_url`, fix profile URL and submit again.
- For adapter fetch failure, retry only after confirming network/provider state.
- For normalization failure, keep raw payload for parser update.

## Rerun / Decision

- Rerun if failure is transient or URL was corrected.
- Mark needs_fix if payload shape changed and parser needs code update.
- Reject only if the source profile is unsupported for Phase 1.
