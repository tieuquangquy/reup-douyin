# Facebook Reels Insights Adapter V1

## Status and scope

`FACEBOOK_GRAPH` is implemented as the first real publication-metrics adapter. It reads
official Facebook video insights into the platform-neutral
`PublicationMetricSnapshot` model. The adapter is code-complete and has a network-free
PostgreSQL fixture pilot, but live access is **not enabled automatically**.

A live read still requires operator verification of the exact Page, media object, Graph
API version, token type and approved insights permissions. Metric availability varies by
API version, account type and media object, so fixture success is not evidence that a
specific Page is authorized.

This adapter does not publish, comment, attach affiliate products, rotate accounts or
attempt to bypass platform protections.

## Durable flow

```text
operator/API authorization
  -> validate confirmed Facebook publication and exact active account
  -> enqueue idempotent COLLECT_PUBLICATION_METRICS job
  -> resolve token reference inside the worker only
  -> GET /{media-id}/video_insights with Bearer authorization
  -> normalize allowlisted lifetime metrics
  -> persist one idempotent PublicationMetricSnapshot
  -> recompute growth deltas and adaptive cadence
```

The job payload contains the account/publication identifiers, collector name and the
authorization decision. It never contains the resolved token. A persisted snapshot is
looked up before any provider-facing guard or credential resolution, so crash recovery
does not spend quota or fail because an account was placed on hold after the snapshot
commit.

## Fail-closed account configuration

The exact `PlatformAccount` must satisfy all of the following:

- platform is `FACEBOOK_REELS`;
- status is `ACTIVE` and the account is not on hold;
- `external_account_id` identifies the Page/account explicitly;
- `token_reference` explicitly names a server-side environment variable;
- `metadata_json.metrics_insights_enabled` is exactly `true`;
- the enqueue/schedule request sets `external_network_authorized=true`.

The token is resolved from the referenced environment variable only inside worker
execution. It is sent in the `Authorization: Bearer ...` header, never in the URL. Raw
credentials, cookies and provider error text are excluded from logs, job payloads,
snapshots and provider summaries.

Optional account metadata:

| Key | Default | Purpose |
| --- | --- | --- |
| `graph_api_version` | `v20.0` | Version used for the Graph request; verify before live use. |
| `facebook_insights_metrics` | views, view time, complete views | Allowlisted metric names to request. |
| `facebook_insights_object_id_source` | first available external reference | Force `external_publish_id`, `external_media_id` or `external_reel_id`. |
| `facebook_view_time_unit` | `milliseconds` | Convert provider view time to canonical seconds; set `seconds` only when verified. |

Unknown metric names are removed by the allowlist. An empty effective list fails with
`metrics_configuration_invalid` rather than issuing a broad provider request.

## V1 normalization

Default Facebook fields map as follows:

| Facebook insight | Canonical snapshot field |
| --- | --- |
| `total_video_views` / `post_video_views` | `view_count` |
| `total_video_view_time` / `post_video_view_time` | `total_watch_time_seconds` |
| `total_video_complete_views` / `post_video_complete_views_organic` | completion numerator |
| `total_video_reactions_by_type_total.like` / `like_count` | `like_count` |
| `comment_count` | `comment_count` |
| `share_count` | `share_count` |
| `save_count` | `save_count` |
| video impressions | `impression_count` |
| `reach` | `reach_count` |

Completion rate is calculated only when both a positive view count and complete-view
count are returned. Missing provider fields remain `null`, appear in
`unavailable_metrics`, and produce `PARTIAL` quality. The adapter never substitutes zero
for unavailable data.

## Failure and retry behavior

- HTTP 429 and Graph codes `4`, `17`, `32`, `613`: retryable rate limit; honor
  `Retry-After` and set an insights-only account cooldown.
- HTTP 401/403 and Graph codes `10`, `190`, `200`: terminal auth/permission failure.
- HTTP 404 and Graph code `100`: terminal media-reference failure.
- connection/provider 5xx failures: bounded retry.
- invalid JSON/response shape, credentials, account capability and configuration errors:
  terminal operator action.

Sanitized provider errors retain only HTTP status and Graph error code/subcode.

## Network-free PostgreSQL pilot

From `apps/api`:

```powershell
python -m scripts.run_facebook_insights_fixture_pilot
```

An optional exact publication can be selected:

```powershell
python -m scripts.run_facebook_insights_fixture_pilot --publication-id <uuid>
```

The pilot uses PostgreSQL and the real enqueue/`JobRunner`/snapshot path. It injects an
in-memory fixture transport with no URL or socket implementation, temporarily enables
the account capability, supplies a random dummy token through the configured environment
reference, then restores account metadata and the environment. It asserts exactly one
provider call, resume reuse and absence of the dummy token in persisted artifacts.

## Before the first live call

Run the read-only controlled-live preflight before enqueueing a real collection job:

```http
POST /platform-publications/{publication_id}/facebook-insights-live-preflight
```

```json
{
  "operator_confirmation": "FACEBOOK_INSIGHTS_LIVE_PILOT_APPROVED",
  "expected_platform_account_id": "<account-uuid>",
  "expected_external_account_id": "<facebook-page-id>",
  "expected_media_id": "<facebook-reel-or-video-id>",
  "required_scopes": ["read_insights", "pages_read_engagement"]
}
```

The response is sanitized and always records `network_used=false`. It does not resolve
the token. `ready_for_live_job=true` requires all account/publication checks and the
following explicit attestations:

- account metadata:
  - `metrics_insights_enabled=true`;
  - `facebook_insights_token_type=PAGE_ACCESS_TOKEN`;
  - `facebook_insights_verified_external_account_id` equals the persisted Page id;
  - `facebook_verified_insights_scopes` contains at least `read_insights` and
    `pages_read_engagement`;
  - `facebook_insights_scopes_verified_at` is timezone-aware and no older than 30 days;
- publication metadata:
  - `facebook_insights_verified_media_id` equals the configured external object id;
  - `facebook_insights_object_verified_at` is timezone-aware and no older than 30 days.

Demo/local identifiers, non-Facebook permalinks, active cooldown/hold and an enabled
metrics scheduler block the one-shot pilot. This prevents a demo publication or recurring
scheduler from accidentally consuming the first authorized live request.

The same preflight is enforced again at both collection enqueue and worker execution.
Calling the older metric-collection endpoint directly cannot bypass it. Only the injected
fixture pilot disables this guard through an internal constructor flag; normal API and
worker construction always uses the fail-closed default.

1. Confirm the exact Page/account and external Reel/video object id.
2. Verify the current official Graph API endpoint, version and metric names for that
   object type.
3. Verify the Page token type and required insights permissions with a least-privilege
   token; do not reuse browser cookies.
4. Set a dedicated `token_reference` environment variable and enable
   `metrics_insights_enabled` only on that account.
5. Run one operator-authorized collection job with the scheduler still disabled.
6. Review snapshot quality, unavailable metrics, provider codes and Page audit logs.
7. Enable adaptive scheduling only after quota behavior and revocation handling are
   confirmed.

`METRICS_SCHEDULER_ENABLED` remains `false` by default. Enabling a real adapter does not
implicitly authorize recurring external calls.
