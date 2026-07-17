# douyin-browser-health-alignment-architecture.md

## Objective

Align Douyin account validation, persisted health/status, and Intake fetch readiness so that a connected browser-backed account is judged primarily by the same persistent browser profile that Intake will use. A successful browser-backed validation must be able to clear stale blocked state that came from older or weaker evidence.

## Audit Findings

- [`DouyinAccountService.validate_account()`](apps/api/src/services/douyin_account_service.py:382) already attempts live browser-context validation before detached HTTP validation.
- [`DouyinAccountService._validate_with_live_browser_context()`](apps/api/src/services/douyin_account_service.py:949) can set the account back to `ACTIVE` and clear errors on browser success.
- [`DouyinAccountService.preflight_fetch_readiness()`](apps/api/src/services/douyin_account_service.py:655) is already browser-profile-first for Intake and reuses watchdog/reopen behavior.
- [`DouyinAccountService._refresh_session_from_live_browser_context()`](apps/api/src/services/douyin_account_service.py:1015) refreshes fetch material from the runtime-backed browser profile before building the fetch client.
- [`DouyinAccountsPage`](apps/web/src/components/douyin-accounts/DouyinAccountsPage.tsx) currently renders a single health/status view, but it does not clearly distinguish between:
  - interactive browser profile availability,
  - automated browser-backed validation result,
  - detached HTTP/session fallback state.
- [`DouyinAccountResponse`](apps/api/src/schemas/douyin_accounts.py:56) exposes raw health, status, validation, error, and browser context fields, but it does not currently expose a path-alignment summary that explains whether validation and Intake are using the same browser-backed path.

## Exact Mismatch Observed In Current Design

The main drift is no longer the top-level validation entrypoint. The drift is evidence clarity and precedence.

### What is already aligned

- Manual Validate uses browser-backed validation first when browser reuse is enabled.
- Intake preflight uses the persistent browser profile as the preferred path and only falls back to HTTP when allowed.
- Browser-backed success already has the ability to overwrite a stale `BLOCKED` account row by setting status back to `ACTIVE`.

### What is still misaligned

- The account row shown in [`DouyinAccountsPage`](apps/web/src/components/douyin-accounts/DouyinAccountsPage.tsx:504) does not tell the operator whether the current blocked state came from:
  - a live browser-backed validation,
  - a retryable browser validation block,
  - a detached HTTP validation path,
  - or older persisted state that predates the current reusable profile runtime.
- [`DouyinAccountService.to_response()`](apps/api/src/services/douyin_account_service.py:872) projects a single account health/status view, but it does not synthesize a stronger operator-facing truth such as:
  - browser profile currently live,
  - last browser-backed validation succeeded/failed,
  - validation path matches Intake path,
  - stale blocked state is being overridden by stronger browser evidence.
- [`DouyinAccountService.health_summary()`](apps/api/src/services/douyin_account_service.py:453) is status-driven. Once an account is `BLOCKED`, the summary remains blocked until another validation overwrites it. This is correct for persistence, but without surfaced evidence-precedence diagnostics it can look wrong to operators when the saved profile is visibly usable.
- [`DouyinBrowserContextRegistry.summary_for_account()`](apps/api/src/services/douyin_browser_context_registry.py:441) and [`DouyinBrowserContextRegistry.validate_account_context()`](apps/api/src/services/douyin_browser_context_registry.py:509) hold runtime truth, but only fragments of that truth are exposed back to the UI.

## Chosen Alignment Policy

### 1. Browser-backed evidence is strongest for browser-backed accounts

If an account has a saved persistent browser profile, and validation succeeds through that live browser context, that result is the strongest current evidence for the account’s usability.

That success must:

- set persisted account status back to `ACTIVE`,
- clear stale blocked/error markers,
- refresh cookie/user-agent material from the same browser runtime,
- record that browser-backed validation succeeded,
- mark that validation and Intake are path-aligned when Intake is also using the browser profile.

### 2. Interactive browser usability and automated browser usability must be separated

The system must distinguish:

- **Interactive browser usable**: a saved or live profile exists and can be opened/reused.
- **Automated browser-backed validation usable**: the runtime profile passed automated validation checks.
- **Detached HTTP path blocked or degraded**: HTTP/session-only validation or fallback cannot be treated as stronger than successful browser-backed validation for browser-backed accounts.

### 3. Detached HTTP evidence must not dominate browser-primary health

For connected browser-profile accounts:

- browser-backed validation success overrides older detached blocked status,
- detached HTTP fallback remains a fallback diagnostic path,
- HTTP-only failure must not leave the UI implying the account is unusable when the stronger browser-backed path is healthy.

### 4. Canonical account model remains unchanged

No second account table, no duplicated health model, and no separate Intake account pipeline will be introduced. The canonical account row remains the source of truth, with stronger diagnostics added around evidence source and alignment.

## Planned Response And UI Additions

The account response should expose explicit browser-health alignment fields for `/accounts/douyin`, such as:

- browser profile saved/live state,
- last browser validation status/reason/time,
- whether the current effective validation evidence came from browser or detached HTTP,
- whether Intake and validation are currently path-aligned,
- whether a stale blocked state was cleared by browser-backed success,
- operator-safe diagnostics describing why the account is usable or not usable.

These fields should be computed in the API service layer so the web app remains a renderer of canonical server truth.

## Non-Goals

- No crawler changes.
- No second discovery or Intake pipeline.
- No new persistence model for account health.
- No attempt to infer real browser usability only from UI state without server-side validation evidence.
- No unsafe logging of cookies, tokens, or private local paths.

## Acceptance Criteria

- Manual validation and Intake report whether they are using the same persistent browser profile path.
- A successful browser-backed validation can clear a stale blocked account state.
- `/accounts/douyin` can distinguish live profile availability from automated validation status.
- Detached HTTP failure no longer dominates operator-visible health for browser-primary accounts.
- Diagnostics remain explicit, safe, and tied to the canonical account record.
