# douyin-browser-connect-state-machine.md

## Purpose
Define the canonical browser-assisted connect state machine for `/accounts/douyin` so backend and frontend remain consistent and mutually exclusive.

## Canonical Attempt States
1. `IDLE` (frontend-only): no active connect session selected.
2. `LAUNCHING_BROWSER`: API accepted request, launcher bootstrap started.
3. `WAITING_FOR_LOGIN`: browser opened, waiting for operator to login/scan QR on real Douyin page.
4. `CAPTURING_SESSION`: authenticated cookie/session capture in progress.
5. `VALIDATING`: captured session is being validated through canonical account validation flow.
6. `COMPLETED` (terminal): account created and validated usable.
7. `FAILED` (terminal): attempt failed; includes explicit error metadata and next action.
8. `CANCELLED` (terminal): operator cancelled attempt.

## Required Transition Rules
- `IDLE -> LAUNCHING_BROWSER` on successful start request.
- `LAUNCHING_BROWSER -> WAITING_FOR_LOGIN` when runtime launcher is ready.
- `WAITING_FOR_LOGIN -> CAPTURING_SESSION` when authenticated session detected.
- `CAPTURING_SESSION -> VALIDATING` after capture handed to account creation/validation.
- `VALIDATING -> COMPLETED` when validation succeeds.
- `VALIDATING -> FAILED` when validation fails.
- Any non-terminal state -> `CANCELLED` if operator cancels.
- Any non-terminal state -> `FAILED` on unrecoverable error.

## Runtime Unavailable Rule (Critical)
- `browser_runtime_unavailable` MUST map to `FAILED` for that attempt.
- Runtime-unavailable attempts must not remain in `LAUNCHING_BROWSER`/pending states.
- UI must not show success/running banners once this failure is known.

## Terminal Failure Metadata
For `FAILED`, backend response should provide explicit rendering inputs:
- `status = FAILED`
- `error_code` (for example `browser_runtime_unavailable`)
- `error_message` (safe operator-facing reason)
- `next_action` (for example `setup_runtime` or `use_manual_import`)
- `manual_fallback_available = true`
- `runtime_available` (if determinable)

## UI Mapping (Mutually Exclusive)
- `IDLE`: neutral instructions + connect CTA.
- Running states (`LAUNCHING_BROWSER`, `WAITING_FOR_LOGIN`, `CAPTURING_SESSION`, `VALIDATING`): single progress block only.
- `COMPLETED`: single success block only.
- `FAILED`: single error block + next-action guidance + manual fallback CTA.
- `CANCELLED`: single neutral/cancelled block with restart CTA.

## Manual Fallback Behavior
- Manual session import remains the same canonical account creation flow.
- On `FAILED` with `browser_runtime_unavailable`, UI must prominently surface manual import fallback.
- Fallback should be operator-actionable immediately (visible section anchor/CTA text).

## Non-Goals
- No second browser connect pipeline.
- No duplicate account model.
- No native QR protocol reverse-engineering.
- No large module redesign.
