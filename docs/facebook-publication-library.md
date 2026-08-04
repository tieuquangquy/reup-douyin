# Facebook Publication Library

## Purpose

The Publication Library is the canonical workspace history of content that exists on an external platform. A `PlatformPublication` is an external fact and can exist without an internal publish draft or publish attempt.

This keeps three responsibilities separate:

- **Accounts** at `/publishing/accounts` owns Facebook Page connection, OAuth capabilities, operator holds, cooldowns, and publishing safety on the same Operator Studio session.
- **Publish Drafts** owns content preparation before publishing.
- **Publication Library** owns external Reel discovery, import, optional draft linking, and post-publish metrics.

## Operator workflow

1. Connect a Facebook Page in `/publishing/accounts`.
2. Open `/publishing/publications`.
3. Select the connected Page and choose **Sync Reels**.
4. Import the Reels that should be tracked locally.
5. Optionally link an imported publication to its internal draft.
6. Run the Insights readiness check for a selected publication.
7. Explicitly authorize and queue one read-only Insights collection.
8. Optionally authorize **Automatic Insights tracking** for 24 hours, 72 hours, or 7 days; pause or resume it from the same publication inspector.
9. Use the **Tracking Monitor** tab to review all Page schedules, identify delayed or blocked collection, and open the affected publication.
10. Use **Classification Queue** to classify caption/transcript/OCR evidence, then approve or override the topic before affiliate matching.

Reel discovery and import do not publish, edit, or delete Facebook content. The API resolves the Page token server-side and never returns it to the browser.

## Import outcomes and recovery

- A successful import creates one `FACEBOOK_DISCOVERY` publication and immediately marks the discovered Reel as imported in the UI.
- Import is idempotent. Retrying the same Reel refreshes the existing local publication instead of creating a duplicate.
- Concurrent duplicate inserts recover by returning the publication that won the database race.
- Graph may return a relative permalink such as `/reel/{id}`. The API normalizes it to an absolute `https://www.facebook.com/...` URL before validation and persistence.
- Relative protocol URLs and non-Facebook hosts remain rejected.
- FastAPI field-validation details are surfaced by the web client so the operator sees the failing field instead of a bare HTTP 422.
- Page/workspace mismatches, missing Pages, invalid credentials, and insufficient read permissions remain fail-closed.
- Import does not download the Reel media, create a publish attempt, advance warm-up, link a draft automatically, or start Insights collection.

## Publication origins

- `CONNECTOR_PUBLISH`: created from a confirmed system connector publish.
- `EXISTING_REEL_IMPORT`: manually registered historical evidence.
- `FACEBOOK_DISCOVERY`: discovered from the connected Page through the Graph API.

Only confirmed `CONNECTOR_PUBLISH` records advance Facebook warm-up. Historical or discovered Reels cannot increase trust automatically.

## Staged Facebook warm-up

The effective publish cadence is calculated server-side:

- `PILOT`: at most 2 attempts per 24 hours, with 360 minutes between attempts.
- `OBSERVE`: available after the configured minimum age and 2 confirmed connector publishes; at most 3 attempts per 24 hours, with 180 minutes between attempts.
- `STANDARD`: available after the configured minimum age and 5 confirmed connector publishes; normal configured limits apply.

An operator cannot manually promote a Page. Holds, unresolved attempts, connector failures, missing scopes, expired capabilities, and cooldowns continue to fail closed.

## Insights boundary

Insights collection remains opt-in and publication-scoped. The UI first runs a read-only preflight. A one-shot read and an automatic tracking window use separate confirmations: approving **Collect once** never enables recurring reads, and creating a schedule requires the exact `FACEBOOK_INSIGHTS_AUTO_TRACKING_APPROVED` confirmation.

Insights preflight accepts either a safe environment-variable reference or a valid encrypted `platform-credential://` OAuth reference. It never resolves or exposes the token. When blocked, Publication Library shows only the failed checks and their backend messages; when ready, it shows the explicit one-shot authorization control.

After **Collect once**, Publication Library polls the durable job and shows `QUEUED`, `RUNNING`, `RETRYABLE`, `COMPLETED`, `FAILED`, or `CANCELLED` with distinct colors. A completed job automatically reloads the growth summary and metric snapshots; a failed job surfaces its safe operator message instead of leaving empty counters unexplained.

If a job remains `QUEUED` for 30 seconds without an attempt, the UI changes from the normal waiting state to a worker-delay warning. Local development workers are launched by `scripts/dev-start.ps1` inside a small supervisor loop; if the Python worker exits unexpectedly, the host restarts it after three seconds while durable PostgreSQL job state remains intact.

