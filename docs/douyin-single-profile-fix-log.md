# Douyin Single Profile Fix Log

## Findings

- The intended primary model is already documented as one
  `DouyinAccountConnection` backed by one persistent browser profile.
- The runtime registry still supports two profile allocation modes:
  - account-backed: `account-{account_id}`
  - connect-session-backed: `{workspace_prefix}-{connect_session_id}`
- Connect-session-backed profiles are acceptable only before an account exists.
  They must not replace an existing account's persisted profile identity.
- Existing-account reopen currently passes `account_connection_id` and normally
  reuses the account metadata profile, but there was no hard guard preventing a
  mismatched capture from overwriting `browser_profile_id/path`.
- `restart_session()` relied on the caller to resend `account_connection_id`.
  If a client omitted it, restart could create a new connect-session profile.
- Workspace-level active session reuse could return an unrelated active session
  while opening a specific account, which can confuse the operator and target
  the wrong profile.

## Root Causes

1. Profile identity was a convention, not an enforced invariant.
2. Restart/retry semantics depended too much on frontend payload correctness.
3. Existing-account captures could update metadata with whatever profile the
   runtime returned, even when the account already had a canonical profile.

## Decisions

- Persisted account profile metadata is authoritative when present.
- If an account has no profile metadata and an account-backed open is requested,
  the canonical allocation is `account-{account_id}`.
- Restart preserves the prior session's `derived_account_id` unless an explicit
  target account is supplied.
- Existing-account capture must fail with `profile_identity_mismatch` if the
  runtime returns a different profile id/path than the account's canonical
  identity.
- Active-session reuse is only allowed for the same target account. Different
  target account attempts must fail clearly instead of silently attaching to a
  different profile.

## Files Touched

- `apps/api/src/services/douyin_browser_context_registry.py`
- `apps/api/src/services/douyin_browser_connect_service.py`
- `apps/api/src/services/douyin_account_service.py`
- `apps/api/tests/test_douyin_browser_connect_service.py`
- `docs/douyin-single-profile-fix-log.md`
- `docs/douyin-single-profile-fix-resume.md`
- `docs/douyin-single-profile-fix-architecture.md`
- `docs/douyin-single-profile-fix-user-guide.md`

## Implementation Notes

- Added `profile_identity_for_account()` to the browser context registry.
  It resolves the canonical account profile from account metadata or falls back
  to `account-{account_id}`.
- Added `profile_identity_matches()` so connect/reopen paths can reject profile
  drift.
- Existing-account `start_connect()` now canonicalizes profile metadata before
  creating the browser connect session.
- Active browser connect sessions are reused only when they target the same
  account. Opening a different account while another profile session is running
  now fails explicitly.
- `restart_session()` preserves the previous session's `derived_account_id`
  when the caller omits `account_connection_id`.
- Background capture now refuses to bind an existing account to a different
  browser profile. The failure code is `profile_identity_mismatch`.
- Account responses now show `profile_saved` for accounts with either
  `browser_profile_id` or `browser_profile_path`, and derive a safe profile id
  from path-only metadata.

## Verification Notes

- Passed focused API tests:
  `python -m unittest tests.test_douyin_browser_connect_service tests.test_douyin_account_preflight tests.test_douyin_account_service tests.test_douyin_live_fetch tests.test_intake_discovery_service`
- Passed API compile:
  `python -m compileall src`

## Status

Completed.
