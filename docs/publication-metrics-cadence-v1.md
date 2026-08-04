# Publication Metrics Cadence Scheduler V1

The cadence scheduler decides when each confirmed publication should be measured again.
It persists the decision as `PublicationMetricSchedule`; it does not hide scheduling state
inside publication metadata or an in-process timer.

## Authority

One schedule belongs to one `PlatformPublication` and records:

- `ACTIVE`, `PAUSED`, `COMPLETED` or `BLOCKED` status;
- collector and policy version;
- next collection time;
- last enqueued job and completed snapshot;
- collection count and consecutive flat intervals;
- bounded decision history;
- collector configuration and explicit external-network authorization decision.

The worker sweep is only a dispatcher. Every external/read operation remains a durable
`COLLECT_PUBLICATION_METRICS` job with its own retry and resume behavior.

## Adaptive policy

Base cadence by publication age:

| Age | Base interval |
| --- | ---: |
| Under 6 hours | 1 hour |
| 6–24 hours | 3 hours |
| 24–72 hours | 12 hours |
| 72 hours to configured limit | 24 hours |
| At/after configured limit | Complete schedule |

Adaptation:

- `GROWING`: half the base interval, with a 30-minute floor;
- `FLAT`: exponential backoff up to 4× and at most 48 hours;
- `COUNTER_REGRESSION`: recheck within at most 3 hours;
- missing/baseline data: use the age-band interval.

Repeated sync of the same snapshot is idempotent: it does not increment collection or
flat counters twice. Pause/resume decisions preserve the superseded adaptive decision in
a bounded 20-entry history.

## API

```http
PUT  /platform-publications/{publication_id}/metric-schedule
GET  /platform-publications/{publication_id}/metric-schedule
GET  /analytics/metric-schedules
POST /analytics/metric-schedules/dispatch-due
POST /publication-metric-schedules/{schedule_id}/pause
POST /publication-metric-schedules/{schedule_id}/resume
```

Each due slot becomes a deterministic collection key containing the schedule id and slot
timestamp. Concurrent dispatchers therefore converge on one job through the existing job
idempotency constraint.

## Worker safety

```text
METRICS_SCHEDULER_ENABLED=false
METRICS_SCHEDULER_SWEEP_INTERVAL_SECONDS=60
METRICS_SCHEDULER_DISPATCH_LIMIT=20
```

The feature flag defaults to `false`. `LOCAL_MOCK` is rejected when `APP_ENV=production`
at enqueue and execution boundaries. `FACEBOOK_GRAPH` schedules are supported only for
an exact capable Facebook account and retain the explicit network authorization decision,
but adapter availability does not automatically enable recurring external calls.

The sweep:

- runs on a slow monotonic clock rather than every worker poll;
- is safe across multiple workers because collection jobs are idempotent;
- respects account and metrics cooldowns through the collector job;
- swallows scheduler errors so publishing/media jobs continue;
- uses a dispatch limit to prevent queue storms.

## Current non-goals

- automatic live Facebook authorization or scheduler activation;
- TikTok/YouTube insights adapters;
- automatic enabling of the scheduler;
- content scoring and topic classification;
- affiliate eligibility, clicks, orders or commission attribution.