The Facebook collector uses `post_video_view_time` for modern Graph versions and reads Reel `views`, `likes.summary(true)`, and `comments.summary(true)` from the video object. This avoids treating the retired `total_video_view_time` parameter as a missing media object. Unsupported Graph fields are reported as parameter errors, while genuine missing-object responses remain terminal media-reference failures.

`Views/hour` is a derived velocity, not a provider counter. The first snapshot is always a baseline. `PUBLICATION_METRICS_V2` withholds velocity until the newest sample has a prior anchor at least 30 minutes old, then uses the newest qualifying anchor instead of the immediately previous snapshot. Frequent manual collections therefore still refresh absolute counters without amplifying a one-view change over a few minutes into a misleading hourly rate. Counter regressions remain fail-closed and hide velocity until a later sample confirms direction.

On the first successful read, the UI says **Baseline saved** rather than the generic **Insights updated**. If Facebook returns only a subset of interaction counters, engagement is explicitly described as a lower bound; `0.00%` must not imply that unavailable share/save counters were confirmed as zero.

## Automatic Insights tracking V1

- One durable `PublicationMetricSchedule` exists per publication; scheduler sweep is enabled, but only `ACTIVE` opt-in schedules are dispatched.
- A new schedule starts immediately when there is no baseline. If a recent baseline exists, the first automatic read waits until the 30-minute stable-velocity boundary instead of spending an extra request.
- `METRICS_CADENCE_V2` schedules the first baseline follow-up at 30 minutes, prioritizes growing videos with a 30-minute floor, and backs off flat videos to longer intervals.
- The tracking horizon starts at operator activation, not the Reel's historical Facebook publish time, so imported older Reels can still be tracked for the selected window.
- Pause clears the next collection time without deleting evidence. Resume respects the stable-measurement boundary. Completed tracking requires a new explicit authorization to restart.
- Terminal collection/configuration failures move the schedule to `BLOCKED`; retryable provider failures remain governed by the durable job retry and cooldown policy.
- Publication Library polls an active schedule every 15 seconds and reloads growth/snapshots when `last_metric_snapshot_id` changes.

Worker crashes and stale locks consume the same retry budget as normal provider failures. Recovery must transition the job to `FAILED` once `max_attempts` is exhausted; it must never requeue an orphaned Insights job indefinitely. Unexpected provider or credential exceptions are converted to a sanitized `metrics_unhandled_error` and cannot expose token data through the job API.

For local development, a relative `platform_credential_local_key_path` is resolved from the `apps/api` root rather than the process working directory. This ensures the API and local worker use the same server-only encryption key even though they are launched from different app folders.

## Tracking Monitor V1

The `Tracking Monitor` tab is an operator-level view over all publication metric schedules. It keeps publication management and monitoring on the same route without adding another navigation destination.

- KPI cards summarize active schedules, collections due within 15 minutes, schedules needing attention, paused/completed schedules, and snapshots created today.
- Page, schedule status, health, and text filters are applied server-side.
- Health is derived centrally as `HEALTHY`, `WAITING`, `DELAYED`, `COOLDOWN`, `BLOCKED`, `PAUSED`, or `COMPLETED`; the browser does not reimplement scheduler rules.
- The aggregated response includes the latest growth summary and latest job per schedule to avoid frontend N+1 requests. Snapshot history is loaded only when the detail drawer opens.
- Pause and resume preserve existing evidence. Opening a monitor row switches Publication Library to the owning Page and selects the exact publication.
- The monitor polls every 15 seconds. A queued job older than 120 seconds, a running job older than 300 seconds, or a collection overdue by more than five minutes is visibly marked for attention.

This view is operational tracking, not an analytics chart or business outcome score. Topic classification, affiliate fit, and conversion attribution remain separate future workflow steps.

## API contracts

- `GET /platform-accounts/{id}/facebook-reels`
- `POST /platform-publications/facebook-discovery-import`
- `PATCH /platform-publications/{id}/draft-link`
- `GET /platform-publications`
- `PUT|GET /platform-publications/{id}/metric-schedule`
- `POST /publication-metric-schedules/{id}/pause`
- `POST /publication-metric-schedules/{id}/resume`
- `GET /analytics/metric-tracking-monitor`
- Existing publication metric snapshot, growth summary, preflight, and one-shot collection endpoints

Cursor values are opaque. Graph API next-page URLs and access tokens must never cross the API boundary.
