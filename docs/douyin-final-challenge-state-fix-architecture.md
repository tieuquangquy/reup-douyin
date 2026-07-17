# Douyin Final Challenge State Fix Architecture

## Problem

A Douyin account can have a healthy app-managed browser runtime and reusable saved profile while still being blocked by unresolved challenge metadata. Runtime readiness and challenge readiness are separate dimensions. The final recovery state machine must avoid treating active runtime as challenge recovery.

## Canonical states

| State | Meaning | Intake | Normal Validate | Recovery action |
| --- | --- | --- | --- | --- |
| `challenge_required` | Browser validation saw a challenge and needs operator action. | blocked | allowed unless cooldown active | complete challenge then mark solved |
| `challenge_waiting_for_manual_verification` | Existing persisted equivalent of challenge required. | blocked | allowed unless cooldown active | mark solved |
| `challenge_cooldown_active` | Cooldown deadline is still in the future. | blocked | rejected | wait or mark solved after manual solve |
| `challenge_cooldown` | Persisted cooldown state; normalizes to active only while deadline is future. | blocked while active | rejected while active | mark solved after manual solve |
| `challenge_repeat_limit_reached` | Repeated challenge failures reached backoff threshold. | blocked | rejected while cooldown active | mark solved after manual solve |
| `challenge_manual_solve_pending` | Operator has indicated manual solve and recheck is running/pending. | blocked | recovery validation only | postcheck |
| `challenge_postcheck_success` | Browser-backed postcheck succeeded on same saved profile/runtime boundary. | ready | allowed | none |
| `challenge_postcheck_still_required` | Browser-backed postcheck still saw a challenge. | blocked | cooldown/backoff enforced | complete challenge then mark solved |
| `challenge_cleared_ready` | Challenge metadata cleared after real success. | ready | allowed | none |

## Transition rules

- Challenge detection increments `douyin_challenge_count` exactly through the canonical metadata updater.
- Count `1` enters `challenge_waiting_for_manual_verification`.
- Count greater than `1` enters `challenge_cooldown` with a cooldown deadline.
- Count at or above repeat limit enters `challenge_repeat_limit_reached` with a cooldown deadline.
- While cooldown is active, normal validation and intake are blocked with the response/preflight state `challenge_cooldown_active`; the persisted state remains the underlying cooldown or repeat-limit state.
- `mark_challenge_solved` and `challenge_recheck` are recovery validation sources and may run browser-backed validation despite cooldown because they represent operator confirmation that the manual browser step was completed.
- Success clears challenge fields/counters/cooldown only when browser-backed validation succeeds and the same saved profile was reused.
- Failure keeps challenge metadata explicit and recomputes cooldown/backoff through the canonical challenge detection updater.
- Runtime diagnostics and challenge diagnostics remain independent, so an active managed runtime is not presented as challenge recovery and challenge state is not presented as runtime unavailability.

## Boundaries

- `apps/api` owns authoritative state, cooldown gating, validation, preflight, and recovery transitions.
- `apps/web` only renders diagnostics and disables/actions based on API state.
- `apps/worker` is not changed for this fix.
