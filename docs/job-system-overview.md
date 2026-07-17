# Job System Overview

The job system is the durable orchestration layer for long-running work. It exists so future crawl, download, OCR, STT, TTS, render, export, and publish preparation can plug into the same state/progress foundation.

## Core Relationship

```text
Job
  -> JobStep(validate_input)
  -> JobStep(fetch_source)
  -> JobStep(persist_assets)
  -> JobStep(finalize)
```

`jobs` stores the high-level unit of work. `job_steps` stores ordered progress within that job. The API creates and controls jobs; the worker claims runnable jobs and executes steps through handlers.

## Responsibilities

- `JobService`: create/list/detail/retry/cancel/resume and safe state changes.
- `job_state_machine`: valid job and step transitions.
- `job_templates`: step sequence registry per `JobType`.
- `job_progress`: consistent progress calculation.
- `JobRunner`: claim and execute jobs with pluggable step handlers.
- `apps/worker`: local polling runtime using placeholder handlers in Phase 1.

## Supported Job Types

```text
CRAWL_PROFILE
SCORE_CANDIDATES
DOWNLOAD_VIDEO
ANALYZE_AUDIO
ANALYZE_OCR
BUILD_TRANSLATION_DRAFT
SYNTHESIZE_TTS
RENDER_PREVIEW
RENDER_FINAL
```

Some early job steps still use placeholders, but selected service-backed handlers now exist in `JobRunner`, including `CRAWL_PROFILE/finalize_session`, download asset registration, audio/TTS/render persistence, publish persistence, and reconciliation updates.

## API Surface

```text
POST /jobs
GET /jobs
GET /jobs/{job_id}
POST /jobs/{job_id}/retry
POST /jobs/{job_id}/cancel
POST /jobs/{job_id}/resume
```

List jobs supports filters for `status`, `job_type`, and `source_video_id`.

## Progress Rules

- `total_steps` is the number of generated steps.
- `completed_steps` counts only `COMPLETED`.
- `failed_steps` counts `FAILED`.
- `SKIPPED` contributes to percent completion but is not counted as completed.
- `progress_percent` is equal-weighted across steps.
- Running step progress contributes partial progress.
- All completed/skipped steps makes job progress `100`.

## Adding A Job Type

1. Add the new enum value in `JobType`.
2. Add an Alembic migration for the PostgreSQL enum.
3. Add a step sequence in `STEP_TEMPLATES`.
4. Add placeholder or real handlers through `StepHandlerRegistry`.
5. Add tests for transitions/progress if behavior differs from the default runner.

## Current Limits

- No Redis queue backend yet.
- No distributed scheduler.
- No media/crawler/OCR/STT/TTS/render logic.
- No UI dashboard.
- No auth or workspace permissions around job APIs yet.
