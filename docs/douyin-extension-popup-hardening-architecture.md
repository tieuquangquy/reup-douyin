# Douyin Extension Popup Hardening Architecture

## Summary

The popup must treat every operator action as a bounded async operation. Each action owns its user-facing status, timeout, error mapping, diagnostics update, and cleanup.

## Action Model

Each popup action should run through one canonical wrapper:

1. Record last action.
2. Mark loading true and disable buttons.
3. Clear transient status for the relevant surface.
4. Execute the action with explicit timeout boundaries.
5. Render success or friendly error.
6. Record lightweight diagnostics.
7. Always clear loading and re-enable buttons in `finally`.

## Timeout Boundaries

- Backend HTTP calls use `AbortController` and a finite timeout.
- Active-tab/direct-execution calls use a promise timeout guard.
- Timeouts map to a friendly `backend_timeout` or `direct_execution_failed`/action-specific timeout message rather than leaving the popup busy.

## Error Categories

The popup presents stable operator categories instead of raw low-level exceptions:

- `backend_timeout`
- `backend_unreachable`
- `no_active_tab`
- `unsupported_tab`
- `challenge_page`
- `login_page`
- `detect_failed`
- `capture_failed`
- `direct_execution_failed`

## Diagnostics

The popup may show lightweight diagnostics:

- backend reachable: yes/no/unknown
- active tab detected: yes/no/unknown
- supported Douyin tab: yes/no/unknown
- last action
- last error category

Diagnostics must not include secrets, cookies, auth tokens, credentials, or private local paths.

## Boundaries

- Extension popup owns browser-local UI state and active-tab interaction.
- Backend continues to own setup status, detect validation, capture persistence, and history.
- No long-running work is added to popup code.
