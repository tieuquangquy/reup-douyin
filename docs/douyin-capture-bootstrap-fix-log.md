# Douyin Capture Bootstrap Fix Log

## Scope

This log tracks the managed-browser bootstrap fix for the operator-assisted Douyin capture-current-page model.

The fix must make Open profile and Reopen profile restore an app-managed runtime from the same saved persistent browser profile, then make Mark challenge solved, Detect current page, and Capture current page depend only on that stable runtime.

## Non-goals

- No crawler implementation.
- No video-processing implementation.
- No scoring/filtering rewrite.
- No new browser profile creation for an existing saved account profile.
- No direct browser automation that replaces the operator's manual Douyin login, captcha, challenge, or navigation steps.
- No legacy detached HTTP fallback as proof for current-page capture readiness.

## Audit findings

### Repository and working rules

- AGENTS.md requires reading relevant files before editing, planning non-trivial changes, keeping the change scoped, updating docs for workflow/architecture changes, and adding focused tests for behavior changes.
- The repository remains local-first but SaaS-ready. The browser runtime registry is runtime-only and must not become hidden business workflow state.

### Runtime registry

Primary file: apps/api/src/services/douyin_browser_context_registry.py.

Relevant runtime objects:

- DouyinBrowserContextSummary projects runtime status, managed runtime status, saved profile identity, and conflict status.
- _ContextRecord stores the app-managed Playwright context, preferred page, account id, persistent profile id/path, lifecycle timestamps, and reason.
- open_profile_for_account is the current app-managed persistent-profile reopen path.
- summary_for_account and watchdog_for_account project whether a live runtime exists.
- snapshot_current_page is the current-page capture boundary.

Current behavior observed during audit:

- open_profile_for_account resolves the saved profile id/path, closes stale records for the same account/profile, launches Playwright persistent context, calls _page_for_context, registers _ContextRecord, then verifies summary_for_account.
- _page_for_context returns the preferred page if usable, otherwise iterates context.pages, otherwise creates context.new_page.
- _page_for_context currently uses only one context.new_page attempt and does not classify page reacquisition versus page creation in precise result categories.
- _classify_persistent_profile_open_error maps TargetClosedError/browser closed messages to first_page_closed_early:<ExceptionClass>.
- _ensure_usable currently checks context.cookies but does not ensure a usable page is attached, so a context can be reported active while page recovery has not been validated.
- snapshot_current_page tries _page_for_record and reads URL/title/content/video links; failures mark the record invalid.

Likely failure chain for the reported UI state:

1. Reopen launches or partly launches a persistent context from the saved profile.
2. Playwright reports TargetClosedError / browser closed while the first page is being obtained or shortly after launch.
3. The catch path classifies this as first_page_closed_early:TargetClosedError.
4. No _ContextRecord is registered, so the account projects managed_runtime_missing.
5. Detect/Capture cannot rely on a stable runtime.

### Browser connect service

Primary file: apps/api/src/services/douyin_browser_connect_service.py.

Relevant behavior:

- The UI Open profile button calls startDouyinBrowserConnect with account_connection_id.
- start_connect resolves the existing account and canonical profile identity from saved metadata.
- _run_background calls PlaywrightDouyinBrowserSessionCapture.capture.
- In persistent profile mode capture uses douyin_browser_context_registry.open_login_context_and_capture.
- open_login_context_and_capture is still login/capture/prevalidation oriented: it navigates to the login URL, waits for authenticated cookies, stabilizes, prevalidates, and returns cookies.
- For the current-page model, Open/Reopen should be a runtime bootstrap first. It should not fail merely because the operator has not completed login/challenge validation yet, and it should not rely on a probe-heavy route before a stable runtime exists.

### Account service

Primary file: apps/api/src/services/douyin_account_service.py.

Relevant behavior:

- mark_challenge_solved calls _run_challenge_recovery, then validate_account.
- _run_challenge_recovery currently captures runtime_before_summary, marks metadata pending recheck, calls validate_account, then compares runtime_after_summary and saved profile identity.
- _ensure_persistent_profile_context calls douyin_browser_context_registry.open_profile_for_account and records last_browser_profile_open_* metadata.
- _validate_with_live_browser_context and surrounding validation metadata need to be reviewed/updated so Mark challenge solved uses the canonical managed runtime bootstrap path and does not treat detached HTTP or a missing runtime as success.
- to_response projects browser_context_status as profile_saved when no active runtime exists but saved profile metadata exists.
- _browser_health_alignment_summary distinguishes saved profile from live runtime, and surfaces managed_runtime_status/page_recovery_status/runtime_attach_status from validation metadata. It should be hardened so the current runtime truth is visible, not only stale metadata.

### Current-page capture service

Primary file: apps/api/src/services/douyin_current_page_capture_service.py.

