# Job Lifecycle

`jobs.status` and `job_steps.status` use related but separate lifecycle vocabularies. Jobs represent high-level orchestration; steps represent ordered units of execution.

## Job Statuses

```text
QUEUED
RUNNING
WAITING_FOR_REVIEW
FAILED
RETRYABLE
CANCELLED
COMPLETED
```

## Expected Job Flow

```text
QUEUED
  -> RUNNING
  -> COMPLETED
```

Jobs that need operator input can move from `RUNNING` to `WAITING_FOR_REVIEW`, then resume later. Failed work should become `RETRYABLE` when another attempt is allowed, or `FAILED` when it needs intervention or has exhausted attempts.

## JobStep Statuses

```text
PENDING
RUNNING
WAITING_FOR_INPUT
FAILED
SKIPPED
COMPLETED
```

## Retry And Resume Expectations

- `jobs.attempts` and `jobs.max_attempts` define retry budget.
- `jobs.idempotency_key` prevents duplicate scheduling for the same logical operation.
- `jobs.locked_by` and `jobs.locked_at` reserve room for distributed worker leases.
- `job_steps.step_key` is unique within a job so a worker can resume from known progress.
- `payload_json`, `context_json`, `input_json`, `output_json`, `result_json`, `metadata_json`, and error summary fields provide traceability without adding premature step-specific tables.

## Reference Model

Jobs may link directly to:

- `source_video_id`
- `crawl_session_id`
- `render_output_id`

They also include `reference_type` and `reference_id` for future objects that should not force a schema rewrite at this stage.

## Current Scope

Step 3 adds service-level transition validation, progress calculation, placeholder step execution, and minimal API controls. It still does not implement a Redis queue, real media pipeline, crawler, OCR, STT, TTS, render, or UI dashboard.
