# apps/worker

Python background worker for long-running `reup-douyin` jobs.

## Responsibility

- Own future crawl, download, scoring, localization, rendering, export, and publishing execution.
- Make long-running work observable, durable, retryable, resumable, and idempotent where possible.
- Use storage, queue, and provider abstractions so local Phase 1 can evolve into distributed SaaS execution.

## Boundaries

- Do not expose HTTP UI/API contracts directly from the worker.
- Do not store secrets in code.
- Do not assume only one worker process forever.

## Worker Skeleton

The worker now has a local polling runtime that can claim queued/retryable jobs from PostgreSQL and execute placeholder step handlers through the shared job orchestration service.

This is not a real media/crawl pipeline yet. It exists so future crawl, OCR, STT, TTS, and render handlers can plug into the orchestration foundation without rewriting job state management.

Run shape for local development later:

```powershell
python src/main.py
```

Run this from `apps/worker` after API/worker dependencies are installed and `DATABASE_URL` is configured.

Each stable `WORKER_ID` owns an OS-level singleton lock under
`.dev/worker-locks`. This prevents an unclosed worker from an older code build
from continuing to claim jobs after the development stack is restarted. The
lock is released automatically if the process exits or crashes. Set
`WORKER_LOCK_DIR` only when the default repository-local runtime directory is
not writable.

## Current Status

Worker skeleton only. No Redis queue backend, crawler, OCR, STT, TTS, render, or publishing logic has been implemented.
