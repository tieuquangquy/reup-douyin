# Publication Metrics V1

Publication Metrics V1 records how a confirmed `PlatformPublication` changes after it
goes live. It is a measurement authority, not a content score or affiliate decision.

## Data model

Each `PublicationMetricSnapshot` belongs to one `PlatformPublication` and stores:

- the platform observation time (`observed_at`), separately from database creation time;
- a caller-supplied idempotency key and canonical payload hash;
- cumulative views, likes, comments, shares and saves;
- optional impressions, reach, follower gain and watch-time metrics;
- collection source, provider schema version, estimated flag and data-quality label;
- sanitized provider summary and metadata without credentials or raw auth payloads;
- derived interval, deltas, view velocity and engagement rates.

The unique boundary is:

```text
platform_publication_id + idempotency_key
```

Retrying the same key and payload returns the existing snapshot. Reusing a key with a
different payload fails with `metric_snapshot_idempotency_conflict`.

## Correct handling of time series

Snapshots may arrive late or out of order. After insertion, the service sorts the full
publication series by `observed_at` and recomputes adjacent deltas. This prevents a late
backfill from leaving the next snapshot with a stale velocity.

Platform counters can decrease after moderation, privacy changes or provider corrections.
The raw signed delta is retained, `counter_regression_detected` is set, and view velocity
is withheld for that interval. Downstream scoring must not treat that interval as normal
negative growth.

## API

```http
POST /platform-publications/{publication_id}/metric-snapshots
GET  /platform-publications/{publication_id}/metric-snapshots
GET  /platform-publications/{publication_id}/growth-summary
```

The write API is an ingestion boundary for manual imports, tests and future collectors.
It does not call a social platform.

## Security and observability

- provider summaries containing token, authorization, cookie, password or secret keys are rejected;
- logs include publication and snapshot ids, never credentials or local media paths;
- `data_quality` and `is_estimated` travel with every snapshot;
- the growth summary reports measurement age so stale data is visible to later operators and scoring.

## Durable collector boundary

`COLLECT_PUBLICATION_METRICS` now provides the durable worker boundary. Enqueueing creates
one idempotent job; the worker normalizes collector output into this snapshot authority.
If a worker resumes after the snapshot commit, it finds the job-derived snapshot key and
does not call the provider again.

The only enabled adapter is `LOCAL_MOCK`, which is explicitly network-free. Fetching from
Facebook, TikTok or YouTube remains disabled until a real insights adapter, OAuth scopes
and an exact account authorization are configured. See
`docs/publication-metrics-collector-v1.md`.

## Explicit non-goals

- real provider API/OAuth insights implementation;
- cross-platform normalization score;
- topic classification;
- affiliate eligibility or product matching;
- clicks, orders, commission and revenue attribution;
- automatic publish or comment actions.
