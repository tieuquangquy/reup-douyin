# douyin-browser-connect-retry-log.md

## Step
- Implement browser connect retry + timeout handling + polling UX for [`/accounts/douyin`](apps/web/src/components/douyin-accounts/DouyinAccountsPage.tsx:56) by reusing canonical browser-assisted connect architecture.

## Time Started
- 2026-04-22 (UTC)

## Findings
- Canonical backend lifecycle is in [`DouyinBrowserConnectService`](apps/api/src/services/douyin_browser_connect_service.py:109).
- Existing backend states are `PENDING`, `LAUNCHING_BROWSER`, `WAITING_FOR_LOGIN`, `CAPTURING_SESSION`, `VALIDATING`, `COMPLETED`, `FAILED`, `CANCELLED` in [`DouyinBrowserConnectSessionStatus`](apps/api/src/enums/__init__.py:66).
- Existing API endpoints already provide one canonical session flow:
  - start: [`POST /douyin-accounts/browser-connect/start`](apps/api/src/api/routes/douyin_accounts.py:104)
  - poll: [`GET /douyin-accounts/browser-connect/{connect_session_id}`](apps/api/src/api/routes/douyin_accounts.py:115)
  - cancel: [`POST /douyin-accounts/browser-connect/{connect_session_id}/cancel`](apps/api/src/api/routes/douyin_accounts.py:126)
- Existing UI polling exists in [`useEffect()`](apps/web/src/components/douyin-accounts/DouyinAccountsPage.tsx:85) with fixed 2s interval and terminal stop only for `COMPLETED|FAILED|CANCELLED`.
- Current timeout behavior is partial:
  - Login wait timeout exists via capture timeout -> `login_timed_out` in [`PlaywrightDouyinBrowserSessionCapture.capture()`](apps/api/src/services/douyin_browser_connect_service.py:53)
  - No explicit terminal `TIMED_OUT` status in persisted session enum.
  - No explicit backend `remaining_seconds` / phase deadline fields in session response schema [`DouyinBrowserConnectSessionResponse`](apps/api/src/schemas/douyin_accounts.py:115).
- Retry currently means user presses start again; no explicit retry contract and no active-session guard in [`start_connect()`](apps/api/src/services/douyin_browser_connect_service.py:121).

## Current Lifecycle Inventory
- Runtime preflight at start: [`_runtime_probe()`](apps/api/src/services/douyin_browser_connect_service.py:293)
- Background state transitions:
  - start -> `LAUNCHING_BROWSER`
  - worker thread sets `WAITING_FOR_LOGIN` then `CAPTURING_SESSION` then `VALIDATING` then terminal state in [`_run_background()`](apps/api/src/services/douyin_browser_connect_service.py:202)
- Cancel support exists in [`cancel_session()`](apps/api/src/services/douyin_browser_connect_service.py:157).

## Timeout/Retry Gaps
- No explicit timeout outcome field separate from generic `FAILED`.
- No source-of-truth response fields for countdown/expiry.
- No guard against duplicate active attempts per workspace.
- UI polling does not protect against stale updates when session changes quickly.
- UI action model lacks explicit retry/cancel/timeout-specific controls and guidance policy.

## Decisions Made
- Keep one canonical connect session model/endpoints/service; no second pipeline.
- Keep DB enum unchanged for V1 safety; encode timeout terminal outcome via backend-derived `outcome` + typed `error_code` while status remains canonical persisted value.
- Introduce backend source-of-truth timeout fields in response (phase + deadline + remaining seconds + outcome).
- Retry policy V1: retry always creates a new session only from terminal/idle; active session must be cancelled first.

## Files Touched
- [`docs/douyin-browser-connect-retry-log.md`](docs/douyin-browser-connect-retry-log.md)
- [`apps/api/src/schemas/douyin_accounts.py`](apps/api/src/schemas/douyin_accounts.py:115)
- [`apps/api/src/services/douyin_browser_connect_service.py`](apps/api/src/services/douyin_browser_connect_service.py:128)
- [`apps/web/src/types/douyin-accounts.ts`](apps/web/src/types/douyin-accounts.ts:104)
- [`apps/web/src/components/douyin-accounts/DouyinAccountsPage.tsx`](apps/web/src/components/douyin-accounts/DouyinAccountsPage.tsx:150)
- [`apps/web/src/lib/i18n/en.json`](apps/web/src/lib/i18n/en.json)
- [`apps/web/src/lib/i18n/vi.json`](apps/web/src/lib/i18n/vi.json)
- [`apps/api/tests/test_douyin_browser_connect_service.py`](apps/api/tests/test_douyin_browser_connect_service.py:12)

## Verification Notes
- Web typecheck passed via [`tsc --noEmit -p tsconfig.typecheck.json`](apps/web/package.json:6).
- API browser-connect unit tests passed: 5/5 in [`test_douyin_browser_connect_service.py`](apps/api/tests/test_douyin_browser_connect_service.py:12).
- `pytest` is unavailable in current Python runtime (`No module named pytest`), so API verification used `unittest` command path.

## Status
- Backend and frontend contract/UX implementation completed for response-derived outcome/phase/can_retry/can_cancel semantics.
- Scenario-level end-to-end verification and final user-flow documentation are in progress.
