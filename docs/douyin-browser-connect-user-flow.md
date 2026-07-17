# douyin-browser-connect-user-flow.md

## Scope
- Document operator-facing lifecycle for browser-assisted Douyin connect on [`/accounts/douyin`](apps/web/src/components/douyin-accounts/DouyinAccountsPage.tsx:56).
- This flow reuses the canonical backend session pipeline in [`DouyinBrowserConnectService`](apps/api/src/services/douyin_browser_connect_service.py:116).
- No duplicate state machine is introduced.

## Canonical Session APIs
- Start session: [`POST /douyin-accounts/browser-connect/start`](apps/api/src/api/routes/douyin_accounts.py:104)
- Poll session: [`GET /douyin-accounts/browser-connect/{connect_session_id}`](apps/api/src/api/routes/douyin_accounts.py:115)
- Cancel session: [`POST /douyin-accounts/browser-connect/{connect_session_id}/cancel`](apps/api/src/api/routes/douyin_accounts.py:126)

## Backend Source-Of-Truth Fields
Session response payload now includes operator-focused fields in [`DouyinBrowserConnectSessionResponse`](apps/api/src/schemas/douyin_accounts.py:115):
- `outcome`: running/completed/failed/timed_out/cancelled
- `phase`: starting_browser/waiting_for_login/capturing_session/validating_session/completed/failed/cancelled
- `phase_deadline_at`
- `remaining_seconds`
- `timed_out_at`
- `can_retry`
- `can_cancel`

Field derivation is centralized in [`DouyinBrowserConnectService.to_response()`](apps/api/src/services/douyin_browser_connect_service.py:192).

## Operator Flow
1. Operator presses **Connect with Browser** in [`startBrowserConnect()`](apps/web/src/components/douyin-accounts/DouyinAccountsPage.tsx:127).
2. API creates one running session (guarded against overlap in [`start_connect()`](apps/api/src/services/douyin_browser_connect_service.py:128)).
3. UI polls every 2 seconds via [`pollBrowserConnect()`](apps/web/src/components/douyin-accounts/DouyinAccountsPage.tsx:150).
4. UI renders phase + remaining seconds from backend response; no optimistic phase simulation.
5. On terminal session:
   - completed -> account shown + reload accounts list
   - timed_out -> explicit timeout message and retry path
   - failed -> error code/message + next action guidance
   - cancelled -> cancelled confirmation and restart availability
6. Manual fallback remains available from status card link to `#manual-session-import` in [`DouyinAccountsPage`](apps/web/src/components/douyin-accounts/DouyinAccountsPage.tsx:315).

## Retry/Cancel Policy (V1)
- Retry is allowed only when backend marks `can_retry=true`.
- Cancel is allowed only when backend marks `can_cancel=true`.
- Starting a new session while another live session is running now returns the existing session so the UI can resume it. Stale running-looking sessions are finalized as timed out before a new session starts.

## Polling Robustness
- UI rejects stale poll updates when active session changes using [`activeConnectSessionIdRef`](apps/web/src/components/douyin-accounts/DouyinAccountsPage.tsx:68).
- Polling interval auto-stops on terminal statuses in [`useEffect()`](apps/web/src/components/douyin-accounts/DouyinAccountsPage.tsx:86).

## Verification Evidence
- Web typecheck passed with [`npm run -w apps/web typecheck`](apps/web/package.json:6).
- API service tests passed with [`python -m unittest tests.test_douyin_browser_connect_service`](apps/api/tests/test_douyin_browser_connect_service.py:12).
- Added tests verify timeout outcome mapping and action parsing in [`DouyinBrowserConnectServiceTests`](apps/api/tests/test_douyin_browser_connect_service.py:12).

## Known Limits
- There is no persisted `TIMED_OUT` enum; timeout is represented as `FAILED` + timeout-class `error_code`, then mapped to response `outcome="timed_out"` in [`_outcome_for()`](apps/api/src/services/douyin_browser_connect_service.py:430).
- Full browser-driven end-to-end validation still depends on local Playwright runtime and manual operator login conditions.
