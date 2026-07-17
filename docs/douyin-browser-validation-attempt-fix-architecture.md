# douyin-browser-validation-attempt-fix-architecture.md

## Objective

Fix browser-backed Douyin validation diagnostics so each Validate run presents one truthful attempt-scoped snapshot.

The fix must prevent stale auto-reopen metadata from older attempts from appearing beside a later active-runtime browser validation result. It must also classify browser-context challenge/captcha/blocked responses explicitly instead of collapsing them into generic `browser_validation_inconclusive`.

## Audited Bug

Current metadata fields are persisted directly in `DouyinAccountConnection.metadata_json` with names such as:

- `last_browser_validation_auto_reopen_attempted`
- `last_browser_validation_reopen_status`
- `last_browser_validation_runtime_reattached`
- `last_browser_validation_continued_after_reopen`
- `last_browser_validation_final_category`
- `last_browser_context_reason`

The old implementation writes some fields during an auto-reopen attempt, then later validation attempts read those same fields without checking whether they belong to the current attempt.

The most visible bug is that a later active-runtime validation can produce `browser_validation_inconclusive` with `browser_context_blocked_response`, while the browser health alignment panel still renders older `reopen failed`, `runtime reattached no`, or `validation continued no` fields.

## Attempt-Scoped Model

Each browser-backed Validate attempt should create a fresh diagnostics scope with:

- `last_browser_validation_attempt_id`
- `last_browser_validation_attempt_started_at`
- current context status/reason/runtime id
- current final category
- current auto-reopen fields only if the current attempt actually attempted reopen
- current challenge category and recommended next action

The implementation may still persist only the latest attempt snapshot in the account metadata. It does not need a new table for this phase. The key requirement is that old attempt-specific fields are removed or overwritten at the start of each browser validation attempt.

## Challenge And Captcha Classification

Browser context probe status `blocked` with reason `browser_context_blocked_response` is not the same as a generic unknown inconclusive result. It means the live browser reached Douyin but encountered challenge/captcha/security verification signals.

Canonical categories:

- `browser_validation_captcha_required`: explicit captcha marker.
- `browser_validation_challenge_required`: security challenge/verification marker.
- `browser_validation_manual_verification_required`: generic browser-context blocked response requiring manual action.
- `browser_validation_inconclusive`: reserved for weaker uncertain results without a stronger challenge/captcha classification.

## Precedence Rules

- Active browser runtime means a browser context is open and attached; it does not mean validation passed.
- If runtime is active and the probe sees captcha/challenge, the final category should be the challenge/captcha category.
- Reopen fields are shown only for the same current attempt and only when reopen was actually attempted.
- Active runtime plus challenge should not render as reopen failed unless the same attempt first failed reopen.

## Projection Contract

`browser_health_alignment` should expose:

- current runtime state
- current browser validation state
- current final category
- current challenge category if present
- current recommended next action
- auto-reopen fields scoped to the current attempt

The web UI should render current-attempt fields and avoid displaying stale reopen diagnostics from older attempts.

## Non-Goals

- No second account model.
- No second discovery or intake path.
- No crawler/video-processing changes.
- No raw cookies, auth tokens, or secrets in logs/UI.
