# Publish Retry And Idempotency

Publishing is the first step that can create an irreversible external side effect. Phase 1 therefore favors explicit attempts and duplicate blocking over hidden retries.

## Duplicate Active Attempts

For a publish draft, only one active attempt is allowed at a time.

Active statuses:

- `QUEUED`
- `RUNNING`
- `UPLOADING`
- `PUBLISHING`
- `AWAITING_PLATFORM_CONFIRMATION`
- `RECONCILING`

If an operator clicks publish twice while an attempt is active, the API returns `duplicate_active_attempt`.

## Retry After Failure

Retry is allowed only after no active attempt exists. If the latest attempt is `NEEDS_RECONCILIATION`, refresh/check that attempt first before creating a new attempt.

The next attempt receives `attempt_number + 1`. Previous attempts stay in the database for trace/debug.

Before retrying:

1. Check the error code.
2. Verify account token/config.
3. Verify final render asset still exists.
4. Verify risk gate still allows publish.
5. Confirm the previous attempt did not actually publish on Facebook if the result was ambiguous.

## Ambiguous Platform Result

If Facebook returns an unclear result or network fails after upload, do not blindly retry. The attempt should move to `NEEDS_RECONCILIATION` when it has an external reference. Use `POST /publish-attempts/{id}/refresh-status` and check the Page manually if the status remains ambiguous.

## Draft State

- `PublishDraft.READY`: metadata is ready for publish attempts.
- `PublishAttempt.FAILED`: one external publish attempt failed.
- `PublishAttempt.NEEDS_RECONCILIATION`: platform state is ambiguous and must be checked before retry.
- `PublishDraft.NEEDS_ATTENTION`: latest publish state needs operator attention.
- `PublishDraft.PUBLISHED`: a publish attempt is confirmed as the canonical published output.

These states are intentionally separate to avoid confusing metadata readiness with external publish result.
