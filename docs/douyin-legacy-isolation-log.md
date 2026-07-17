# Douyin Legacy Isolation Log

## Purpose

This log tracks the hard isolation of legacy Douyin manual-import and detached HTTP-fallback paths from the default runtime and main operator UI.

The target default path is browser-profile-backed only:

1. Open or reopen a persistent browser profile.
2. Let the operator log in or solve challenges manually in that same profile.
3. Validate through that same browser profile.
4. Run Intake through that same browser profile.
5. Extract data through the browser-backed fetch path.
6. Feed the canonical downstream ingest/discovery pipeline without changing canonical models.

## Non-goals

- Do not delete legacy manual-import code.
- Do not delete detached HTTP fallback code.
- Do not add crawler, video processing, scoring, queue, database schema, or auto-publish implementation.
- Do not rewrite the canonical downstream ingest/discovery pipeline.
- Do not hardcode user-specific local paths.

## Initial implementation plan

1. Audit all current reachability for manual import and detached HTTP fallback before editing runtime code.
2. Create required isolation docs first.
3. Add explicit default-off legacy/debug settings and document them.
4. Gate validation, preflight/readiness, health projection, and Intake orchestration so browser profile is the only default happy path.
5. Hide manual import and fallback execution surfaces from the main operator UI unless explicit debug flags are enabled.
6. Add tests proving default browser-only behavior and explicit legacy behavior.
7. Run focused backend tests and web typecheck.

## Audit findings before code changes

### Settings and environment

Current backend settings in `apps/api/src/core/settings.py` expose browser-primary defaults plus one HTTP fallback flag:

- `douyin_persistent_browser_profile_enabled = True`
- `douyin_prefer_browser_profile_for_validation = True`
- `douyin_prefer_browser_profile_for_fetch = True`
- `douyin_allow_legacy_http_fallback_for_intake = False`
- `douyin_persistent_browser_context_enabled = True`
- `douyin_reuse_live_browser_for_validation = True`
- `douyin_reuse_live_browser_for_fetch = True`

Gap: there are no explicit, broad flags yet for:

- `DOUYIN_ENABLE_LEGACY_MANUAL_IMPORT`
- `DOUYIN_ENABLE_LEGACY_HTTP_FALLBACK`
- `DOUYIN_ENABLE_LEGACY_DEBUG_SURFACES`

### Manual import reachability

Manual import currently participates in account creation/update, response projection, health details, and main UI.

Backend reachability in `apps/api/src/services/douyin_account_service.py`:

- `ManualImportPreflightResult` defaults to `source_type="manual_import"`.
- `create_account()` auto-detects manual import metadata and runs `validate_account(..., validation_source="manual_import_smoke")`.
- `update_account()` can re-run manual import smoke validation when imported material changes.
- `_is_manual_import_metadata()` detects `metadata_json.connection_source == "manual_import"`.
- `_manual_import_preflight_result()` and `_manual_import_preflight_summary()` project manual import readiness and next action.
- `to_response()` exposes `manual_import_preflight` for accounts where manual-import metadata exists.

Frontend reachability in `apps/web/src/components/douyin-accounts/DouyinAccountsPage.tsx`:

- The main Douyin Accounts page includes a visible `details` panel with `id="manual-session-import"`.
- The form submits `metadata_json: { connection_source: "manual_import" }`.
- Account rows display manual import preflight details as normal operator information.
- Validation messages prefer `account.manual_import_preflight.summary` when present.
- `connectionSourceLabel()` maps `manual_import` to `Manual` as a normal source label.

API/schema reachability in `apps/api/src/schemas/douyin_accounts.py` and web type reachability in `apps/web/src/types/douyin-accounts.ts`:

- `manual_import_preflight` is part of `DouyinAccountResponse` / `DouyinAccount`.
- `DouyinManualImportPreflightSummary` / `DouyinManualImportPreflight` are still public contracts.

Browser connect reachability in `apps/api/src/services/douyin_browser_connect_service.py`:

- Browser connect failure/recovery text suggests manual import fallback.
- Browser connect response includes `manual_fallback_available=True`.
- Recommended actions include `setup_runtime_or_manual_import`, `retry_login_or_manual_import`, and `retry_or_manual_import`.

Default-policy decision: keep these code paths and contracts, but they must not appear as normal main operator choices unless legacy/debug surfaces are explicitly enabled.

### Detached HTTP fallback reachability

Detached HTTP fallback currently participates in validation fallback, fetch client construction, preflight readiness, health evidence, Intake ready-check, and UI diagnostics.

Backend validation reachability in `apps/api/src/services/douyin_account_service.py`:

- `validate_account()` first attempts live browser context validation via `_validate_with_live_browser_context()`.
- If browser validation returns `None`, the method falls through to `resolve_runtime_config()`, builds a `DouyinLiveFetchClient`, and fetches the validation URL through detached HTTP/session material.
- This fallback is not yet gated by an explicit broad `DOUYIN_ENABLE_LEGACY_HTTP_FALLBACK` setting.

Backend fetch reachability in `apps/api/src/services/douyin_account_service.py` and `apps/api/src/adapters/douyin_live_fetch.py`:

- `build_fetch_client()` passes `prefer_browser_profile=settings.douyin_prefer_browser_profile_for_fetch`.
- `build_fetch_client()` passes `allow_http_fallback=settings.douyin_allow_legacy_http_fallback_for_intake`.
- `DouyinLiveFetchClient` supports browser primary with optional HTTP fallback.
- `DouyinLiveFetchClient` also supports HTTP-primary-with-browser-fallback metadata for legacy paths.

