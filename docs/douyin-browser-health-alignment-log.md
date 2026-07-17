# douyin-browser-health-alignment-log.md

## Status

- Audit completed for validation flow, health projection, Intake preflight alignment, browser runtime registry reuse, and `/accounts/douyin` operator rendering.
- Root cause identified as an evidence-precedence and diagnostics mismatch, not a total absence of browser-backed validation.
- Implementation completed for canonical browser-health alignment diagnostics in the API response and `/accounts/douyin` operator UI.
- Browser-backed validation evidence is now surfaced alongside Intake path alignment so operators can see when reusable-browser success has cleared older blocked state.
- Documentation set now includes architecture, log, resume, and user-guide notes for this task.

## Audit Scope Covered

- [`AGENTS.md`](AGENTS.md)
- [`docs/douyin-hard-reset-architecture.md`](docs/douyin-hard-reset-architecture.md)
- [`docs/douyin-browser-primary-fetch-architecture.md`](docs/douyin-browser-primary-fetch-architecture.md)
- [`docs/douyin-intake-preflight-architecture.md`](docs/douyin-intake-preflight-architecture.md)
- [`docs/douyin-browser-watchdog-architecture.md`](docs/douyin-browser-watchdog-architecture.md)
- [`docs/douyin-fetch-observability-architecture.md`](docs/douyin-fetch-observability-architecture.md)
- [`docs/douyin-account-health-architecture.md`](docs/douyin-account-health-architecture.md)
- [`apps/api/src/services/douyin_account_service.py`](apps/api/src/services/douyin_account_service.py)
- [`apps/api/src/services/douyin_browser_context_registry.py`](apps/api/src/services/douyin_browser_context_registry.py)
- [`apps/api/src/services/douyin_browser_connect_service.py`](apps/api/src/services/douyin_browser_connect_service.py)
- [`apps/api/src/api/routes/douyin_accounts.py`](apps/api/src/api/routes/douyin_accounts.py)
- [`apps/api/src/schemas/douyin_accounts.py`](apps/api/src/schemas/douyin_accounts.py)
- [`apps/web/src/components/douyin-accounts/DouyinAccountsPage.tsx`](apps/web/src/components/douyin-accounts/DouyinAccountsPage.tsx)
- [`apps/web/src/types/douyin-accounts.ts`](apps/web/src/types/douyin-accounts.ts)
- focused tests in [`apps/api/tests/test_douyin_account_service.py`](apps/api/tests/test_douyin_account_service.py) and [`apps/api/tests/test_douyin_account_preflight.py`](apps/api/tests/test_douyin_account_preflight.py)

## Key Findings

1. [`DouyinAccountService.validate_account()`](apps/api/src/services/douyin_account_service.py:382) already prefers live browser-context validation before detached HTTP validation.
2. [`DouyinAccountService._validate_with_live_browser_context()`](apps/api/src/services/douyin_account_service.py:949) already allows browser-backed success to set the account back to `ACTIVE`, clear errors, and update [`last_successful_validation_at`](apps/api/src/models/source_accounts.py:51).
3. [`DouyinAccountService.preflight_fetch_readiness()`](apps/api/src/services/douyin_account_service.py:655) is already browser-profile-first for Intake, including watchdog and reopen logic.
4. [`DouyinAccountService._refresh_session_from_live_browser_context()`](apps/api/src/services/douyin_account_service.py:1015) already refreshes fetch material from the same runtime-backed browser profile before live fetch.
5. [`DouyinAccountService.to_response()`](apps/api/src/services/douyin_account_service.py:872) exposes raw persisted status plus runtime browser context fragments, but not an explicit alignment summary.
6. [`DouyinAccountsPage`](apps/web/src/components/douyin-accounts/DouyinAccountsPage.tsx:504) renders one health/status surface and a browser-context badge, but it does not explain whether blocked state is stale, browser-derived, HTTP-derived, retryable, or already superseded by stronger browser-backed evidence.

## Exact Root Cause

The main bug is not that validation never uses the browser profile. The main bug is that the system does not clearly surface evidence precedence and path alignment for browser-backed accounts.

Current behavior allows this operator-visible mismatch:

- the persistent browser profile is visibly openable or live,
- Intake is prepared to use that browser-backed path,
- but the account row can still present a blocked-looking status trail without telling the operator whether that block came from older detached validation, retryable browser prevalidation, or current browser-backed evidence.

