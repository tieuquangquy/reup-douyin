# Publish Reconciliation Flow

Reconciliation handles uncertain or stale publish attempts without guessing platform state.

## Status Model

Internal attempt statuses:

- `SUCCEEDED`: connector returned confirmed publish success.
- `FAILED`: no usable external reference or platform confirmed failure.
- `NEEDS_RECONCILIATION`: local result is uncertain and an external reference exists.
- `RECONCILING`: a refresh is currently checking platform state.
- `RECONCILED`: a previous uncertain state has been resolved.

External publication statuses:

- `UNKNOWN`
- `PROCESSING`
- `PUBLISHED`
- `FAILED`
- `REMOVED`
- `NOT_FOUND`
- `PARTIALLY_CONFIRMED`

## Rules

### Internal Succeeded

If the connector returns `SUCCEEDED` and external status `PUBLISHED`, the attempt becomes canonical for the draft.

### Failed With External Reference

If a request fails after Facebook returns a video/reel id, the attempt moves to `NEEDS_RECONCILIATION`. Operators should refresh status before retrying.

### Failed Without External Reference

If no external reference exists, the attempt is a normal `FAILED` attempt and can be retried once the root cause is fixed.

### Stale Running Attempt

If an active attempt is older than the phase 1 threshold:

- with an external reference: mark `NEEDS_RECONCILIATION`;
- without an external reference: mark `FAILED` with `stale_attempt_state`.

### Duplicate Successful Attempts

Multiple published attempts are surfaced as a warning. The canonical attempt is the latest confirmed published attempt by timestamp and attempt number.

## APIs

```http
POST /publish-attempts/{publish_attempt_id}/refresh-status
POST /publish-drafts/{publish_draft_id}/reconcile
GET /publish-drafts/{publish_draft_id}/publish-history
GET /publish-drafts/{publish_draft_id}/publication-summary
```

Manual refresh checks one attempt. Draft reconciliation checks uncertain or stale attempts for the draft and then syncs the draft current/canonical state.

## Operator Interpretation

- `latest` means the newest attempt and may still be failed or uncertain.
- `canonical` means the attempt currently treated as the real published output.
- `external_status` is platform evidence; it should not be confused with internal orchestration status.
- `NEEDS_RECONCILIATION` means do not blindly retry until the platform state is refreshed or checked manually.
