# Phase 13F Harvest State Resume Fix Resume

## What Changed

Phase 13F introduced canonical harvest lifecycle normalization for the Douyin extension popup and harvest controller.

## Files Touched

- `apps/extension-douyin-capture/src/types.ts`
- `apps/extension-douyin-capture/src/popupProgress.ts`
- `apps/extension-douyin-capture/src/modalHarvest.ts`
- `apps/extension-douyin-capture/src/contentScript.ts`
- `apps/extension-douyin-capture/src/popup.ts`
- `apps/extension-douyin-capture/src/popupProgress.test.ts`
- `docs/metadata-phase13F-harvest-state-resume-fix-log.md`
- `docs/metadata-phase13F-harvest-state-resume-fix-resume.md`

## Canonical State

`harvest_status` is the display/action source of truth:

- `running` means active harvest loop, `current_state = harvesting`, and a fresh heartbeat.
- `paused` means resumable non-running state, `current_state = paused`, `phase = paused`.
- `completed` and `completed_with_warnings` force completed phases.
- `failed` forces failed phase.
- legacy stopped states normalize to paused/idle instead of rendering active phases.

## Heartbeat

`harvest_loop_heartbeat_at` is persisted and exposed in progress. The controller refreshes it when the loop starts and during loop iterations. Popup normalization treats a stale running heartbeat as inactive and shows Resume Harvest.

## Resume Details

Resume uses the saved target queue and status map. If target 1 is already updated, it advances to the first pending target instead of repeatedly showing `1 / 53`. Popup stale probe status does not block resume when a resumable target queue exists.

## Retest Focus

Confirm these impossible combinations cannot render:

- `harvest_status = paused` with badge `Extracting metrics...`
- `current_state = harvesting` while `harvest_status = paused`
- `harvest_status = running` forever with stale heartbeat

## Verification

Run:

```bash
npm --workspace @reup-douyin/extension-douyin-capture run test
npm --workspace @reup-douyin/extension-douyin-capture run typecheck
npm --workspace @reup-douyin/extension-douyin-capture run build
```
