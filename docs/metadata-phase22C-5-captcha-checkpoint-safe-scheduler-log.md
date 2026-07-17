# Phase 22C-5 — Captcha/checkpoint safe scheduler log

## Scope

Implemented the Phase 22C-5 safety scheduler for the Douyin extension Safe Batch Next 10 flow. The work stays inside the extension whole-profile harvest boundary and does not redesign Capture Inbox UI, increase batch size, rewrite backend save, or call the legacy runner.

## Audit summary

Existing behavior already had captcha pause, tab-health checks, pause acknowledgements, queue checkpointing, backend verification, and Safe Batch Next 10 retry/skip-completed behavior. Gaps addressed in this phase:

- Safety states were captcha-specific instead of canonical.
- Resume could be offered even while user attention was still required.
- Modal open used direct navigation without a scheduler result model.
- Metadata extraction had no per-item watchdog timeout.
- Stale running collection locks were not recovered through a safety checkpoint.
- Popup wording did not distinguish attention-needed, reconnect-tab, and safe pause cases.

## Canonical safety states

The harvest state now carries these scheduler states:

- `safe`
- `needs_attention`
- `stale`
- `blocked`
- `recoverable`
- `fatal`

The scheduler also records:

- `safety_reason`
- `safety_evidence`
- `safety_last_checked_at`
- `safety_recoverable`
- `safety_user_action_required`
- `safety_checkpoint`

## Safety checkpoint

Every safety pause builds a `douyin_safety_checkpoint.v1` checkpoint with profile/session/run/item identifiers, queue progress, safety reason/evidence, and next pending aweme. The checkpoint preserves queue, session, and calibration state while clearing the collection action lock for safe operator recovery.

## Detector behavior

`detectDouyinSafetyBlock` detects captcha/security, login walls, abnormal traffic, and access denied indicators from page title/body/url text. The popup runtime mirrors those checks in page context to avoid injecting imported extension code into the page.

## Tab context behavior

The popup runtime now checks whether the active tab still matches the harvest tab, whether it is blank/browser-error/local/extension/not-Douyin, and whether page safety text is present. Unsafe context returns a typed scheduler result instead of allowing blind continuation.

## Modal scheduler behavior

The popup runtime implements `openTargetModalWithTimeout` with:

- URL/modal id wait timeout: 8 seconds by default.
- DOM readiness timeout: 12 seconds in contract diagnostics.
- Metadata readiness timeout: 15 seconds by default.
- One retry by default for recoverable open/readiness timeout.
- No blind continuation on safety block or aweme mismatch.

## Extraction watchdog

The controller wraps `extractModalMetrics` with a 30 second timeout. Timeout produces a recoverable safety stop path through the existing modal timeout error policy instead of waiting indefinitely.

## Heartbeat and stale recovery

Collecting heartbeat fields are written into diagnostics:

- `batch_heartbeat_at`
- `batch_heartbeat_stage`
- `batch_heartbeat_aweme`

If a running collection lock is older than 90 seconds, the watchdog pauses safely, clears the action lock, writes a stale safety checkpoint, and makes recovery explicit.

## Stop policy

Unsafe conditions stop the batch, preserve queue/session/calibration, write diagnostics, and clear the action lock. Backend save/verify remains authoritative; no item is marked saved without backend verification.
