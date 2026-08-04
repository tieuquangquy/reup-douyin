# Facebook OAuth onboarding

This guide configures the **Connect with Facebook** flow in `Operator Studio >
Publishing > Accounts`. It replaces manual Page-token copy/paste for normal
operation and uses the same login session as Drafts and Publication Library.

The application cannot create a Meta App on the operator's behalf. Creating the
app, accepting Meta terms and requesting production permissions remain explicit
Meta developer actions.

## 1. Create the Meta App

1. Sign in to Meta for Developers with the Facebook identity that manages the
   target Page.
2. Create an app suitable for a business/Page integration.
3. Add the Facebook Login product or use case offered by the current Meta
   dashboard.
4. Keep the app in Development mode while testing with an app administrator,
   developer or tester account.
5. Copy the **App ID** and reveal the **App Secret**. Enter it only in the
   write-only Meta configuration field on the Accounts page. The API encrypts
   it immediately and never returns it to the browser.

Meta changes dashboard labels periodically. Use the Page/business integration
option that exposes Facebook Login and Graph API permissions.

## 2. Register the redirect URI

Add this exact URI to the Facebook Login valid OAuth redirect URIs:

```text
http://localhost:3000/publishing/accounts
```

The URI must exactly match `FACEBOOK_OAUTH_REDIRECT_URI`, including scheme,
host, port and path. For production, use the public HTTPS origin instead.
For a permanent Windows hostname, follow
[`fixed-cloudflare-tunnel-facebook-oauth.md`](fixed-cloudflare-tunnel-facebook-oauth.md).

## 3. Configure requested permissions

The default onboarding request is:

```text
pages_show_list
pages_read_engagement
read_insights
pages_manage_posts
```

- `pages_show_list` discovers Pages managed by the signed-in identity.
- `pages_read_engagement` and `read_insights` support the Insights preflight.
- `pages_manage_posts` is reserved for the controlled Facebook publishing
  connector.

Do not add permissions “just in case”. The API rejects an OAuth configuration
that contains permissions outside this allowlist or omits the minimum Page
publishing permissions.

Development-mode app roles can test before App Review. Access for people who
are not app roles may require Meta App Review and any business verification
required by Meta at that time.

## 4. Configure the Meta App in Accounts

1. Sign in to Operator Studio as an owner or administrator.
2. Open `/publishing/accounts` and expand **Meta App configuration**.
3. Enter App ID, App Secret, the registered redirect URI and Graph API version.
4. Keep only the approved Page permissions and choose **Save Meta configuration**.
5. Choose **Add Facebook Page → Connect with Facebook** once. The callback
   lists every manageable Page returned by Meta.
6. Select one or more publishable Pages, set the shared default priority, and
   choose **Add selected Pages**. Each Page receives its own encrypted Page
   credential; the browser never receives the token value.

Repeat OAuth only when Meta permissions are revoked/expired or when a newly
granted Page is not present in the current short-lived selection session.

The configuration is scoped to the active workspace. App Secret is encrypted
by the API and is never returned to the browser. On the first local save, the
API creates a server-only key at `./data/secrets/platform-credentials.key` when
no external key reference is configured. The key file must not be committed or
copied into frontend storage.

Production does not auto-generate a filesystem key. Configure
`PLATFORM_CREDENTIAL_ENCRYPTION_KEY_REF` from the deployment secret manager or
replace the local key adapter with KMS. The legacy `FACEBOOK_APP_*` environment
values remain a break-glass fallback; a workspace database configuration takes
precedence.

## 6. Connect Facebook Pages

1. After saving Meta App configuration, choose **Connect with Facebook**.
2. Sign in to Meta and approve the requested Page permissions.
3. Select one or more publishable Pages from the multi-select Page picker.
4. Set the shared default priority and choose **Add selected Pages**.

The application stores one encrypted Page credential per selected Page and
runs the setup check for each. Display name, Page ID, Graph API version and
credential reference are system-managed; only status, priority, safety and
routing settings are operator-editable.

The picker reconciles every discovered Page with the workspace before enabling
selection:

- New Pages can be selected for **Add**.
- Healthy connected Pages are read-only and cannot be added twice.
- Pages in `RECONNECT_REQUIRED` can be selected to rotate their encrypted
  credential without resetting priority, routing, warm-up or publication
  history.
- Missing-permission, operator-hold, cooldown and archived Pages are not
  selectable; they must be handled through their explicit safety/account flow.

## Security and lifecycle

- OAuth state is short-lived, single-use and bound to the initiating workspace
  and operator subject.
- The authorization code and user token are processed only by the API.
- Page access tokens are encrypted with AES-256-GCM before persistence.
- The browser receives Page ID, name, tasks and granted-scope names only.
- The OAuth session retains only still-selectable publishable Pages while the
  short-lived selection flow is active, then drops its encrypted payload when
  all selectable Pages have been handled or the session expires.
- Manual `FACEBOOK_PAGE_ACCESS_TOKEN` and Meta App environment configuration remain break-glass
  fallback. Safe defaults still require OAuth-verified publish capability.
- If Meta revokes the token or Page permissions change, reconnect the Page.
- A Page is placed on a safety hold when OAuth does not attest both
  `pages_manage_posts` and the Page `CREATE_CONTENT` task.
- New OAuth-connected Pages use a conservative warm-up window (2 attempts per
  24 hours and a 6-hour minimum interval by default). Mature Pages are limited
  to 6 attempts per 24 hours and a 60-minute minimum interval.
- Only one active attempt is allowed per Page. An unresolved/ambiguous attempt
  must be reconciled before another publish is admitted.
- Graph rate-limit responses create a cooldown; token, permission and platform
  restriction responses pause the Page and require operator reconnection.
- Publish tokens are sent in an HTTPS `Authorization` header, never in a URL
  query string or persisted request summary.

These are conservative product guardrails, not a guarantee against account
restriction. Content rights, Page quality, policy compliance, user behavior,
and Meta's own risk systems remain outside this application. Do not use proxy
rotation, browser-cookie scraping, device spoofing, or permission inflation to
evade Meta controls.

Recurring Insights collection remains disabled. OAuth onboarding does not
publish content, enqueue collection or enable the scheduler.
