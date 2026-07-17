# douyin-browser-reset-architecture.md

## Purpose

`Reset browser connect state` is a local-development recovery action for `/accounts/douyin`. It clears stuck browser-connect attempts without deleting saved Douyin accounts or creating a second connect pipeline.

## What Reset Affects

Reset affects only `DouyinBrowserConnectSession` records in active-looking states:

- `PENDING`
- `LAUNCHING_BROWSER`
- `WAITING_FOR_LOGIN`
- `CAPTURING_SESSION`
- `VALIDATING`

Those rows are terminalized as `CANCELLED` with a recovery-specific `last_error` and metadata.

## What Reset Does Not Affect

Reset does not:

- delete `DouyinAccountConnection` records
- delete completed account sessions
- delete validated saved accounts
- clear runtime install/configuration
- remove historical browser-connect attempts
- log or return raw cookies

## API Behavior

`POST /douyin-accounts/browser-connect/reset`

Response includes:

- `reset_count`
- `affected_session_ids`
- `resulting_state`
- `can_start_new`
- `warning`

If no resettable sessions exist, the endpoint returns `reset_count=0` and `can_start_new=true`.

## UI Behavior

The `/accounts/douyin` page shows `Reset browser connect state` as a troubleshooting action when there is a non-completed browser-connect session in view. The action requires confirmation and explains that saved accounts are not deleted.

After reset:

- polling detaches from the old session
- local browser-connect UI state clears
- start connect becomes usable again
- saved account table remains intact

## No-Duplication Strategy

Reset is implemented inside `DouyinBrowserConnectService`, the same service used by start/resume/cancel/restart. It is not a second browser-connect pipeline and does not bypass canonical persistence.

## V1 Limitations

- Reset terminalizes DB state; it does not maintain a separate browser process registry.
- Existing Playwright loops observe terminal DB state through the existing cancellation check.
- The action is intentionally operator-triggered and explicit rather than hidden cleanup.
