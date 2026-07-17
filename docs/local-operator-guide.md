# Local Operator Guide

This guide is the shortest path for running the Phase 1 system locally after dependencies are installed.

## Daily Start

From repo root:

```powershell
.\scripts\dev-doctor.ps1
.\scripts\dev-migrate.ps1
.\scripts\dev-reseed.ps1
.\scripts\dev-start.ps1
```

Open:

- Web: `http://localhost:3000`
- API docs: `http://127.0.0.1:8000/docs`
- Operational metrics: `http://127.0.0.1:8000/ops/metrics`

Stop local services:

```powershell
.\scripts\dev-stop.ps1
```

## Operator Demo Path

1. Open `/` to see the Operator Studio home dashboard (metrics, action queue, quick launch).
2. Open `/selection/review-board` and inspect candidate score, risk, and status.
3. Open the transcript editor at `/production/transcript-editor/{source_video_id}`.
4. Open final review at `/production/final-review/{source_video_id}`.
5. Open publish drafts at `/publishing/drafts` or a specific draft at `/publishing/drafts/{draft_id}`.
6. Check warnings and risk decisions before marking a publish draft ready.
7. Open the Ops Console at `/ops` for operational health, jobs, publish control, and risk.

## Running A Pilot Session

Before a real pre-beta session, create a report folder:

```powershell
.\scripts\new-pilot-report.ps1 -Name pilot-001
```

Use:

- `docs/operator-pilot-workflow.md` for the daily operator process
- `docs/pre-beta-test-plan.md` for validation suites
- `docs/bug-bash-plan.md` for stress scenarios
- `docs/issue-taxonomy-and-triage.md` for severity and triage
- `docs/go-no-go-criteria.md` before deciding whether to build a publish connector

## When Something Fails

Use this order:

1. Run `.\scripts\dev-doctor.ps1`.
2. Check `GET /ops/metrics` for failed job counts, retryable backlog, and common error codes.
3. Open the relevant runbook under `docs/runbooks/`.
4. Retry only jobs that are `FAILED` or `RETRYABLE` and whose inputs still exist.
5. If a render or publish draft is blocked by risk, review `docs/runbooks/publish-draft-risk-blocked.md`.

## Local Boundaries

Phase 1 uses local disk storage and a local worker loop. The API and worker still go through the same storage, job, manifest, and provider abstractions that can later point to object storage and distributed queues.
