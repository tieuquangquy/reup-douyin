# Canonical Publish Success Model

Each `PublishDraft` can have many `PublishAttempt` rows, but only one canonical published attempt.

## Definitions

- `latest attempt`: most recent attempt by creation/attempt order.
- `canonical attempt`: the current best confirmed published attempt.
- `current publication`: the platform state copied to `PublishDraft` from the canonical attempt, or latest attempt when no canonical success exists.

## Selection Rule

The canonical attempt is selected from attempts with external status `PUBLISHED`. If multiple exist, the latest by completion/check timestamp and attempt number wins.

If no external `PUBLISHED` attempt exists, a `SUCCEEDED` or `RECONCILED` attempt may be used only when it is the best available confirmed success.

## Draft Lifecycle

- publish starts: `PublishDraft.PUBLISHING`
- confirmed success: `PublishDraft.PUBLISHED`
- latest attempt uncertain: `PublishDraft.NEEDS_ATTENTION`
- failed without canonical success: `PublishDraft.FAILED`
- no attempts or no current publish state: draft stays ready/draft according to its metadata workflow

## Retry Rule

Retrying a draft creates a new `PublishAttempt`. It does not delete previous attempts. If a retry accidentally creates another published post, the duplicate success warning surfaces in the publication summary.

## Why No Separate PlatformPublication Yet

For phase 1, `PublishDraft` and `PublishAttempt` hold enough state. A separate `PlatformPublication` table should be added later only if the product needs cross-draft publication management, analytics, takedown sync, or multi-account reporting.