So the root cause is:

- insufficient canonical diagnostics around **which path produced the current effective health judgment**, and
- insufficient operator-visible distinction between **interactive browser availability**, **automated browser-backed validation success/failure**, and **detached HTTP/session fallback state**.

## Policy Chosen

For browser-profile-backed accounts:

- browser-backed validation is the strongest evidence,
- successful browser-backed validation must clear stale blocked state,
- validation and Intake should report whether they are path-aligned on the same browser profile/runtime,
- detached HTTP failure must remain fallback-only evidence and must not dominate browser-primary account health messaging.

## Files Changed

- [`apps/api/src/schemas/douyin_accounts.py`](apps/api/src/schemas/douyin_accounts.py)
- [`apps/api/src/services/douyin_account_service.py`](apps/api/src/services/douyin_account_service.py)
- [`apps/api/tests/test_douyin_account_service.py`](apps/api/tests/test_douyin_account_service.py)
- [`apps/web/src/types/douyin-accounts.ts`](apps/web/src/types/douyin-accounts.ts)
- [`apps/web/src/components/douyin-accounts/DouyinAccountsPage.tsx`](apps/web/src/components/douyin-accounts/DouyinAccountsPage.tsx)
- [`apps/web/src/lib/i18n/en.json`](apps/web/src/lib/i18n/en.json)
- [`apps/web/src/lib/i18n/vi.json`](apps/web/src/lib/i18n/vi.json)
- [`docs/douyin-browser-health-alignment-architecture.md`](docs/douyin-browser-health-alignment-architecture.md)
- [`docs/douyin-browser-health-alignment-log.md`](docs/douyin-browser-health-alignment-log.md)
- [`docs/douyin-browser-health-alignment-resume.md`](docs/douyin-browser-health-alignment-resume.md)
- [`docs/douyin-browser-health-alignment-user-guide.md`](docs/douyin-browser-health-alignment-user-guide.md)

## Implementation Summary

- Added [`DouyinBrowserHealthAlignmentSummary`](apps/api/src/schemas/douyin_accounts.py:56) and attached it to [`DouyinAccountResponse`](apps/api/src/schemas/douyin_accounts.py:72).
- Updated [`DouyinAccountService.to_response()`](apps/api/src/services/douyin_account_service.py:873) to compute canonical browser-health alignment diagnostics using persisted account state plus reusable-browser runtime summary data.
- Added [`DouyinAccountService._browser_health_alignment_summary()`](apps/api/src/services/douyin_account_service.py:933) to expose:
  - interactive browser state,
  - automated browser validation state,
  - detached HTTP fallback state,
  - effective validation path,
  - expected Intake path,
  - validation/Intake alignment,
  - stale blocked state cleared visibility,
  - operator-safe summary/detail text.
- Updated [`DouyinAccountsPage`](apps/web/src/components/douyin-accounts/DouyinAccountsPage.tsx:550) to render the new diagnostics inside the account row details panel.
- Added matching frontend types in [`apps/web/src/types/douyin-accounts.ts`](apps/web/src/types/douyin-accounts.ts) and i18n labels in [`apps/web/src/lib/i18n/en.json`](apps/web/src/lib/i18n/en.json) and [`apps/web/src/lib/i18n/vi.json`](apps/web/src/lib/i18n/vi.json).
- Added focused regression coverage in [`apps/api/tests/test_douyin_account_service.py`](apps/api/tests/test_douyin_account_service.py:217).

## Verification Notes

- Audit findings are based on direct source inspection of the API service, browser context registry, schemas, routes, web UI, and focused tests.
- Backend verification passed with `set PYTHONPATH=apps/api&& python -m unittest apps.api.tests.test_douyin_account_service`.
- Frontend verification passed with `npm run typecheck` executed from [`apps/web/package.json`](apps/web/package.json).
- Result: browser-backed validation, stale blocked override visibility, and Intake-path alignment diagnostics are now exposed without changing the canonical account model or Intake flow.

## Remaining Edge Cases

- The new alignment summary is derived from persisted validation data plus current runtime summary, so it still depends on operators rerunning browser-backed validation when a saved profile exists but the latest browser evidence is old.
- Vietnamese wording in [`apps/web/src/lib/i18n/vi.json`](apps/web/src/lib/i18n/vi.json) is serviceable but may need later product-language polish.
