# Douyin Persistent Browser Context Architecture

## What It Means

Persistent browser context means the local API process can keep a Playwright browser context alive after browser-assisted login, then reuse that authenticated context for later validation and live-fetch preparation.

It is a local development optimization. It is not a remote browser farm, SaaS session broker, or second account model.

## Canonical Model Relationship

`DouyinAccountConnection` remains the canonical persisted account record.

The runtime browser context is ephemeral:

- held in API process memory;
- lost on API restart;
- never returned to the frontend as raw cookies or browser handles;
- bound to an account id only after the canonical account exists.

## Runtime Context Model

The local registry tracks:

- `runtime_context_id`
- `account_connection_id`
- `connect_session_id`
- `workspace_id`
- `status`
- `started_at`
- `last_used_at`
- `last_validated_at`

The registry owns Playwright runtime handles and can close them during reset, account delete/disable, or idle cleanup.

## Validation Reuse Strategy

When enabled:

1. `DouyinAccountService.validate_account()` checks for a live context for the account.
2. If live context exists and is healthy, validation refreshes cookies from that context and maps the result into the same canonical account status fields.
3. If no live context exists, or the context is stale/closed, validation falls back to the existing cookie-backed HTTP path.

The validation result mapping remains canonical. Only the transport source changes.

## Fetch Reuse Strategy

V1 uses a practical reuse strategy:

1. Before live fetch builds the normal account-backed adapter, `resolve_runtime_config()` tries to refresh session artifacts from the live browser context.
2. The canonical `DouyinLiveFetchClient` and intake ingest path still perform the fetch.
3. If the live context is gone, fetch proceeds with the persisted cookie if the account is otherwise usable.

This reduces repeated QR/login without introducing a browser-only intake pipeline.

## Cleanup / Reset Behavior

- Idle or max-lifetime-expired contexts become stale and are closed on access.
- Browser-connect reset closes runtime contexts tied to affected connect sessions.
- Account delete/disable closes runtime contexts for that account.
- If the browser process dies, the registry marks the context invalid on next access and falls back.

## UI Behavior

`/accounts/douyin` and `/intake` show browser context availability as an operational hint:

- live browser attached
- no live browser context
- stale/closed browser context

Runtime availability is not the same as persisted account health.

## No-Duplication Strategy

No new account table, intake pipeline, or browser-only fetch product path is added. The registry is a runtime helper used by canonical browser connect and account-backed fetch services.
