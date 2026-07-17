# Douyin Challenge Flow Hardening Log

## Status

Completed.

## Implementation Plan

1. Audit current browser challenge detection, validation projection, intake preflight, and web operator flows.
2. Write architecture, resume, and operator guide docs before major code changes.
3. Implement account-level challenge metadata/state projection.
4. Add manual solve and post-solve recheck actions.
5. Gate intake readiness and discovery while challenges are unresolved.
6. Update account and intake UI actions/diagnostics.
7. Add tests and run verification.

## Audit Findings

- `DouyinBrowserContextRegistry._prevalidate_record_context()` detects captcha/security markers and returns `blocked` with `browser_context_blocked_response`.
- `DouyinAccountService._validate_with_live_browser_context()` classifies that result into explicit challenge/captcha/manual-verification statuses.
- Current validation still marks the account `INVALID` without a dedicated pending-human-solve/resume action.
- `DouyinAccountService.preflight_fetch_readiness()` can currently report browser profile readiness from active runtime/watchdog evidence without checking unresolved challenge metadata first.
- `/accounts/douyin` exposes open/validate/use actions but no dedicated “I solved it” action.
- `/intake` ready check exposes revalidate/reopen actions but no challenge-specific action or diagnostics.

## Decisions

- Keep one account mapped to one saved persistent browser profile.
- Store challenge state in account metadata for this local-first phase.
- Treat manual solve as a checkpoint that requires a browser-backed recheck before intake can resume.
- Make unresolved challenge states strong negative browser evidence.
- Keep detached HTTP fallback below unresolved browser challenge evidence.

## Verification Commands

- `npm run typecheck --workspace apps/web`
  - Result: passed.
- `set PYTHONPATH=apps/api&& python -m unittest tests.test_intake_discovery_service tests.test_douyin_account_service`
  - Result: passed, 40 tests.

## Completed Implementation Notes

- Added first-class Douyin challenge states for unresolved manual verification, post-solve pending recheck, cooldown, and repeat-limit handling.
- Added manual challenge solve and post-solve recheck account actions.
- Made unresolved challenge metadata block Intake preflight before browser reopen or detached HTTP fallback can make the account appear ready.
- Surfaced challenge diagnostics and actions in the Douyin accounts and Intake operator UI.
- Added backend tests for blocked probe metadata, manual solve gating, successful recheck clearing, and Intake ready-check challenge blocking.
