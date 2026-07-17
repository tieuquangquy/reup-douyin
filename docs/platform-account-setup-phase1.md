# Platform Account Setup Phase 1

Phase 1 uses manual Facebook Page account configuration. This is intentionally minimal so the first connector can be validated without building a full OAuth product.

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

