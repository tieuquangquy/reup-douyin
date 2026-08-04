# Ops Control Tower

The Ops Console uses three distinct operational surfaces:

- `/ops/health` answers whether the observed system can process work safely and where triage is required.
- `/ops/jobs` is the durable operational worklist.
- `/ops/users` is the workspace access ledger.

## Home V9 creative command center

`/ops` is a progressive-disclosure landing surface rather than another analytics table:

- A restrained status header explains the current condition and data check time without a decorative hero.
- The status header, three decision instruments, and operational-domain ribbon share one asymmetric command stage.
- A data-bound status beacon and subtle depth effects provide visual identity without inventing historical signals.
- Exactly three decision metrics stay above the fold: critical signals, oldest queued work, and busy-worker evidence.
- Pipeline workload is the dominant shared-scale stacked horizontal bar chart, preserving queued, running, review, retryable, and failed states.
- The incident queue remains a ranked action list because severity, age, context, and recommended action are more useful than a chart.
- Publish outcomes use seven daily stacked columns so volume and outcome mix can be compared together.
- Failure signatures use Pareto bars, and Douyin fetch health uses account-ranked blocked-rate bars.
- Dependency readiness uses explicit status rows plus a numeric storage headroom bar. Missing telemetry remains `not observed`.
- Dependency readiness is arranged as a layered system stack (control plane, execution, media runtime, and external/publishing), while its state remains text-labelled and color-independent.
- A connected hidden-risk strip adds four evidence-backed checks that ordinary totals miss: running-job observability coverage, potentially stuck work, retry amplification, and cross-record integrity debt.
- The command stage includes an admission verdict: `Safe to accept new work`, `Accept with guardrails`, or `Pause new work`.
- Donut charts and the decorative production topology are intentionally removed.

The V9 home continues to use `/ops/home-summary` as its sole authority and does not compose legacy endpoints in the browser.

## Health V2 diagnostic cockpit

`/ops/health` is the evidence drill-down behind Home rather than a second summary wall:

- The command chamber uses the canonical admission verdict and explains why new work is safe, guarded, or paused.
- Decision evidence uses one diagnostic canvas rather than KPI cards: an incident focus sits beside a connected Queue → Observability → Workers execution path, while storage capacity and integrity evidence share the foundation strip.
- Dependency readiness uses the backend probe results from `/ops/home-summary`, arranged along the control, execution, media, and external system spine. The browser no longer invents storage or provider health from record counts.
- The dependency drill-down renders those four architecture layers as a balanced 2×2 system map. Triage shows the five highest-priority incidents and progressively discloses any remaining signals instead of creating an internal scrollbar.
- The hidden-risk ledger preserves heartbeat coverage, type-aware stuck-work evidence, true retry claims, and database-contract integrity gaps.
- Detailed job, risk, fetch, asset, and publish panels continue to use their specialist metrics authorities.
- Zero queue and zero publish activity render explicit neutral states instead of empty axes or unexplained dashes.

## Authority rules

- Job status totals come from `/ops/metrics`, never from the currently loaded page of `/jobs`.
- Job search, status, type, and pagination are applied by `/jobs` so UI filters do not silently exclude unloaded rows.
- A running job's worker signal comes from `locked_by` and `locked_at`. `started_at` is not a heartbeat.
- Observability coverage counts only running jobs with both a worker lock and a heartbeat newer than that job type's stale-lock policy. `updated_at` is not treated as proof of progress.
- Potentially stuck work means a running job has no complete lock evidence or has exceeded its type-specific heartbeat threshold.
- Job `attempts` counts worker claims. Retry amplification is `(first claims + retry claims) / jobs claimed`, where retry claims are `max(attempts - 1, 0)`.
- Health labels retries using the `retry_claims` evidence segment; it does not present total worker claims as retry count.
- Integrity debt is limited to database-contract gaps the system can prove: missing Douyin account attribution in the latest 200 fetch runs, review-ready/approved renders without a media asset, and published drafts without a canonical publish attempt.
- Admission control pauses on critical execution/dependency evidence, accepts with guardrails when risk or required telemetry remains uncertain, and reports safe only when all checked admission signals are clear.
- Queue health includes `oldest_queued_at`, running jobs with/without a visible lock, and distinct active worker count.
- API and database rows on Health mean only that the metrics request and its database query completed. They are observed signals, not independent availability probes.
- Redis and idle-worker liveness remain explicitly `not observed` until dedicated probes are introduced.
- Disk capacity and FFmpeg availability use fast local read-only probes; no private storage path is returned.
- The Users page labels refresh-token issuance as `last sign-in`, not generic last activity.

## Safety rules

- The backend prevents an owner/admin from disabling or demoting their own account below Ops access.
- Existing last-active-owner protection remains authoritative.
- The UI hides owner assignment from non-owners and disables destructive access toggles when the target is protected.
- The trash action on `/ops/jobs` calls `DELETE /jobs/{job_id}` and hard-deletes the `jobs` row plus its `job_steps`; the UI then reloads the canonical database-backed list instead of only hiding the row locally.
- Before deletion, every nullable foreign key to `jobs.id` is detached. Media, render, queue, analytics, classification, affiliate, and publishing records are retained; render provenance keeps the deleted job id in metadata.
- A `RUNNING` job with an active worker lock cannot be deleted. The operator must cancel it and wait for the worker lock to clear, preventing an in-flight worker from writing into a deleted job.

## Known follow-ups

- Dedicated Redis, storage read/write, provider, GPU, and worker-instance probes.
- Time-series snapshots for queue age, throughput, failure rate, and P50/P95 latency.
- Workspace audit events, active session count, and MFA posture for the Users ledger.
