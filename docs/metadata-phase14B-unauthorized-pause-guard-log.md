# Phase 14B Unauthorized Pause Guard Log

## Exact root cause

- The false `Harvest paused` UI was coming from `apps/extension-douyin-capture/src/popupProgress.ts`.
- Concrete caller:
  - `canonicalHarvestStatus(progress)` inferred `paused` from stale heuristics such as `can_resume`, `pending_count > 0`, and stale heartbeat.
  - `normalizeHarvestState(progress)` then rewrote the visible panel state to `harvest_status = "paused"` / `phase = "paused"` even when runtime V2 had no valid `pause_reason`.
- At the same time, progress counters were still trusting cached runtime fields (`counts.flushed`, `current_target_index`) instead of rebuilding from `target_status`, which allowed impossible combinations like `target index 15 / 53` with only `updated 5`.

## Allowed pause reasons

- `operator_stop`
- `backend_flush_failed`
- `content_script_unavailable`
- `detector_unavailable`
- `captcha_required`
- `calibration_invalid`
- `consecutive_failures`
- `pending_flush_unavailable`

## transitionHarvestRuntime behavior

- All runtime `status` / `phase` / `pause_reason` changes now go through `transitionHarvestRuntime(...)`.
- Unauthorized pause requests are rejected.
- Rejected pause attempts append a transition log entry with reason `rejected_unauthorized_pause`.
- Runtime normalization auto-recovers stale `paused` without a valid `pause_reason` back to `running/loading_target` with reason `auto_recovered_unauthorized_pause`.

## Counter invariant fixes

- `processed = updated + failed + skipped`
- `remaining = target - processed`
- `current_target_index = first pending/processing target index`
- `flushed_count` now means flushed item count, derived from `updated_count - pending_flush`
- `flush_attempt_count` is tracked separately

## Runtime transition log

- Canonical runtime now carries `state_transition_log`
- Ring buffer size: last 50 transitions
- Popup maintenance action `Show Runtime Transitions` renders the latest entries for diagnosis

## Tests run

- `npm --workspace @reup-douyin/extension-douyin-capture run typecheck`
- `npm --workspace @reup-douyin/extension-douyin-capture run test`

## Live retest steps

1. `npm --workspace @reup-douyin/extension-douyin-capture run build`
2. Reload the unpacked extension
3. Open a calibrated Douyin modal batch page
4. Start `Smart Capture & Harvest`
5. Confirm after target `#1` success:
   - title stays `Harvest running`
   - no `Resume Harvest`
   - next target advances automatically
6. Let the run pass several targets and confirm:
   - `current_index` equals first pending target from the queue
   - `Flushed` never exceeds `Updated`
7. Click `Show Runtime Transitions` and verify state changes show `running/loading_target -> extracting -> loading_target -> flushing` without unauthorized `paused`
8. Click `Stop Harvest` and confirm the only paused state shown is `Pause reason: operator_stop`
