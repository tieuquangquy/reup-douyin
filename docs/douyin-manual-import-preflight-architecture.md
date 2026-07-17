# Douyin Manual Import Preflight Architecture

## Goal

Add a preflight diagnostics layer for manual-imported Douyin accounts so operators can see, before `/intake`, whether an imported session is usable, insufficient, blocked, invalid, or retryable.

## Canonical Architecture

This step does **not** introduce a new fetch path.

Canonical flow remains:

```text
manual import -> DouyinAccountConnection
  -> DouyinAccountService normalization
  -> canonical runtime config
  -> DouyinLiveFetchClient / existing validation path
  -> account health + intake discovery
```

## Preflight Categories

Manual-import preflight must classify at minimum:

- `imported_session_missing_cookie`
- `imported_session_cookie_parse_failed`
- `imported_session_missing_user_agent`
- `imported_session_cookie_too_thin`
- `login_required`
- `blocked_response`
- `validation_transport_error`
- `parse_failed`
- `usable_for_fetch`
- `unknown_validation_failure`

## Safe Operator-Facing Summary

For manual-imported accounts, the API should expose a compact preflight summary with:

- `code`
- `outcome`
- `summary`
- `next_action`
- `fetch_usable`
- `detected_format`
- `cookie_strength`
- `checked_at`
- `source_type`

No raw cookies or secret headers are exposed.

## Persistence Strategy

- Use the existing `DouyinAccountConnection.metadata_json` / summary fields to store bounded preflight metadata.
- Do not add a second account table.
- Do not duplicate validation state outside the canonical account record.

## UI Strategy

`/accounts/douyin` should show, for manual imports only:

- last preflight result
- short reason
- recommended next action
- safe import/runtime details

This is a compact operator aid, not a deep debug console.

## Non-Goals

- No new manual-import-only discovery path.
- No browser-connect redesign.
- No raw cookie inspection in UI.
- No full observability dashboard redesign.
