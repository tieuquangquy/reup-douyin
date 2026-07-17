# douyin-browser-connect-ui-fix-log.md

## Step
- Fix browser connect runtime error handling and UI state consistency for `/accounts/douyin`.

## Time Started
- 2026-04-22 (UTC)

## Findings
- Frontend `/accounts/douyin` stores global banners in separate `message` and `error` states in [`DouyinAccountsPage`](apps/web/src/components/douyin-accounts/DouyinAccountsPage.tsx:56).
- `startBrowserConnect()` unconditionally sets success-like message (`browserStarted`) immediately after `POST /browser-connect/start` resolves in [`startBrowserConnect()`](apps/web/src/components/douyin-accounts/DouyinAccountsPage.tsx:122).
- Polling later sets failure text when session status transitions to `FAILED` in [`pollBrowserConnect()`](apps/web/src/components/douyin-accounts/DouyinAccountsPage.tsx:143), but does not clear old success message.
- Result: contradictory UI can show both red error + green started/running message at the same time.
- Backend always creates a connect session as `LAUNCHING_BROWSER` before runtime capture attempt in [`start_connect()`](apps/api/src/services/douyin_browser_connect_service.py:119).
- Runtime unavailable is currently raised inside background capture (`ImportError -> browser_runtime_unavailable`) in [`PlaywrightDouyinBrowserSessionCapture.capture()`](apps/api/src/services/douyin_browser_connect_service.py:51), so frontend initially receives accepted session and optimistic started state.
- Current API contract lacks explicit structured fields for UI guidance (`error_code`, `next_action`, `manual_fallback_available`, `runtime_available`) in [`DouyinBrowserConnectSessionResponse`](apps/api/src/schemas/douyin_accounts.py:115).

## Root Causes
1. UI state model mixes optimistic banner state with polled backend state and allows non-mutually-exclusive rendering.
2. Backend runtime availability check occurs too late (background), creating temporary running state for attempts that are guaranteed to fail.
3. Session response contract is not explicit enough for deterministic frontend rendering logic.

## Decisions Made
- Keep one canonical browser connect pipeline; no parallel/duplicate flow.
- Make backend session/API truth authoritative for UI status rendering.
- Treat `browser_runtime_unavailable` as terminal failure for that attempt.
- Normalize response metadata to drive clear operator next steps and fallback visibility.
- Keep manual session import fallback explicit and immediately actionable.

## Files Planned
- `apps/api/src/services/douyin_browser_connect_service.py`
- `apps/api/src/schemas/douyin_accounts.py`
- `apps/api/src/api/routes/douyin_accounts.py` (if contract or error mapping requires)
- `apps/web/src/types/douyin-accounts.ts`
- `apps/web/src/components/douyin-accounts/DouyinAccountsPage.tsx`
- `apps/web/src/lib/i18n/en.json`
- `apps/web/src/lib/i18n/vi.json`
- `docs/douyin-browser-connect-state-machine.md`
- `docs/douyin-browser-connect-troubleshooting.md`

## Verification Plan
- Runtime unavailable path: only terminal failed state shown; no success/running banner leakage.
- Normal start path: running state shown and polling progresses.
- Completed path: success state only.
- Manual fallback remains clearly accessible.

## Verification Notes
- `python -m pytest apps/api/tests/test_douyin_browser_connect_service.py` failed locally because `pytest` is not installed in current environment.
- `python -m unittest apps.api.tests.test_douyin_browser_connect_service` failed from workspace root due to `ModuleNotFoundError: No module named 'src'` (module path context issue).
- Verified test execution with Windows-compatible path context:
  - `set PYTHONPATH=apps/api&& python -m unittest discover -s apps/api/tests -p "test_douyin_browser_connect_service.py"`
  - Result: `Ran 2 tests ... OK`.

## Status
- Audit complete.
- Backend/API contract updates complete.
- Frontend mutually-exclusive backend-driven state mapping complete.
- i18n fallback wording updates complete.
- Troubleshooting documentation complete.
- Task complete.
