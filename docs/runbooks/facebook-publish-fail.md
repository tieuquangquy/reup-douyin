# Facebook Publish Fail Runbook

Use this runbook when a Facebook Reels publish attempt fails, stalls, or needs reconciliation.

## Symptoms

- `POST /publish-drafts/{id}/publish` returns an error.
- Publish draft shows `FAILED` or `NEEDS_ATTENTION`.
- Publish attempt shows `FAILED`, `NEEDS_RECONCILIATION`, or `RECONCILING`.
- The reel appears on Facebook but the app does not show `PUBLISHED`.
- The app reports `duplicate_active_attempt`.

## Common Causes

- Page access token missing, expired, or missing permissions.
- `PlatformAccount.external_account_id` is not the Facebook Page id.
- Final render asset is missing or unreadable.
- Risk gate blocks the draft.
- Network failed after Facebook created an upload reference.
- Facebook returned an ambiguous processing response.
- Operator clicked publish multiple times while an attempt was active.

## Checks

1. Open the publish draft and inspect the latest attempt.
2. Check `error_code`, `error_message`, `external_publish_id`, `external_media_id`, and `external_reel_id`.
3. If any external id exists, do not retry immediately.
4. Click `Refresh status` in the publish panel or call:

```http
POST /publish-attempts/{publish_attempt_id}/refresh-status
```

5. Check `current_publication_status` on:

```http
GET /publish-drafts/{publish_draft_id}/publish-status
```

6. Verify the Page manually in Facebook if status remains `UNKNOWN`, `PROCESSING`, or `PARTIALLY_CONFIRMED`.

## Fixes

- `invalid_platform_account`: confirm account is `FACEBOOK_REELS`, status is `ACTIVE`, Page id is correct, and the token env var exists.
- `auth_token_invalid`: rotate or replace the Page access token.
- `missing_render_output`: rerun render or repair the final render asset.
- `gate_blocked`: resolve, waive, or record the required risk decision before retry.
- `network_request_failed` with external id: refresh status before retrying.
- `duplicate_active_attempt`: wait for the active attempt to finish or reconcile it.

## Rerun Policy

Rerun publish only when:

- no attempt is active;
- no attempt is currently `RECONCILING`;
- any `NEEDS_RECONCILIATION` attempt has been refreshed or manually checked;
- the operator has confirmed a retry will not create an accidental duplicate post.

## Escalate

Escalate before retrying if:

- Facebook shows a published reel but the app cannot reconcile it;
- multiple attempts show different external ids;
- the Page token repeatedly fails after rotation;
- the same draft is both `PUBLISHED` and has newer ambiguous attempts.
