# Phase 17C Safe Runner Continuous Loop Log

Phase 17C moves Douyin modal harvest loop ownership into the content script Safe Runner and uses one canonical local state record.

## Scope

Changed extension-only runtime/state/popup wiring under `apps/extension-douyin-capture`. No backend, web gallery, calibration workflow, crawler, CDP, or auto-publish behavior was changed.

## Root Cause

The extension had two competing runtime concepts: the older runtime stored under `douyinHarvestRuntimeV2` and a projected safe-run state stored under `douyinSafeHarvestRun`. Popup and progress rendering could observe projected state while the long-running content-script loop used the older runtime. The loop also marked a target `updated` before backend flush success, then returned or paused from stale/generic phases in several paths. That combination made the operator see inconsistent `running`/`paused` state and made successful extraction capable of looking complete without a durable backend commit.

## Phase 17C Runtime Decisions

- Canonical runtime key: `douyinSafeHarvestRun`.
- Canonical schema version: `phase17c_safe_runner`.
- Content-script singleton: `window.__REUP_DOUYIN_SAFE_HARVEST_RUNNER`.
- Legacy `window.__REUP_DOUYIN_HARVEST_RUNNER_V2` remains only as an alias to the same runner for command compatibility.
- Legacy harvest storage keys are cleared before loading/rendering safe-run progress.
- Start no longer requires a current modal probe; calibration must exist, then the runner can open the first target directly.

## Continuous Loop

The Safe Runner loop keeps a `while (true)` drain pattern:

1. load canonical state from `douyinSafeHarvestRun`;
2. exit only if run id changed, status is not `running`, or abort signal is set;
3. heartbeat and persist;
4. find first pending target;
5. process one target;
6. continue the loop after success instead of returning.

## Commit Ordering

For each target, the runner now follows:

1. mark target `processing`;
2. open direct modal URL if needed;
3. wait target modal metrics;
4. extract metrics;
5. validate phase;
6. place exactly the validated item in the pending flush queue;
7. flush to backend;
8. only after backend success mark target `updated` and append OK recent item;
9. advance to the next pending target.

Backend flush failure keeps the pending item and pauses with `backend_flush_failed`.

## Direct Modal Navigation

Primary navigation updates the current profile/video URL to include `?modal_id=<aweme_id>` via content-script history state and dispatches `popstate`. ArrowDown is not used as primary runner navigation.

## Allowed Pause Reasons

The allowed safe-run pause reasons are:

- `operator_stop`
- `backend_flush_failed`
- `content_script_unavailable`
- `calibration_invalid`
- `captcha_required`
- `consecutive_failures`
- `harvest_loop_inactive`

Unauthorized/null pause states are normalized back to running when there is an active run.

## Verification

Verified with:

```cmd
npm --workspace @reup-douyin/extension-douyin-capture run typecheck
npm --workspace @reup-douyin/extension-douyin-capture run test
```

The extension test command also runs the extension build and dist module resolution test.