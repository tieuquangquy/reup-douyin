# Fixed Cloudflare Tunnel for Facebook OAuth

## Target URL

Use one permanent public hostname for the web application, for example:

```text
https://reup.example.com
```

The only Facebook OAuth callback for Accounts is then:

```text
https://reup.example.com/publishing/accounts
```

The retired Ops Console callback is not supported. The hostname, scheme, port,
and path configured in Meta must exactly match the redirect URI saved in the
Accounts UI.

## Current Windows operator deployment

The configured Phase 1 hostname is:

```text
https://reup.vieclammienbac.site
```

The single Meta callback is:

```text
https://reup.vieclammienbac.site/publishing/accounts
```

The DNS zone is served by Cloudflare and the local Named Tunnel origin is
`http://localhost:3000`. The ignored runtime file `.dev/fixed-tunnel.json`
contains only the hostname, tunnel ID, and origin URL; the tunnel credential
JSON remains outside the repository under the operator's Cloudflare profile.

When that runtime file exists, `scripts/dev-start.ps1` starts the fixed tunnel
with the API, web app, and workers. `scripts/dev-stop.ps1` stops the recorded
Windows process trees. The permanent callback was verified end to end on
2026-08-01; the prior `trycloudflare.com` redirect was then removed from Meta.

## Requirements

- A domain you own, such as `example.com`.
- The domain must use Cloudflare DNS/nameservers.
- A Cloudflare account with access to Zero Trust.
- The local Next.js web app running on `http://localhost:3000`.
- `cloudflared` installed on the Windows operator machine.

A free `trycloudflare.com` Quick Tunnel cannot reserve a hostname. Its URL will
change whenever the Quick Tunnel is recreated. A fixed hostname requires a
Named Tunnel and a Cloudflare-managed DNS hostname.

## Recommended setup: dashboard-managed Named Tunnel

1. Add the owned domain to Cloudflare and complete the nameserver change shown
   by Cloudflare. Wait until the zone status is **Active**.
2. Open **Cloudflare Zero Trust → Networks → Tunnels**.
3. Choose **Create a tunnel**, select **Cloudflared**, and name it
   `reup-douyin-windows`.
4. Select the Windows connector instructions. Open PowerShell as Administrator
   and run the exact `cloudflared.exe service install <TOKEN>` command generated
   by Cloudflare. Treat the tunnel token as a secret and do not save it in this
   repository.
5. In the tunnel dashboard, add a **Public Hostname**:

   - Subdomain: `reup`
   - Domain: the owned Cloudflare domain
   - Type: `HTTP`
   - URL: `localhost:3000`

6. Save the hostname and ensure the connector shows **Healthy**.
7. Start the local stack and open `https://reup.example.com`. Confirm the
   Operator Studio login page loads.
8. Confirm `https://reup.example.com/publishing/accounts` loads Accounts after
   one Operator Studio login.

The Windows service starts the Named Tunnel automatically after a reboot. The
Next.js/API/worker stack still needs to be started by the project startup flow.

## Meta App configuration

In **Meta for Developers**, open the app used by this workspace:

1. Go to **Facebook Login → Settings**.
2. Enable **Client OAuth Login** and **Web OAuth Login**.
3. Add exactly this value to **Valid OAuth Redirect URIs**:

   ```text
   https://reup.example.com/publishing/accounts
   ```

4. Remove every legacy Ops Console callback and obsolete `trycloudflare.com`
   URI.
5. In the Meta App basic settings, set **App Domains** to the owned root domain,
   for example `example.com`, when Meta requests it.
6. Save changes. Keep the app in Development mode while testing with an app
   administrator/developer/tester. Production use still requires Meta review
   for any permissions Meta marks as advanced access.

Then open **Operator Studio → Publishing → Accounts → Meta App configuration**:

1. Set **OAuth redirect URI** to the same permanent URI.
2. Verify the App ID, Graph API version, and requested permissions.
3. Leave App Secret blank when preserving the already encrypted secret; enter a
   new secret only when intentionally rotating it.
4. Save Meta configuration.
5. Choose **Connect with Facebook** and verify the callback returns directly to
   `/publishing/accounts` without another login.

## Cutover from the current Quick Tunnel

Do not stop the existing Quick Tunnel until the Named Tunnel hostname is
Healthy and the new URL loads.

After the permanent hostname is verified:

1. Update Meta Valid OAuth Redirect URIs.
2. Update the redirect URI in Accounts and save it.
3. Complete one Facebook connection test.
4. Stop the old Quick Tunnel process.
5. Remove the obsolete `trycloudflare.com` URI from Meta.

## Verification checklist

- The hostname remains identical after restarting `cloudflared`.
- `/publishing/accounts` uses the normal Operator Studio login.
- Meta configuration reports OAuth ready.
- Connect with Facebook returns to the permanent hostname.
- Page discovery succeeds without a raw token appearing in the browser.
- The retired Ops Console callback returns 404 and is not registered in Meta.
