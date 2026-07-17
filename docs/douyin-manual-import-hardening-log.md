# Douyin Manual Import Hardening Log

## Step: harden manual-imported Douyin accounts into a first-class fetch path

Started: 2026-04-23

Status: completed

## Findings

- `/accounts/douyin` manual import UI currently sends:
  - `display_name`
  - `session_cookie`
  - `user_agent`
  - `proxy_url`
  - `notes`
  - `metadata_json.connection_source=manual_import`
- `DouyinAccountConnection` persists:
  - `session_secret_blob`
  - `user_agent`
  - `headers_json`
  - `proxy_url`
  - health/validation fields
- Canonical runtime fetch currently expects:
  - Cookie header string
  - User-Agent string
  - optional proxy URL
- Manual imports can currently submit JSON cookie exports through the same `session_cookie` textarea.
- Secondary fragility:
  - imported JSON cookie export may be stored without being normalized into the canonical Cookie-header-ready runtime shape
  - missing User-Agent may be silently masked by global defaults instead of being classified as a manual-import usability issue

## Decisions

- Define one canonical runtime shape:
  - `Cookie` header string
  - `User-Agent`
  - optional `proxy_url`
- Normalize imported session data once in `DouyinAccountService`, not ad hoc in intake/fetch paths.
- Reject malformed imports early with structured validation errors.
- After manual import persistence, run a lightweight smoke validation before treating the account as usable.
- Keep one canonical fetch-client construction path for browser-backed and manual-imported accounts.

## Files Touched

- `apps/api/src/services/douyin_account_service.py`
- `apps/api/src/api/routes/douyin_accounts.py`
- `apps/api/src/services/intake_discovery_service.py`
- `apps/api/src/api/routes/intake.py`
- `apps/api/tests/test_douyin_account_service.py`
- `apps/api/tests/test_intake_discovery_service.py`
- `apps/web/src/components/douyin-accounts/DouyinAccountsPage.tsx`
- `apps/web/src/types/intake.ts`
- `apps/web/src/lib/api.ts`
- `docs/douyin-manual-import-hardening-log.md`
- `docs/douyin-manual-import-hardening-resume.md`
- `docs/douyin-manual-import-hardening-architecture.md`
- `docs/douyin-manual-import-hardening-user-guide.md`

## Verification Notes

- Existing intake wiring bug is already fixed.
- This step focuses on making manual import truly usable and diagnosable, not merely storable.
- Focused tests passed:
  - `python -m unittest tests.test_douyin_account_service tests.test_intake_discovery_service`
- Web typecheck passed:
  - `npm --workspace @reup-douyin/web run typecheck`
- API behavior verified:
  - missing User-Agent on manual import returns `422` with structured `code=imported_session_missing_user_agent`
  - imported accounts with unusable session material are smoke-validated and marked `BLOCKED`/`INVALID` instead of appearing silently usable
  - `/intake` continues to use the canonical account resolution path and now refuses unusable imported accounts with classified diagnostics
  - explicitly selected blocked imported account now returns `code=blocked_response` instead of a generic availability error
