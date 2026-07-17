# Phase 17C Safe Runner Resume Notes

## Resume Semantics

Resume is owned by the content-script Safe Runner. The popup sends a resume command and then renders canonical progress; it does not run the harvest loop.

Resume behavior:

1. load `douyinSafeHarvestRun`;
2. reject resume when there is no saved `run_id`;
3. no-op when the run is already completed or completed with warnings;
4. normalize allowed paused state back to `running`;
5. set phase to `opening_target`;
6. preserve pending, failed, skipped, and updated target statuses;
7. restart the singleton drain loop for the same run id;
8. continue at the first target whose status is `pending` or `processing`.

## Stop Semantics

Stop aborts the active runner and persists a controlled pause using reason `operator_stop`. This is the operator-requested pause path and is resumable.

## Reset Semantics

Harvest reset aborts the active runner, removes canonical and legacy harvest runtime/queue keys, then writes an idle `phase17c_safe_runner` state to `douyinSafeHarvestRun`.

## Legacy State Handling

The following state families are ignored/deleted for loop and render decisions:

- legacy harvest progress keys;
- old full-modal harvest state;
- smart capture projection state when rendering safe-run progress;
- old `douyinHarvestRuntimeV2` runtime records.

The extension keeps backward-compatible command names, but they delegate to the Safe Runner.

## Watchdog and Recovery

Phase 17C keeps the existing state-transition gate and unauthorized pause repair behavior. A running state with no allowed pause reason is normalized back to running so stale projected pause states do not stop rendering or resume. The runner heartbeats on each loop iteration and restarts from canonical state when progress is requested and a running saved state has pending work but no active singleton loop.