Relevant behavior:

- detect_current_page calls douyin_browser_context_registry.snapshot_current_page.
- If no snapshot is available, detection returns unknown_page, supported_capture false, and recommended action open_managed_browser_profile.
- capture_current_page fails with managed_runtime_unavailable if no snapshot is available.
- Capture support is currently tied to page type profile_page/profile_feed_page and normalized profile URL.
- Additional runtime readiness/result categories should be explicit so the UI can disable Capture until managed runtime is active and page classification is supported.

### Frontend

Primary file: apps/web/src/components/douyin-accounts/DouyinAccountsPage.tsx.

Relevant behavior:

- openBrowserProfile calls startDouyinBrowserConnect(browserConnectPayload(browserForm, account)).
- Detect current page is enabled whenever the account row is not busy.
- Capture current page is disabled only when the latest detection does not have supported_capture.
- Mark challenge solved is enabled for actionable challenge state without explicit managed runtime readiness gating.

## Planned implementation direction

1. Add a dedicated account-profile bootstrap path for Open/Reopen that uses the saved persistent profile identity and registers an app-managed runtime without requiring login validation to pass first.
2. Harden _page_for_context/_page_for_record so closed preferred/first pages are recoverable by reacquiring another page in the same context or creating a new page in that same context.
3. Make _ensure_usable verify both context and a recoverable page.
4. Project precise page recovery statuses such as page_reacquired_same_context and page_created_same_context, while retaining compatibility with existing status strings where necessary.
5. Make Detect current page fail clearly when runtime is missing and expose managed_runtime_status/runtime_attach_status/page_recovery_status.
6. Make Capture current page require managed_runtime_active and supported page classification.
7. Make Mark challenge solved invoke/reuse the canonical managed runtime bootstrap before post-challenge validation.
8. Add focused backend tests for page recovery, same-profile reuse, runtime gating, and challenge bootstrap/reuse.
9. Update this log with implementation and verification results.

## Implementation status

- Audit completed before code changes.
- Mandatory docs created before code changes.
- `apps/api/src/services/douyin_browser_context_registry.py` now recovers closed remembered pages within the same Playwright context by reacquiring another usable page or creating a new page in that same context. New page creation is retried for transient first-page closure cases.
- `apps/api/src/services/douyin_browser_context_registry.py` now reports explicit recovery/failure statuses: `page_reacquired_same_context`, `page_created_same_context`, and `managed_runtime_reopen_failed`.
- `apps/api/src/services/douyin_browser_connect_service.py` now routes existing saved-account Open/Reopen sessions through `open_profile_for_account` so the browser-connect path bootstraps an app-managed runtime from the same saved profile before validation-heavy capture behavior.
- `apps/api/src/services/douyin_account_service.py` now projects live registry truth into account health alignment so saved-profile metadata is not confused with an active app-managed runtime.
- `apps/api/src/services/douyin_current_page_capture_service.py` now rejects capture unless the current snapshot is backed by `managed_runtime_active`.
- `apps/web/src/components/douyin-accounts/DouyinAccountsPage.tsx` now disables Detect until a managed runtime is active and disables Capture until the latest detection is both supported and backed by `managed_runtime_active`.
- `apps/web/src/lib/i18n/en.json` and `apps/web/src/lib/i18n/vi.json` include operator-facing labels for runtime reopen failure and the stricter Detect/Capture gating.
- `apps/api/tests/test_douyin_browser_connect_service.py` includes focused coverage for same-context page reacquisition, same-context page creation, and managed-runtime reopen failure classification.

## Verification plan

- Python compile for touched API files.
- Focused unit tests for Douyin browser context registry bootstrap behavior.
- Focused unit tests for current-page capture runtime gating.
- Existing Douyin account/current-page/intake tests touched by account projection changes.
- Web typecheck for frontend gating/types/i18n changes.

## Verification results

Passed:

- `python -m py_compile apps/api/src/services/douyin_browser_context_registry.py apps/api/src/services/douyin_browser_connect_service.py apps/api/src/services/douyin_account_service.py apps/api/src/services/douyin_current_page_capture_service.py`
- `python -m unittest tests.test_douyin_browser_connect_service`
- `python -m unittest tests.test_douyin_current_page_capture_service`
- `python -m unittest tests.test_douyin_account_service tests.test_douyin_account_preflight tests.test_intake_discovery_service`
- `python -m unittest tests.test_douyin_browser_connect_service tests.test_douyin_current_page_capture_service tests.test_douyin_account_service tests.test_douyin_account_preflight tests.test_intake_discovery_service`
- `npm run typecheck`

Note: an attempted `git status --short` and a path-limited `git diff` command failed because this workspace is not currently exposed as a Git repository to the terminal, so final review used tool-read file inspection and the verification commands above.