Preflight/readiness reachability in `apps/api/src/services/douyin_account_service.py`:

- `preflight_fetch_readiness()` can return `fetch_readiness_category="fetch_ready_http_fallback"` and `selected_fetch_path="http_html"` when legacy fallback is allowed and HTTP material exists.
- Without a browser profile and with fallback enabled, the preflight can become successful through detached HTTP.
- With default fallback disabled, no-profile accounts return `browser_profile_required`; this needs to remain the default invariant.

Intake reachability in `apps/api/src/services/intake_discovery_service.py`:

- `ready_check()` reads `douyin_allow_legacy_http_fallback_for_intake` into `fallback_allowed`.
- `_ready_check_status()` maps `fetch_ready_http_fallback` to `FALLBACK_READY`.
- `safe_to_run_intake_now` currently includes `FALLBACK_READY`.
- `_ready_check_recommended_action()` returns `run_intake_now` / `Run Intake with fallback` for fallback readiness.
- `_ready_check_summary_message()` presents fallback readiness as runnable.

Health/evidence reachability in `apps/api/src/services/douyin_account_service.py`:

- `_browser_health_alignment_summary()` computes `detached_http_state` from cookie/user-agent material.
- `effective_validation_path` can become `detached_http` when `validation_source` starts with `http`.
- `expected_intake_path` currently becomes `detached_http` when no saved browser profile exists.
- `validation_intake_aligned` can therefore consider a detached HTTP path aligned.
- Operator summary can state that the account depends on detached HTTP session material.

Frontend reachability in `apps/web/src/components/intake/IntakePage.tsx`:

- The ready-check button changes to a fallback run label for `FALLBACK_READY`.
- Result diagnostics show `fallback_from_execution_path` and `http_fallback_attempted` as normal status details.
- Label helpers include `http_html`, `http_then_browser_fallback`, `http_primary_with_browser_fallback`, `http_only`, and `fetch_ready_http_fallback`.

Frontend reachability in `apps/web/src/components/douyin-accounts/DouyinAccountsPage.tsx`:

- Browser health alignment displays detached HTTP state and expected/effective path labels in the normal account table.
- `alignmentPathLabel()` labels `detached_http` as a normal path.
- `alignmentDetachedHttpStateLabel()` labels detached HTTP states as normal evidence.

API/schema and type reachability:

- `apps/api/src/schemas/intake.py` exposes `fallback_allowed`, `intended_fetch_path`, `fetch_execution_path`, `fallback_from_execution_path`, `http_fallback_attempted`, and `http_fallback_reason`.
- `apps/web/src/types/intake.ts` mirrors these fields.
- These fields can remain for observability/debug, but the default main operator UI should not present fallback as an ordinary happy path.

Default-policy decision: detached HTTP fallback remains present in code for legacy/debug mode, but default validation/readiness/intake must fail or block when the browser profile path is unavailable instead of silently falling back to detached HTTP.

## Target default invariants

- A Douyin account without a reusable persistent browser profile is not ready for primary Intake.
- Browser validation must not silently fall through to detached HTTP in default mode.
- Preflight must not return `FALLBACK_READY` in default mode.
- Ready Check must not mark detached HTTP fallback as safe to run in default mode.
- Health/status alignment must prefer browser-profile evidence and should not mark detached HTTP as the expected Intake path in default mode.
- Main operator UI must lead the operator to browser connect/reopen/validate/challenge-solve actions.
- Manual import and HTTP fallback can be re-enabled only through explicit legacy/debug flags.

## Work log

### 2026-04-26

- Read `AGENTS.md` and confirmed repository boundaries, documentation expectations, logging expectations, and local-first SaaS-ready direction.
- Audited backend and frontend references to manual import, fallback, browser health alignment, validation, preflight, and Intake readiness.
- Created this log before runtime/UI code edits, as required by the task.
- Added explicit default-off backend flags for legacy manual import, legacy HTTP fallback, and legacy debug surfaces.
- Added explicit default-off frontend flag for legacy Douyin debug surfaces.
- Gated manual-import smoke validation and response projection so manual import no longer runs or appears by default.
- Gated detached HTTP validation, fetch client fallback, preflight fallback, Intake Ready Check safety, and browser health alignment behind explicit legacy HTTP fallback.
- Updated browser-connect recovery wording and actions so default operator guidance points to browser runtime setup, reconnect, reopen, or browser-backed validation.
- Hid manual import UI, manual-import diagnostics, detached HTTP state, and fallback diagnostics from the main operator UI unless legacy debug surfaces are enabled.
- Added/updated tests covering default browser-only behavior and explicit legacy enablement.

## Verification log

### 2026-04-26

- Passed backend verification:

  ```powershell
  set PYTHONPATH=apps/api&& python -m unittest tests.test_douyin_account_preflight tests.test_intake_discovery_service tests.test_douyin_account_service tests.test_douyin_live_fetch tests.test_douyin_browser_connect_service
  ```

  Result: `Ran 80 tests in 1.095s` / `OK`.

- Passed web typecheck:

  ```powershell
  npm run typecheck --workspace apps/web
  ```

  Result: `tsc --noEmit -p tsconfig.typecheck.json` completed with exit code 0.
