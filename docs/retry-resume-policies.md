# Retry And Resume Policies

This document captures the Phase 1 operational rules for jobs, assets, and reruns.

## Job Retry

Retry is allowed only when the job status is `FAILED` or `RETRYABLE`, the job is still marked retryable, and attempts are below `max_attempts`.

Current behavior:

- failed steps are reset to `PENDING`
- step errors are cleared
- the job returns to `QUEUED`
- progress is recalculated from completed steps

Retry should be used when the underlying input is still valid and the failure looks transient or fixable, for example storage write failure, provider timeout, or missing temporary dependency.

## Job Resume

Resume is for paused work, not arbitrary failed work.

Current behavior:

- `RETRYABLE` job resumes to `QUEUED`
- `WAITING_FOR_REVIEW` job resumes to `RUNNING`
- step `WAITING_FOR_INPUT` resumes to `RUNNING`

Use resume when the operator has completed a checkpoint, resolved a warning, or restored an expected asset.

## Cancel

Cancel is valid for active jobs. Pending, running, and waiting steps are marked `SKIPPED`. Completed historical outputs are not deleted automatically.

## Rerun And Current Outputs

- Media assets keep historical versions where useful and mark the latest intended output with `is_current`.
- Render outputs should keep old records for trace/debug; current/latest selection should be explicit in API responses and UI.
- Publish-ready on media does not mean publish metadata is ready.
- A new render can make an older publish-ready decision stale; the operator should final-review the new render before preparing publish draft.

## Idempotency

- Demo seed uses stable external identifiers and should be safe to rerun.
- Jobs can use `idempotency_key` for duplicate prevention where the caller has a stable operation key.
- Asset registration should avoid duplicate current assets with the same logical type/version.

## Known Phase 1 Limits

- No Redis-backed distributed locking yet.
- Local worker claim behavior is suitable for one operator/local machine.
- Provider-level retry taxonomy is still lightweight.
- Temp cleanup is conservative; failed artifacts may remain for debugging.

