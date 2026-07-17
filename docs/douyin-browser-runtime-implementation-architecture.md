# Douyin Browser Runtime Implementation Architecture

## Canonical Runtime Layer

Browser-assisted Douyin connect uses one runtime path:

1. Web page `/accounts/douyin`
2. `POST /douyin-accounts/browser-connect/start`
3. `DouyinBrowserConnectService.start_connect`
4. `PlaywrightDouyinBrowserSessionCapture.capture`
5. `DouyinAccountService.create_account`
6. `DouyinAccountService.validate_account`

The runtime is **Python Playwright inside `apps/api`**.

There is no Node Playwright path and no worker-owned browser login path for V1.

## Probe / Launch / Session Capture Lifecycle

### Probe

The API service probes runtime readiness before creating a connect session:

- Python Playwright importable
- Chromium executable path available
- optional headless launch smoke succeeds

Probe failures are returned as actionable setup/runtime codes such as:

- `dependency_missing`
- `browser_binary_missing`
- `launch_failed`
- `runtime_probe_failed`
- `runtime_not_supported`

On Windows the service sets the Proactor event loop policy before Playwright starts. This prevents Playwright subprocess launch from hitting `NotImplementedError` under an incompatible event loop policy.

### Launch

The background connect thread launches a visible Chromium browser, navigates to `https://www.douyin.com/`, and waits for the operator to complete login in that browser.

If Douyin shows QR login, the operator scans the QR shown by the real Douyin page.

If the browser closes before login completes, the session fails with `browser_closed` rather than an opaque runtime error.

### Session Capture

The runtime polls the browser context cookies until authenticated Douyin cookie names are present.

Captured data is reduced to:

- Douyin cookie header
- user agent
- safe metadata summary such as cookie count and login URL

Raw cookies are passed only to server-side account persistence and are never returned to browser UI.

## Account Persistence Integration

Successful capture creates a canonical `DouyinAccountConnection` through `DouyinAccountService.create_account`.

The account metadata includes:

- `connection_source = browser_assisted`
- `browser_connect_session_id`
- safe capture metadata

Manual import uses the same account table with `connection_source = manual_import`.

## Validation Integration

After capture, `DouyinAccountService.validate_account` validates the account through the existing live-fetch validation path.

The browser connect session moves to:

- `COMPLETED` when validation succeeds
- `FAILED` with `validation_failed:<reason>` when validation fails

The API response exposes safe account summary only.

## No-Duplication Strategy

- Do not add a second connect session model.
- Do not add a second account model.
- Do not add a frontend-only session capture path.
- Do not introduce Node Playwright for this flow.
- Keep manual import as fallback, not as a competing primary flow.

## V1 Simplifications

- The persisted status enum remains compact: `PENDING`, `LAUNCHING_BROWSER`, `WAITING_FOR_LOGIN`, `CAPTURING_SESSION`, `VALIDATING`, `COMPLETED`, `FAILED`, `CANCELLED`.
- Timeout is represented as `status = FAILED` plus response `outcome = timed_out`.
- Douyin login detection uses known authenticated cookie names, not password automation or a private QR protocol.
