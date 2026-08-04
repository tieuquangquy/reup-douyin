# Publication Metrics Collector Job V1

The collector job turns publication measurement into durable background work without
coupling the worker to Facebook, TikTok or YouTube response shapes.

## Flow

```text
POST metric-collection-jobs
  -> validate confirmed publication and account
  -> create idempotent COLLECT_PUBLICATION_METRICS job
  -> worker claim / retry / resume
  -> collector adapter read
  -> idempotent PublicationMetricSnapshot
  -> growth summary
```

Enqueue API:

```http
POST /platform-publications/{publication_id}/metric-collection-jobs
```

`collection_key` identifies one intended observation slot. Repeating the same key and
payload returns the existing job. Reusing the key with different metrics fails closed.

## Resume and idempotency

Each job writes a snapshot with:

```text
metric-collection-job:{job_id}
```

If the snapshot was committed but the worker crashed before the step completed, the next
execution returns that snapshot before resolving or calling a collector. Provider reads
are safe to retry, but this guard also preserves quota.

## Retry and cooldown

- transient provider/network errors use bounded exponential backoff;
- explicit provider `Retry-After` and account cooldown times are honored exactly;
- terminal configuration, held-account, invalid payload and unsupported-provider errors
  fail without retry;
- concurrency is capped per workspace;
- stale jobs are recoverable by the normal worker lock/heartbeat mechanism.

Metrics-specific cooldown is stored in account metadata as
`metrics_collection_cooldown_until`. It does not overwrite the account's global publish
cooldown, so an insights-only quota issue does not silently rewrite routing policy. A
pre-existing global account cooldown is still respected.

## Enabled adapters

`LOCAL_MOCK` accepts normalized test metrics and makes no network request. It exists for
PostgreSQL/worker regression and must remain clearly marked in snapshot provenance.
Both enqueue and worker execution reject this adapter when `APP_ENV=production`, including
jobs inserted through the generic job API.

`FACEBOOK_GRAPH` is the first real provider adapter. It is fail-closed and requires an
explicit Facebook account identity, server-side token reference, account capability flag
and `external_network_authorized=true` on the request. Tokens are resolved only during
worker execution and sent in an authorization header, never in the URL or persisted
state. Missing provider fields remain unavailable rather than becoming zero.

The implementation and network-free PostgreSQL fixture pilot are complete. A live call
is still blocked operationally until the exact Page, media object, Graph version and
insights scopes have been verified. The read-only controlled-live preflight endpoint
returns explicit blocker codes without resolving credentials or using the network. See
`docs/facebook-reels-insights-adapter-v1.md` for the contract and live-read checklist.
The same gate runs at enqueue and worker execution, so a caller cannot bypass it by using
the generic collection endpoint.

Every additional real provider adapter requires:

- official insights API and scopes for the target account;
- server-side token resolution without logging or persisting credentials;
- sanitized provider summaries;
- error mapping for auth, rate-limit, unavailable and removed-media states;
- provider contract tests with recorded, secret-free fixtures;
- explicit operator authorization for the account being queried.

Adaptive recurring planning is implemented separately in
`docs/publication-metrics-cadence-v1.md`. Its worker sweep remains disabled by default
until a real provider adapter is authorized.

## Configuration

```text
METRICS_COLLECTION_MAX_CONCURRENT_RUNNING=2
METRICS_COLLECTION_STALE_RUNNING_SECONDS=300
METRICS_COLLECTION_RETRY_BACKOFF_BASE_SECONDS=60
METRICS_COLLECTION_RETRY_BACKOFF_MAX_SECONDS=3600
METRICS_COLLECTION_RATE_LIMIT_COOLDOWN_SECONDS=900
```

## Non-goals

- automatic live Facebook authorization or scheduler activation;
- TikTok/YouTube insights calls;
- scoring, topic classification or affiliate eligibility;
- click/order/commission attribution;
- automatic external publishing or commenting.
