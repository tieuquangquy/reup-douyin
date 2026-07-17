# Phase 13F Harvest State Resume Fix Log

## Scope

Phase 13F is limited to `apps/extension-douyin-capture` and extension-facing documentation. It fixes the popup/controller inconsistency where a stopped harvest could still expose stale `current_state = harvesting` and `phase = extracting_metrics`, leaving Smart Harvest stuck at target index `1 / 53`.

## Root Cause

The extension had no single source of truth for harvest lifecycle. Popup rendering combined `running`, `current_state`, `phase`, `stopped_reason`, and `can_resume` independently. A restored or stopped controller could therefore show `Harvest paused` while the phase badge still said `Extracting metrics...`. Resume also probed first and could block on a stale probe before restarting the saved harvest orchestrator.

## Canonical Harvest Status

Added canonical `harvest_status` with values:

- `idle`
- `running`
- `paused`
- `completed`
- `completed_with_warnings`
- `failed`

The popup now normalizes display state before rendering and button sync. Controller progress and persisted state include the canonical status.

## normalizeHarvestState Behavior

`normalizeHarvestState` maps impossible states into safe display states:

- `harvest_status = running` keeps `current_state = harvesting` only when the heartbeat is fresh.
- stale running heartbeat becomes `paused` with `stopped_reason = harvest_loop_inactive`.
- stopped/paused raw state with stale `phase = extracting_metrics` becomes `phase = paused`.
- completed and failed states force matching `current_state` and `phase`.

## Resume Behavior

Resume still calls `REUP_DOUYIN_RESUME_FULL_MODAL_HARVEST`, which creates a controller from stored state and calls `start()`. The controller uses target status to find the first pending target, so target `1` marked `updated` advances to target `2`. Popup resume no longer lets a stale probe freeze restart when a resumable target queue exists.

## Progress Panel Rendering Rules

Paused display always renders:

- title: `Harvest paused`
- badge: `Paused`
- no running state
- Resume guidance

Running display renders:

- title: `Harvest running`
- current active phase badge
- polling remains active

Impossible display `Harvest paused + Extracting metrics...` is covered by tests.

## Tests Run

Pending final verification commands:

```bash
npm --workspace @reup-douyin/extension-douyin-capture run test
npm --workspace @reup-douyin/extension-douyin-capture run typecheck
npm --workspace @reup-douyin/extension-douyin-capture run build
```

## Live Retest Steps

1. Open a Douyin profile, run profile capture, then open the first modal video.
2. Start Smart Capture & Harvest with a target queue of multiple videos.
3. Stop or reload while target `1 / 53` is visible.
4. Reopen the popup and confirm the panel shows `Harvest paused` with badge `Paused`, not `Extracting metrics...`.
5. Click Resume Harvest.
6. Confirm the popup changes to `Harvest running` and target index advances to `2 / 53` after target 1 is processed/recognized as updated.
7. Confirm stale `Last probe` does not block Resume when the saved target queue exists.
