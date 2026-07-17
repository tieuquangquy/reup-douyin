# Douyin Managed Runtime Fix Log

## Scope

This log tracks the managed-browser runtime ownership fix for Douyin browser-backed accounts.

## Audit findings

- The live managed runtime is currently identified only by an in-memory registry record owned by `DouyinBrowserContextRegistry`.
- A visible browser window is not enough to prove ownership. If the app did not create/register that Playwright persistent context, `_record_for_account()` returns no record and validation reports `no_live_browser_context`.
- `Open profile` currently calls `open_profile_for_account()` and reuses a registry record when one exists for the same account/profile identity. If none exists, it launches a persistent context for the saved profile and registers a new `_ContextRecord`.
- `Validate` first probes `validate_account_context()`. If no active registry record exists and a saved profile exists, it calls `_ensure_persistent_profile_context()` to reopen the saved persistent profile, then validates again.
- `Mark challenge solved` delegates to the same `validate_account()` path, so it inherits the same managed-runtime behavior and failure ambiguity.
- `Ready Check` / `Intake` call `preflight_fetch_readiness()`, which uses `watchdog_for_account()`, may call `_ensure_persistent_profile_context()`, and then runs browser-backed fetch through `fetch_profile_page()`.
- Persistent profile launch errors are currently classified as `profile_locked_by_existing_process` when Chromium reports process singleton/user-data-directory lock text, but the account metadata/UI mostly surfaces this under generic reopen/runtime-unavailable language.
- `first_page_closed_early:TargetClosedError` can still happen when `launch_persistent_context()` returns/starts but page acquisition fails. The previous page recovery made the page replaceable once context exists, but the managed-open path still wraps first page acquisition as early failure instead of classifying ownership/lock/stale-context cases consistently.

## Planned strict model

- Primary browser-backed paths must use only app-managed registry records.
- A browser window opened manually or by another process must be classified as external/unmanaged, not treated as usable.
- A profile lock from another Chromium/Chrome process must be classified as `profile_locked_by_existing_process` and surfaced as `profile_opened_outside_managed_runtime` recovery guidance.
- Missing/stale/dead registry records must be classified separately from external profile locks.
- Closed first page with live context must remain recoverable as `first_page_closed_but_context_alive`.

## Change log

- 2026-04-26: Started audit. Created mandatory managed-runtime docs before code changes.
- 2026-04-26: Added first-class registry ownership diagnostics for managed-runtime active/missing/stale state and external profile-lock conflicts.
- 2026-04-26: Hardened `Open profile` canonical runtime behavior by reusing only active app-managed records, closing stale duplicate same-profile records, and classifying persistent profile locks as `profile_opened_outside_managed_runtime`.
- 2026-04-26: Hardened page handling so a closed remembered/first page with a live context is recovered as `first_page_closed_but_context_alive` instead of recurring as `first_page_closed_early:TargetClosedError` in normal managed-runtime flow.
- 2026-04-26: Propagated managed-runtime/profile-conflict diagnostics through validation, profile open, Ready Check/Intake preflight, API schema, frontend types, account health UI, and i18n recovery labels.
- 2026-04-26: Added focused test coverage for profile-lock conflict classification, validation metadata/health alignment, Intake ready-check blocking, and updated page-recovery expectations.
- 2026-04-26: Verification: frontend typecheck passed via `npm run typecheck`. Backend targeted pytest could not run in the current environment because Python 3.11 lacks `pytest` and Python 3.12 is not installed despite `apps/api/pyproject.toml` requiring Python >=3.12.
