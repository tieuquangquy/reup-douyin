# Phase 18I-J1 Readiness + Action Gating Log

## Scope

Fix Whole Profile Harvest popup readiness and action gating only.

## What changed

- Added canonical readiness selector:
  - `apps/extension-douyin-capture/src/wholeProfileHarvest/readiness.ts`
- Progress summary now renders readiness from selector output instead of stale persisted layer flags.
- Popup buttons now enable, disable, hide, and relabel from selector output.
- Added next recommended action helper in the popup.
- Added minimal backend preparation controls:
  - `Prepare Backend Session`
  - `Build Payload Preview`

## Readiness rules

- `profile_scan_ready`
  - true when verify/profile scan succeeded and accepted targets exist.
- `dry_run_ready`
  - true when dry-run status is `success` or `completed_with_warnings` and `pass > 0`.
- `extraction_ready`
  - true when at least one harvest result is `extracted`.
- `backend_session_ready`
  - true when canonical capture session status is `ready` and session id exists.
- `payload_preview_ready`
  - true when payload preview status is `ready` and preview payload exists.
- `payload_guard_passed`
  - true when payload guard result is `ok`.
- `one_item_flush_ready`
  - requires backend session, payload preview, guard pass, and no running one-item flush.
- `batch_flush_ready`
  - requires backend session and at least one extracted result without backend item id.
- `resume_ready`
  - true only for real paused states with `resume_available = true`.
- `stop_ready`
  - true only while verify, dry-run, extraction, or batch flush is running.

## Fixed inconsistency

Previous bug:

- `dry_run.pass = 3`
- `dry_run.fail = 0`
- UI still showed `Dry-run ready = no`

Cause:

- progress summary was reading stale `state.layer.dry_run_ready`

Fix:

- summary now uses `getWholeProfileHarvestReadiness(state)`

## Action gating

- Dry-run buttons require verified targets and calibration.
- Run Extraction requires verified targets and dry-run readiness.
- Flush One Item requires:
  - backend session ready
  - payload preview ready
  - payload guard passed
- Flush Batch requires:
  - backend session ready
  - extracted unflushed results
- Resume is hidden unless paused and resumable.
- Stop is shown only while a run is actively running.

## Next recommended action

Selector returns:

- `Verify Profile`
- `Calibrate 4 Points`
- `Dry-run Random 3`
- `Run Extraction`
- `Prepare Backend Session`
- `Build Payload Preview`
- `Flush One Item`
- `Flush Batch`
- `Resume after captcha`
- `Review Results`

## Tests run

- `npm --workspace @reup-douyin/extension-douyin-capture run test`
- `npm --workspace @reup-douyin/extension-douyin-capture run typecheck`
- `npm --workspace @reup-douyin/extension-douyin-capture run build`

## Next UX phase

- Reduce Whole Profile popup density further once readiness correctness is stable.
