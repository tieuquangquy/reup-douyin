# Douyin Challenge Flow Hardening Architecture

## Objective

Make `browser_validation_challenge_required` a first-class human-in-the-loop browser-profile state instead of a generic invalid terminal state. The system must keep one Douyin account mapped to one saved persistent browser profile, let the Windows operator solve Douyin security challenges manually in that same profile, then recheck and resume validation/intake with positive browser evidence.

## Current Audited Path

1. Browser context prevalidation runs inside `DouyinBrowserContextRegistry._prevalidate_record_context()`.
2. Captcha/security page markers return `blocked` with reason `browser_context_blocked_response`.
3. `DouyinAccountService._validate_with_live_browser_context()` maps blocked browser probes into explicit challenge categories such as `browser_validation_challenge_required`.
4. The account is currently marked invalid and the UI only tells the operator to retry validation. There is no durable manual-solve state, solve confirmation endpoint, recheck endpoint, or challenge-aware intake gate.
5. `DouyinAccountService.preflight_fetch_readiness()` can mark browser profile fetch ready when the runtime is active even if the latest browser validation is an unresolved challenge.

## Canonical State Model

The challenge flow uses account metadata and response projection to expose these state families without introducing a duplicate account model:

- `browser_validation_success`: latest browser-backed validation passed and clears challenge metadata.
- `browser_validation_inconclusive`: browser-backed validation reached the profile but did not prove success or a hard manual action.
- `browser_validation_login_required`: cookies/login are missing or expired.
- `browser_validation_challenge_required`: Douyin security challenge or captcha is present in the reusable browser profile.
- `browser_validation_blocked`: hard block not expected to be solved by a normal captcha/security challenge.
- `challenge_waiting_for_manual_verification`: operator has been instructed to solve the challenge in the already-open reusable profile.
- `challenge_recently_solved_pending_recheck`: operator clicked “I solved it”; system must rerun browser-backed validation in the same profile/runtime before intake is allowed.
- `challenge_cooldown`: repeated challenge loop reached a temporary backoff window.
- `challenge_repeat_limit_reached`: repeated challenge loop exceeded the per-account limit and must pause until operator review.

## Metadata Contract

Metadata is stored only in `DouyinAccountConnection.metadata_json` until a durable schema is introduced later. Current fields are browser-profile-only diagnostics and must not contain secrets:

- `douyin_challenge_state`
- `douyin_challenge_detected`
- `douyin_challenge_category`
- `douyin_challenge_count`
- `douyin_challenge_last_detected_at`
- `douyin_challenge_last_solved_at`
- `douyin_challenge_cooldown_until`
- `douyin_challenge_repeat_limit_reached`
- `douyin_challenge_recheck_attempt_id`
- `douyin_challenge_recheck_started_at`
- `douyin_challenge_recheck_resolved`
- `douyin_challenge_same_runtime_reused`
- `douyin_challenge_recommended_next_action`

Attempt-scoped validation metadata remains separate and is reset at the beginning of each validation attempt.

## Backend Actions

The API adds account-scoped actions:

1. Open profile for challenge solving.
   - Reuses `DouyinBrowserConnectStartRequest.account_connection_id` and existing persistent profile mapping.
   - Must not create a new profile for the account.
2. Mark challenge solved.
   - Sets `challenge_recently_solved_pending_recheck`.
   - Invalidates preflight cache.
   - Does not mark the account active by itself.
3. Recheck after solve.
   - Runs normal browser-backed validation in the same account profile/runtime.
   - Success clears challenge state and makes intake eligible.
   - Repeated challenge increments challenge count and may enter cooldown/repeat-limit state.

## Intake Gate

`preflight_fetch_readiness()` and intake ready check must reject unresolved challenge states before reporting browser-profile fetch ready. Failure codes are explicit:

- `manual_verification_required`
- `challenge_recheck_required`
- `challenge_cooldown`
- `challenge_repeat_limit_reached`

`discover()` must also stop before adapter construction if preflight fails. This prevents live fetch from silently using detached HTTP evidence or an active but unresolved browser page.

## Evidence Precedence

- Post-challenge browser validation success outranks previous challenge metadata and clears challenge fields.
- An unresolved challenge outranks active runtime/watchdog status.
- An unresolved challenge outranks detached HTTP fallback.
- Operator “I solved it” is not enough evidence; only browser-backed validation success can mark the account usable for intake.

## Non-goals

- No crawler implementation.
- No video processing implementation.
- No distributed queue or multi-user workflow.
- No new database schema in this step.
- No automated captcha solving.
- No bypassing Douyin security challenges.
