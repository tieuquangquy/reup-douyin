# Publish Attempt Lifecycle

`PublishDraft` describes publish metadata. `PublishAttempt` records each actual attempt to publish to a platform.

## Statuses

- `QUEUED`: attempt record exists but execution has not started.
- `RUNNING`: orchestration is validating and preparing publish.
- `UPLOADING`: media upload is in progress.
- `PUBLISHING`: platform publish/finalize is in progress.
- `AWAITING_PLATFORM_CONFIRMATION`: reserved for future polling/webhook flows.
- `SUCCEEDED`: platform accepted the publish.
- `FAILED`: attempt failed with error code/message.
- `NEEDS_RECONCILIATION`: the attempt has a platform reference but the final platform state is not confirmed.
- `RECONCILING`: a status refresh is currently checking platform state.
- `RECONCILED`: a previously ambiguous attempt has been checked against the platform.
- `CANCELLED`: reserved for future cancellation support.

## Flow

```text
PublishDraft READY
  -> gate/account/render validation in API
  -> PublishAttempt QUEUED
  -> PUBLISH_CONTENT durable job
  -> worker executes the pre-created attempt
  -> RUNNING
  -> UPLOADING
  -> PUBLISHING
  -> SUCCEEDED, FAILED, or NEEDS_RECONCILIATION
```

The HTTP publish action returns the queued attempt and does not upload media inline.
Confirmed external posts are materialized separately as `PlatformPublication` rows; see
`docs/publishing-foundation-v2.md`.

On confirmed success, the publish draft status becomes `PUBLISHED`. On failure without any external reference, the draft becomes `FAILED` and the failed attempt carries the failure details.

If an upload/publish call fails after Facebook has returned a video/reel reference, the attempt moves to `NEEDS_RECONCILIATION`. The draft moves to `NEEDS_ATTENTION` until an operator refreshes status or manually investigates the Page.

## Reconciliation

```text
NEEDS_RECONCILIATION
  -> RECONCILING
  -> RECONCILED / NEEDS_RECONCILIATION
```

`POST /publish-attempts/{id}/refresh-status` asks Facebook for the current external status.

- `PUBLISHED` marks the attempt `RECONCILED` and makes it canonical for the draft.
- `FAILED` or `NOT_FOUND` marks reconciliation as resolved failure.
- `PROCESSING`, `UNKNOWN`, or `PARTIALLY_CONFIRMED` keeps the attempt in `NEEDS_RECONCILIATION`.

## Traceability

Each attempt stores:

- attempt number
- platform account id
- external media/reel ids
- external status/permalink
- reconciliation status
- request summary
- response summary
- warning summary
- error code/message

This keeps retries and duplicate-click handling clear.

## API

- `POST /publish-drafts/{id}/publish`
- `GET /publish-attempts`
- `GET /publish-attempts/{id}`
- `POST /publish-attempts/{id}/refresh-status`
- `GET /publish-drafts/{id}/publish-status`
