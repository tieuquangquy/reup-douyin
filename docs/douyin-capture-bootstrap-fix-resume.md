# Douyin Capture Bootstrap Fix Resume

## Current task

Fix the managed-browser bootstrap path for the Douyin capture-current-page model so Reopen profile reliably restores an app-managed runtime from the saved persistent profile, and downstream actions depend on that runtime.

## User-visible problem

The UI reports:

- Manual challenge required.
- profile_reopen_failed.
- first_page_closed_early: TargetClosedError.
- Managed runtime status: no app-managed runtime.
- Runtime attach status: live runtime missing; same saved profile will reopen.
- Auto-reopen attempted: Yes; reopen failed.
- Runtime reattached: No.

The saved browser profile exists, but app-managed runtime bootstrap/reopen is unstable, so current-page detection/capture cannot be reliable.

## Non-negotiable requirements

- Open profile and Reopen profile must restore an app-managed runtime from the same saved persistent browser profile.
- If the remembered first page is closed, recover within the same context/profile instead of failing immediately.
- Mark challenge solved, Detect current page, and Capture current page must require and reuse the same managed runtime.
- Capture current page must remain disabled until managed runtime is truly active and page classification is supported.
- No new profile may be created for an account that already has saved browser profile metadata.

## Files already audited

- AGENTS.md.
- apps/api/src/services/douyin_browser_context_registry.py.
- apps/api/src/services/douyin_browser_connect_service.py.
- apps/api/src/services/douyin_account_service.py.
- apps/api/src/services/douyin_current_page_capture_service.py.
- apps/api/src/api/routes/douyin_accounts.py.
- apps/web/src/components/douyin-accounts/DouyinAccountsPage.tsx.

## Key findings

- Open/Reopen from the UI currently starts a browser-connect session rather than directly calling the stable account-profile bootstrap path.
- Browser-connect persistent profile capture still performs login/cookie/prevalidation workflow and can fail before a stable runtime is established.
- open_profile_for_account is closer to the desired bootstrap path, but needs stronger first-page closure recovery and page-ready verification.
- _page_for_context can reacquire/create pages, but it does not expose precise statuses and does not retry context.new_page after transient first-page closure failures.
- _ensure_usable checks context cookies only, not page availability.
- Current-page capture already refuses capture when snapshot is unavailable, but the UI only disables Capture based on supported_capture from the latest detection.
- Mark challenge solved enters validation flow, which should explicitly bootstrap/reuse the app-managed runtime before post-challenge validation.

## Expected touched files

Backend:

- apps/api/src/services/douyin_browser_context_registry.py.
- apps/api/src/services/douyin_browser_connect_service.py.
- apps/api/src/services/douyin_account_service.py.
- apps/api/src/services/douyin_current_page_capture_service.py.
- apps/api/src/schemas/douyin_accounts.py if response projection requires new fields.
- apps/api/tests/test_douyin_browser_context_registry.py or a new focused registry test file.
- apps/api/tests/test_douyin_current_page_capture_service.py.
- Existing Douyin challenge/account tests if present.

Frontend:

- apps/web/src/components/douyin-accounts/DouyinAccountsPage.tsx.
- apps/web/src/types/douyin-accounts.ts if response types change.
- apps/web/src/lib/i18n/en.json.
- apps/web/src/lib/i18n/vi.json.

Docs:

- docs/douyin-capture-bootstrap-fix-log.md.
- docs/douyin-capture-bootstrap-fix-resume.md.
- docs/douyin-capture-bootstrap-fix-architecture.md.
- docs/douyin-capture-bootstrap-fix-user-guide.md.

## Completed implementation steps

1. Reviewed `_validate_with_live_browser_context` in `apps/api/src/services/douyin_account_service.py` and kept Mark challenge solved on the canonical browser-profile validation path.
2. Updated the browser-connect existing-account flow in `apps/api/src/services/douyin_browser_connect_service.py` so saved-account Open/Reopen calls `open_profile_for_account` directly before validation-heavy capture behavior.
3. Hardened registry page recovery in `apps/api/src/services/douyin_browser_context_registry.py`:
   - Returns `page_reacquired_same_context` when another page is recovered from `context.pages`.
   - Returns `page_created_same_context` when a new page is created in the same context.
   - Retries new page creation for transient first-page closure cases.
   - Classifies page recovery failure as `managed_runtime_reopen_failed`.
4. Updated `_ensure_usable` to verify both context cookies and recoverable page availability.
5. Kept current-page detection/capture tied to runtime snapshots and made capture reject non-active managed runtime snapshots with `capture_not_ready_runtime_missing`.
6. Updated account projection so saved profile and live managed runtime are shown separately, using live registry truth when available.
7. Gated frontend buttons:
   - Detect current page is disabled until managed runtime is active.
   - Capture current page requires `managed_runtime_active` and supported page classification.
   - Status text now exposes reopen failure and page recovery states.
8. Added focused backend tests for bootstrap recovery, reopen failure classification, and one-profile runtime reuse behavior.
9. Updated docs with final implementation and verification results.

## Verification commands run

From the repository root on Windows:

```powershell
python -m py_compile apps/api/src/services/douyin_browser_context_registry.py apps/api/src/services/douyin_browser_connect_service.py apps/api/src/services/douyin_account_service.py apps/api/src/services/douyin_current_page_capture_service.py
```

From `apps/api`:

```powershell
python -m unittest tests.test_douyin_browser_connect_service tests.test_douyin_current_page_capture_service tests.test_douyin_account_service tests.test_douyin_account_preflight tests.test_intake_discovery_service
```

From the repository root:

```powershell
npm run typecheck
```

## Current status

Implementation is complete and focused verification passed. The saved-profile Open/Reopen path now restores an app-managed runtime from the same persistent profile, closed remembered pages recover within the same context/profile, and downstream Detect/Capture actions are gated on true managed runtime readiness.
