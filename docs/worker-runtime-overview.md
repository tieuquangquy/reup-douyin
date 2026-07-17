# Worker Runtime Overview

The Phase 1 worker runtime is a local polling skeleton. It is intentionally small so the job system can be validated before adding Redis queues or real media processing.

## Runtime Flow

```text
LocalPollingWorker
  -> JobRunner.claim_next_job()
  -> JobRunner.run_job()
  -> StepHandlerRegistry.get(job_type, step_key)
  -> StepHandler.handle(job, step)
  -> JobService updates Job and JobStep state
```

## Claiming

The worker looks for jobs in `QUEUED` or `RETRYABLE`, orders by priority and creation time, and uses `FOR UPDATE SKIP LOCKED` for future multi-worker safety on PostgreSQL.

## Step Handlers

Handlers implement:

```text
handle(job, step) -> StepHandlerResult
```

The default handler is a placeholder that immediately completes the step and writes a small output payload. The current `JobRunner` also contains focused service-backed handlers for selected real steps, including `CRAWL_PROFILE/finalize_session`, which calls `SourceIngestService`. Additional real handlers for download, OCR, STT, TTS, and render can continue to plug in by job type and step key.

## Stop Conditions

The runner stops a job when:

- a step returns `WAITING_FOR_INPUT`
- a step returns `FAILED`
- all steps complete

## Local-First, SaaS-Ready

Phase 1 can run one local worker loop. The service layer and database fields already leave room for:

- distributed worker locks
- retry attempts
- resumable steps
- queue backend replacement
- dashboard polling

## Current Limits

- No Redis queue consumer.
- No real crawl/download/OCR/STT/TTS/render handlers.
- No heartbeat or stale lock recovery.
- No worker concurrency control beyond one local loop.
