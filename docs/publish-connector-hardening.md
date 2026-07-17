# Publish Connector Hardening

Step 19 hardens the first real connector, Facebook Reels for Pages. The goal is operational clarity after a real external side effect, not a broad social publishing platform.

## Why This Step Exists

Publishing can succeed externally while local state is stale, or fail locally after Facebook has already accepted an upload reference. The system must preserve uncertainty instead of mapping weak evidence to success or failure.

## Hardened Boundaries

```text
PublishDraft
  -> PublishGateService
  -> PublishAttemptService
  -> PublishConnector
  -> PublishReconciliationService
  -> PublishLifecycleService
```

- `PublishConnector` maps transport requests/responses.
- `PublishAttemptService` creates and runs actual attempts.
- `PublishReconciliationService` refreshes external state and handles stale/uncertain attempts.
- `PublishLifecycleService` syncs latest/canonical publication state back to `PublishDraft`.

## Phase 1 Hardening Choices

- No new `PlatformPublication` table yet. `PublishAttempt` plus `PublishDraft` current/canonical fields are enough for minimal post-publish tracking.
- No automatic scheduler yet. Operators can manually refresh attempt status or reconcile a draft.
- No analytics. Only external ids, permalink, external status, and last checked time are tracked.
- No webhook flow yet. Pull-based refresh is simpler and debuggable for local-first operation.

## Operator-Facing Outcomes

An operator should be able to tell:

- which attempt is latest;
- which attempt is canonical published output;
- which attempt failed without external side effects;
- which attempt needs reconciliation;
- what external id/permalink/status Facebook returned.

