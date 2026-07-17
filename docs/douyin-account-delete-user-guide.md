# Douyin Account Delete User Guide

## What Delete Does

Use **Delete** in `/accounts/douyin` when a saved Douyin source account connection should no longer appear in active account lists or intake selectors.

In V1 this is a safe soft delete:

- the connection is disabled;
- it is hidden from the Connected accounts table after refresh;
- it is hidden from `/intake` account selection;
- default selection is cleared if the deleted account was default;
- history and references remain intact for debugging.

## What Delete Does Not Do

Delete does not:

- delete intake/crawl history;
- delete browser-connect session history;
- delete other Douyin accounts;
- reset a stuck browser-connect session;
- return or expose raw cookies;
- uninstall Playwright or browser runtime state.

For stuck browser connect, use **Reset browser connect state** instead.

## Confirmation Flow

The UI asks for confirmation before calling the backend.

The confirmation warns when:

- the account is default;
- the account is currently usable for live fetch;
- the account is the only usable account.

After a successful delete, the UI reloads the account list from the API.

## Backend Guardrails

The backend blocks deletion if the account is attached to a running browser-connect session. Cancel, force restart, or reset the browser-connect session first.

The backend is the source of truth. The frontend never removes the account locally without a successful API response.

## Intake Impact

`/intake` reads the canonical account list from `GET /douyin-accounts`. Soft-deleted accounts are hidden from this default list, so a deleted account will no longer be selectable for live fetch.

If the deleted account was the only usable account, validate or connect another account before running live fetch.

## V1 Limitations

- There is no restore UI for soft-deleted accounts.
- Direct historical references can still resolve a soft-deleted row for debugging.
- Delete does not perform a deep cleanup of all historical records by design.
