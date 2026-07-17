# Douyin Managed Runtime Fix Resume

## Current objective

Fix Douyin browser-backed runtime ownership so operator-visible browser windows are not treated as usable unless they are app-managed live runtimes registered by the API process.

## Non-negotiables

- Primary browser-backed flow is managed-runtime-only.
- One account/profile may have at most one app-managed live runtime.
- Externally opened saved profiles must be detected/classified and surfaced clearly.
- `Open profile` creates or reuses the canonical managed runtime.
- `Validate`, `Mark challenge solved`, `Ready Check`, and `Intake` must not silently rely on unmanaged visible browser windows.
- Normal managed runtime flow must not fail on a replaceable first page handle.

## Audit snapshot

Relevant files inspected:

- `apps/api/src/services/douyin_browser_context_registry.py`
- `apps/api/src/services/douyin_account_service.py`
- `apps/api/src/services/intake_discovery_service.py`
- `apps/api/src/services/douyin_browser_connect_service.py`
- `apps/api/src/schemas/douyin_accounts.py`

Key current behavior:

- Managed runtime identity is registry-local: `_records` contains `_ContextRecord` entries keyed by runtime context id.
- Account lookup uses `_record_for_account(account_connection_id)` and selects the most recently used record.
- No registry record means `Validate` sees `runtime_missing_reopen_required`, even if an operator can see a browser window.
- Reopen uses Playwright persistent profile launch; competing process errors are classified at the registry layer but not yet exposed as first-class ownership diagnostics.
- Intake uses the same preflight/watchdog/reopen/fetch path, but current ready-check fields do not clearly distinguish `managed_runtime_missing` from `profile_opened_outside_managed_runtime`.

## Implementation status

1. Done: Added first-class managed runtime diagnostics to registry summaries/results.
2. Done: Normalized ownership statuses:
   - `managed_runtime_active`
   - `managed_runtime_missing`
   - `managed_runtime_stale`
   - `profile_locked_by_existing_process`
   - `profile_opened_outside_managed_runtime`
   - `first_page_closed_but_context_alive`
3. Done: Hardened `open_profile_for_account()` to return canonical ownership results and avoid duplicate managed records for the same account/profile.
4. Done: Persisted selected diagnostics into account metadata in `_ensure_persistent_profile_context()` and `_validate_with_live_browser_context()`.
5. Done: Extended API schemas and frontend types/UI labels.
6. Done: Added focused tests for ownership, conflict classification, and page recovery.
7. Partial verification: frontend typecheck passed. Backend pytest is blocked in the current environment because `pytest` is not installed for Python 3.11 and Python 3.12 is unavailable.

## Verification scenarios to cover

- No browser open, saved profile exists: `Open profile` creates a managed runtime; `Validate` succeeds or reports challenge/login with managed diagnostics.
- Managed browser open/logged in: `Validate`, `Mark challenge solved`, and `Intake` reuse the same runtime/context.
- Browser manually opened outside app with same profile: app reports external/unmanaged profile conflict and instructs operator to close it/use `Open profile`.
- Managed first page closes while context lives: app reacquires/creates a page in the same context.
- Runtime record stale/dead: app closes/reconciles stale record and reports reopen-required or external lock accurately.
- Intake ready-check never reports browser-profile ready based only on an unmanaged visible window.
