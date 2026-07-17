# Phase 22C-5 — Captcha/checkpoint safe scheduler resume notes

## Operator states

Phase 22C-5 uses concise operator wording:

- **Attention needed**: Douyin is showing captcha, security verification, login, abnormal traffic, or similar user-action condition.
- **Reconnect Douyin tab**: the tab is blank, lost, blocked, stale, or not a valid active Douyin context.
- **Paused safely**: the extension stopped at a checkpoint and preserved progress.

## Resume preflight

Resume is available only when the safety state is safe, recoverable, or stale and no user action is currently required. If the stored safety status is `needs_attention`, `blocked`, or `fatal`, resume preflight keeps the run paused, writes a safety checkpoint, and updates the pause message.

## What is preserved

Safety stops preserve:

- Profile URL.
- Capture session id.
- Calibration.
- Harvest queue.
- Current index and aweme where available.
- Saved/failed/pending counters.
- Backend proof state.

Safety stops clear:

- Active collection task.
- Collection action lock.
- Blind continuation state.

## Manual recovery steps

1. Open the Douyin tab used by the extension.
2. Complete captcha/security/login if shown.
3. If the tab is blank or not Douyin, navigate back to the intended Douyin profile.
4. Wait until the page is visibly loaded.
5. Return to the extension popup.
6. Resume only when the safety warning has cleared and Resume is enabled.
7. If Resume stays disabled, open Advanced diagnostics and check `safety_status`, `safety_reason`, and `safety_checkpoint`.

## Failure semantics

- Captcha/login/security: stop as `needs_attention`; user must resolve manually.
- Tab lost/not Douyin/extension/local page: stop as blocked/reconnect path.
- Modal timeout/readiness timeout: stop as recoverable unless a safety block appears.
- Modal aweme mismatch: stop as data integrity mismatch; do not save.
- Extraction timeout: stop through watchdog timeout; do not save stale extraction results.
- Backend save/verify failure: existing verified-save policy remains in force; no fake success.
- Stale running heartbeat: pause safely, clear lock, and write a stale checkpoint.

## Manual retest checklist

1. Run Scan Profile on a Douyin profile.
2. Run Test 3 Videos and confirm calibration/readiness remain valid.
3. Run Safe Batch Next 10 and confirm up to 10 items are processed.
4. Trigger/login captcha manually and confirm the batch stops with **Attention needed**.
5. Close or switch away from the Douyin tab and confirm the batch does not continue blindly.
6. Open a wrong modal id and confirm mismatch stops without saving.
7. Simulate stale state and confirm the action lock clears with a stale checkpoint.
8. Resolve the issue and confirm Resume only becomes available when safe.
