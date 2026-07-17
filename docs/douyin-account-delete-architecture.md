# Douyin Account Delete Architecture

## Goal

Provide a safe operator-facing **Delete** action for connected Douyin source accounts without breaking browser-connect history, intake live-fetch selection, or canonical `DouyinAccountConnection` ownership.

## Delete Model

Phase 1 uses soft delete.

The backend remains the only canonical delete path. The frontend does not remove accounts optimistically without API confirmation.

When an account is deleted:

- `status` becomes `DISABLED`.
- `is_default` becomes `false`.
- health projection becomes disabled/unusable.
- `metadata_json.delete_mode` becomes `soft_delete`.
- `metadata_json.deleted_at` records the deletion time.
- `metadata_json.original_display_name` preserves the previous display name.
- `display_name` is archived with a deleted suffix to avoid blocking future reconnects with the same name.

Normal account lists hide soft-deleted records. Direct historical references can still resolve the row if needed.

## What Delete Does Not Do

Delete does not:

- remove successful browser-connect history;
- delete raw runtime/browser state outside the account row;
- delete intake, crawl, or live-fetch history;
- reset stuck browser-connect sessions;
- remove unrelated `DouyinAccountConnection` records;
- return cookies, tokens, or raw session data.

## API Behavior

`DELETE /douyin-accounts/{account_id}` returns a safe summary:

- `deleted_account_id`
- `delete_mode`
- `success`
- `warnings`
- `recommended_follow_up`

The delete action blocks if the account is tied to a currently running browser-connect session.

## UI Confirmation Behavior

`/accounts/douyin` shows a Delete button in Connected accounts. It opens a confirmation prompt before calling the backend.

The confirmation states that the saved connection is removed from active use and historical records remain. It also warns when the account is default, currently usable for live fetch, or the only usable account.

## Guardrails

- Default account: allowed, with warning; default flag is cleared.
- Only usable account: allowed, with warning; intake may have no usable account afterward.
- Active browser-connect session tied to account: blocked; cancel/reset the connect session first.
- Historical references: preserved by soft-delete.

## Intake / Live Fetch Impact

Because default `GET /douyin-accounts` hides soft-deleted accounts, `/intake` account selectors no longer offer deleted accounts. If the deleted account was default, default resolution falls back to another usable account or no account.

## No-Duplication Strategy

Delete remains part of the existing `DouyinAccountService` and `/douyin-accounts` API. It does not create a second account table, separate cleanup flow, or alternate browser-connect management path.
