# Platform Account Setup Phase 1

Phase 1 supports controlled Meta OAuth onboarding with encrypted Page-token
storage. Manual environment-variable configuration remains a break-glass
fallback, but safe defaults require OAuth-verified publish capability before a
new external publish is admitted.

## Model

`PlatformAccount` stores:

- workspace id
- platform
- display name
- external account id, which is the Facebook Page id
- token reference
- status
- metadata

The token value itself should live outside code. By default, the API resolves the token from:

```text
FACEBOOK_PAGE_ACCESS_TOKEN
```

You can create an account with a different `token_reference` if the token is stored in another environment variable.

## Create Account

```http
POST /platform-accounts
```

Example:

```json
{
  "platform": "FACEBOOK_REELS",
  "display_name": "Demo Page",
  "external_account_id": "123456789",
  "token_reference": "FACEBOOK_PAGE_ACCESS_TOKEN",
  "metadata_json": {
    "graph_api_version": "v20.0"
  }
}
```

## Security Rules

- Do not commit page access tokens.
- Do not paste tokens into docs, screenshots, logs, or issue reports.
- Do not store full tokens in `metadata_json`.
- Token references can be stored in DB; token values should come from env/config.
- Rotate the token if it appears in logs or a pilot report.

## Operational Check

Before publishing:

1. Confirm `PlatformAccount.status = ACTIVE`.
2. Confirm `external_account_id` is the Page id.
3. Confirm the environment variable named by `token_reference` exists.
4. Confirm the Meta app/token has the permissions required for Page video publishing.

## Controlled Facebook Page Setup UI

The operator can now configure and verify a Facebook Page from:

```text
/publishing/accounts
```

The setup surface supports:

- creating and editing a `FACEBOOK_REELS` `PlatformAccount`;
- Page id, display name, priority and account status;
- a server-side token environment-variable reference (never the raw token);
- Graph API version and Insights media-id source;
- explicit operator attestation for `read_insights` and
  `pages_read_engagement`;
- a read-only setup check that performs no Facebook network request and never
  returns the token value.

For manual fallback, the token must be placed in the local API environment and
the UI stores only the variable name. With the default
`FACEBOOK_PUBLISH_REQUIRE_VERIFIED_CAPABILITY=true`, a manually entered token
alone cannot pass the publishing gate because the application has not verified
`pages_manage_posts` and the Page `CREATE_CONTENT` task. Reconnect through OAuth
instead. Disabling this guard is an explicit break-glass action and is not
recommended for normal operation.

The preferred path is now the server-controlled Meta OAuth onboarding flow
documented in `docs/facebook-oauth-onboarding.md`. It discovers Pages, stores the
selected Page token in the encrypted platform credential store and fills the
account form automatically. Environment-variable token setup remains a manual
fallback.

## Conservative Publish Guardrails

The API applies Page-level admission control before enqueue and again in the
worker while excluding the current durable attempt:

- OAuth publish capability must be no older than 30 days;
- only one active attempt can exist for a Page (also backed by a PostgreSQL
  partial unique index);
- unresolved external outcomes block another attempt;
- a newly connected Page defaults to 2 attempts per 24 hours with a 6-hour
  interval for 7 days;
- afterward, the default is 6 attempts per 24 hours with a 60-minute interval;
- 2 failed attempts in 24 hours block more publishing pending investigation;
- rate-limit errors create a cooldown; token, permission and restriction errors
  pause and hold the account until reconnection.

These values are local safety policy, configurable through the documented
`FACEBOOK_PUBLISH_*` environment settings. They do not represent Meta's private
limits and cannot guarantee that Meta will never restrict an account.

## Register An Existing Reel

`POST /platform-publications/manual-import` registers an operator-verified Reel
that already exists on the selected Facebook Page. It creates a reconciled local
evidence attempt and a canonical `PlatformPublication` with:

```text
origin = MANUAL_IMPORT
```

Registration requires an existing Facebook `PublishDraft`, exact account,
Reel/media id, Facebook permalink, timezone-aware publish time and the literal
operator attestation `EXISTING_FACEBOOK_REEL_VERIFIED`.

This operation never uploads content and never calls Facebook. Repeating the
same Page + external publish id + draft is idempotent. Migration
`0037_publication_origin` adds the explicit publication origin field.

## One-Shot Insights Canary

After Page setup and Reel registration, the same UI runs the existing Facebook
Insights live preflight. Only a fully passing preflight reveals the one-shot
collection action. The operator must separately authorize that external network
read before a durable `FACEBOOK_GRAPH` metric job is enqueued.

The recurring metric scheduler remains disabled and is not changed by account
setup, Reel registration, preflight or one-shot collection.
