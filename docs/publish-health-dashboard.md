# Publish Health Dashboard

The publish health dashboard is an operator view for post-publish operations.

Route:

```text
/dashboard/publish-health
```

Primary API:

```http
GET /analytics/publish-health?window=last_7_days
```

## Panels

- Overview cards: success rate, canonical published count, reconciliation backlog, ready backlog, risk-blocked count.
- Account health: attempts, success rate, failures, and reconciliation count by Page/account.
- Failure insights: grouped error categories.
- Operator action queue: drafts needing reconciliation, drafts ready to publish, recent successful publications.
- Pipeline outcome hints: grouped by source profile, niche, and preset.
- Feedback form: quick quality/confidence/root-cause note for recent publications.

Each publication row links back to the publish draft workflow so the dashboard remains action-oriented instead of becoming a passive report.

## Time Windows

Supported windows:

- `today`
- `last_7_days`
- `last_30_days`

Custom range is supported at API level for publish health, but the phase 1 UI keeps controls simple.

## Operator Use

The operator should check this dashboard after publishing batches:

1. Clear reconciliation backlog.
2. Investigate accounts with repeated failures.
3. Publish ready drafts if risk gates are clear.
4. Add feedback to recent publications.
5. Use source/preset hints to decide the next review batch.
