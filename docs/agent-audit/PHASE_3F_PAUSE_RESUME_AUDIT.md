# Phase 3F Pause/Resume Audit

## Executive summary

This was an audit-only pass. No runtime source behavior was changed.

Current Pause/Resume behavior is broadly safe for the Phase 3E/3F protected workflow:

- A normal safe Next 10 batch limit is not modeled as a paused run. It completes as `batch_safe_mode_completed` with collection state `idle`, preserves queue/calibration/session state, sets the next pending queue index, and expects the operator to continue with Start Collecting again.
- Resume is reserved for actual paused or stale-pausing collection states. It dispatches to the canonical safe-batch runner, not the legacy whole-profile modal runner.
- Resume and repeated Start Collecting both reach the one-item canonical save path, which uses profile-safe backend capture-session verification from Phase 3E.
- Pause is cooperative and checkpoint-based. It is safe, but it is not an immediate abort of an in-flight network save or modal operation.

The main product risk is UX clarity: after a 10-item safe batch with 100 pending items, the correct continuation button is Start Collecting, not Resume. That is logical in the state machine but can be confusing because the operator may interpret “continue collecting” as “resume.”

No P0 blocker was found for continuing batches after a successful 10-item safe batch, provided the operator uses Start Collecting again. The highest priority follow-up is to make this continuation model explicit in UI copy and tests.

## Current behavior map

### Normal safe batch continuation

Observed state after a successful safe batch with pending items:

- `status: "idle"`
- `phase: "batch_safe_mode_completed"`
- `workflow.collection.status: "idle"`
- `workflow.active_task: null`
- `workflow.action_lock: null`
- `harvest.status: "idle"`
- `harvest.resume_from_index` set to the next pending queue index
- `debug.last_response_summary.batch_stop_reason: "limit_reached"`
- queue and calibration preserved

Readiness treats this as ready to Start Collecting, not ready to Resume.

### Pause request

The popup has an immediate clicked-state path and then calls the controller pause action.

Controller pause request behavior:

- Writes canonical state with `phase: "harvest_pausing"`.
- Sets `workflow.collection.status: "pausing"`.
- Sets `workflow.active_task` and `workflow.action_lock` to `collect_videos`.
- Sets `harvest.pause_requested: true` and `harvest.stop_requested: true`.
- Records pause diagnostics.
- Writes a legacy `douyinSafeHarvestRun` pause signal for older content-script runtime compatibility.
- If the collection is already idle or detached, it acknowledges pause immediately and transitions to paused.

### Pause acknowledgement

The safe-batch runner checks persisted state at multiple checkpoints and acknowledges pause when it sees pause flags:

- before selecting the next target
- before the safe delay
- after the safe delay
- after an item checkpoint
- after payload finalization before backend commit
- before backend commit

Acknowledgement clears active collection locks, records `pause_acknowledged_at`, preserves queue state, and sets `resume_available: true`.

### Resume request

Resume behavior:

- Recovers stale pausing locks first.
- Finds the next pending target from the preserved queue.
- Blocks if safety state requires attention.
- Clears `pause_requested` and `stop_requested` for a runnable target.
- Sets `phase: "batch_safe_mode_resuming"`.
- Dispatches to `runBatchCollectNext10SafeMode` with `resume: true`.
- Writes legacy `douyinSafeHarvestRun` resume signal for compatibility.

### Stale popup/storage lifecycle recovery

Popup recovery handles two important lifecycle cases:

1. `pausing` with unacknowledged pause:
   - Delegates to controller stale-pausing recovery.
   - Can preserve queue/session/calibration and expose Resume.
2. ownerless stale `running` collection:
   - Converts to paused/interrupted display.
   - Clears active locks.
   - Preserves queue/calibration/session.
   - Sets `resume_available: false` and tells the operator to reload the Douyin tab and scan again.

This is conservative and safe for extension reload/runtime invalidation.

## State fields and transitions

Key fields audited:

- `workflow.collection.status`
- `workflow.active_task`
- `workflow.action_lock`
- `harvest.status`
- `harvest.pause_requested`
- `harvest.stop_requested`
- `harvest.pause_requested_at`
- `harvest.pause_acknowledged_at`
- `harvest.resume_available`
- `harvest.resume_from_index`
- `harvest.current_aweme_id`
- `harvest.pause_diagnostics`
- `harvest.collect_trace`
- `debug.last_response_summary`

Important transitions:

| Trigger | Before | After | Resume button? | Continuation action |
|---|---|---|---|---|
| Start Collecting safe batch reaches limit | running | idle / `batch_safe_mode_completed` | No | Start Collecting |
| User pauses during running collection | running | pausing, then paused | Yes after acknowledgement | Resume |
| User requests pause while detached/idle | idle/detached | paused | Yes if queue remains | Resume |
| Stale pausing lock | pausing | paused / `paused_stale_recovered` | Yes | Resume |
| Ownerless stale running after extension reload | running without owner lock | paused/interrupted | No | Reload/rescan |
| Resume with no pending targets | paused | success/completed | No | Review results |

The main state-machine distinction is intentional: `batch_safe_mode_completed` is an idle checkpoint, not a pause checkpoint.

## Resume after batch limit assessment

Resume after a normal 10-item limit is not the intended action. The safe batch finalizer uses `batch_stop_reason: "limit_reached"`, leaves the workflow idle, and preserves `resume_from_index` for diagnostics/next-target tracking. Readiness excludes `idle` from Resume eligibility and exposes Start Collecting when scan, classification, calibration, and queue are ready.

Assessment:

- Logic is safe for continuing batches.
- Repeated Start Collecting is covered by tests and uses the next pending items.
- The naming may confuse operators because “continue after first 10” sounds like Resume, but the system treats it as a fresh safe batch continuation.

Recommendation: keep the state model, but adjust copy/tests so the UI explicitly says something like “Batch complete. Click Start Collecting to collect the next 10.”

## Session reuse/reverification assessment

Resume and repeated Start Collecting are safe with respect to Phase 3E capture-session behavior.

Evidence from code audit:

- Safe batch dispatch calls the one-item canonical collection/save path.
- The one-item path calls `ensureBackendCaptureSession` with the current local session ID and profile URL.
- `ensureBackendCaptureSession` verifies backend existence and profile proof before reuse.
- Wrong-profile or unverifiable sessions are discarded and replaced with a fresh correct-profile session.
- The legacy `runRealModalExtractionHarvest` path still has unsafe direct existing-session reuse, but popup Start Collecting/Resume dispatch and tests prevent the canonical scanner path from calling it.

Assessment:

- No session P0 found in the current popup Start Collecting/Resume path.
- The legacy runner remains a risk only if reintroduced into scanner dispatch later.

## Queue/index/calibration preservation assessment

Queue, index, and calibration preservation are good in the audited paths.

Preserved across:

- safe batch completion
- repeated Start Collecting
- pause acknowledgement
- stale pausing recovery
- legacy runner quarantine/migration
- Phase 3E stale session discard/replacement

Known details:

- `harvest.current_index` advances through successful saves.
- `harvest.resume_from_index` is set to the next pending queue index.
- Queue items retain save/verification markers.
- Calibration is not cleared by collection pause/resume/batch transitions.
- Stale ownerless recovery preserves queue/calibration but intentionally disables Resume.

## UI/UX assessment

Current UI behavior is mostly consistent with the state machine:

- Running or collecting states expose Pause.
- Pausing states show Pausing and disable duplicate pause/resume action.
- Paused states expose Resume if `resume_available` and safety allow it.
- Idle `batch_safe_mode_completed` states expose Start Collecting when prerequisites are ready.

UX gaps:

1. The difference between Resume and Start Collecting is not obvious after a safe batch limit.
2. `resume_available` defaults to true in idle state, but readiness correctly prevents Resume unless the workflow is paused. This is safe but semantically noisy in diagnostics/UI conditions.
3. The footer pause/resume visibility condition includes `state.harvest.resume_available`, which may make the control visible more often than the actual enabled action allows. The button routing still reads current state and only resumes when `workflow.collection.status === "paused"`.
4. Stale ownerless recovery message is safe but may feel harsh because it disables Resume even though queue and session are preserved.

## Existing test coverage

Existing coverage is strong for controller behavior and source-route safety.

Covered:

- Pause during a harvest transitions to paused and sets `resume_available`.
- Idle/detached pause request acknowledges immediately.
- Stale pausing lock recovery preserves queue/session and exposes Resume.
- Resume dispatches to `runBatchCollectNext10SafeMode` and not `runRealModalExtractionHarvest`.
- Safe batch completion after limit returns idle `batch_safe_mode_completed` with `limit_reached`.
- Stable repeated Start Collecting processes the next 10 and reuses a verified matching session.
- Safe batch pause after current item stops before consuming all 10.
- Pause before backend commit prevents partial backend save.
- Popup source coverage verifies pause/resume clicked diagnostics and dispatcher routing.
- View model tests cover paused/pausing states and primary action behavior.

Gaps:

- No direct view-model test for `batch_safe_mode_completed` with pending items asserting primary action is Start Collecting and not Resume.
- No direct popup integration-style test for the operator path: first safe batch limit, then click primary action to collect next 10.
- No explicit Resume test where the stored session is stale/wrong-profile and Phase 3E replacement occurs during resume.
- No explicit test for a pause request arriving after backend fetch starts; current behavior is cooperative and should be documented/verified as “finishes current in-flight save, then pauses.”
- Limited lifecycle test coverage for real extension reload/content-script invalidation beyond source-text and recovery logic assertions.

## Gaps and risks ranked by severity

### P0

No P0 blocker found for continuing collection after a successful 10-item safe batch, as long as the operator uses Start Collecting again.

### P1

1. UX ambiguity after `batch_safe_mode_completed`.
   - Risk: operator expects Resume after the first 10 and may think collection is stuck because Resume is not the continuation action.
   - Fix: add explicit status/copy and tests.
2. Cooperative pause is not an immediate cancellation.
   - Risk: operator clicks Pause while a backend save is already in flight; one more item may save before pause appears acknowledged.
   - Fix: document in UI/details; optionally add an in-flight marker.
3. Footer pause/resume visibility may be broader than readiness eligibility.
   - Risk: visible disabled control can confuse operator after idle batch completion.
   - Fix: align visibility/copy to paused/running states while preserving primary action.
4. Legacy runner still contains unsafe direct session reuse if accidentally reconnected.
   - Risk: future refactor could bypass Phase 3E safeguards.
   - Fix: keep denylist/source tests; consider stronger runtime assertion if legacy path is ever invoked from scanner actions.

### P2

1. `resume_available` default true on idle state is semantically noisy.
2. Stale ownerless recovery could provide more granular guidance about why Resume is disabled.
3. Diagnostics could display “next pending index” separately from “resume from index” to avoid implying idle batch continuation uses Resume.
4. Add a manual “Collect next 10” label after batch limit if product language prefers it over Start Collecting.

## Recommended next changes

### P0 must fix before full collection

- None found in the audited protected Start Collecting/Pause/Resume path.

### P1 should fix soon

- Add UI copy for `batch_safe_mode_completed` with pending items: “Batch complete. Click Start Collecting to collect the next 10.”
- Add a focused view-model/readiness test proving idle batch completion maps to Start Collecting, not Resume.
- Add a controller test for Resume with stale/wrong-profile local session to prove Phase 3E replacement is exercised during Resume.
- Add a documented/tested expectation for Pause after backend commit has already started.

### P2 nice to have

- Rename or supplement diagnostics so `resume_from_index` does not imply Resume is the continuation action after a non-paused batch limit.
- Tighten footer pause/resume visibility around actual paused/running states.
- Add richer stale ownerless recovery copy with a “why Resume is disabled” diagnostic.

## Suggested focused implementation plan

Do not implement in this audit phase. Suggested follow-up plan:

1. Add tests first.
   - Readiness/view-model test for `batch_safe_mode_completed` + pending queue => Start Collecting enabled, Resume not visible/enabled.
   - Controller test for Resume with wrong-profile stale local session => fresh verified session is created.
   - Popup source/view test for the new batch-complete continuation copy.
2. Add copy-only UI change.
   - Surface “Batch complete; click Start Collecting for next 10” when `phase === "batch_safe_mode_completed"` and pending remains.
3. Add diagnostics clarification.
   - Keep existing `resume_from_index` for compatibility but add `next_pending_index`/`next_batch_start_index` in response summary if needed.
4. Re-run focused checks.
   - Typecheck, popup workflow test, view-model/readiness tests, whole-profile harvest test, backend client test, build.
5. Manually validate on the known healthy profile.
   - Scan Profile still reaches full queue count.
   - First safe batch saves 10.
   - UI instructs Start Collecting for the next 10.
   - Second safe batch saves the next 10 using the same verified session.

## Suggested tests to add

- `batch_safe_mode_completed` readiness test:
  - Given queued/calibrated state, 10 saved, pending remains, collection idle.
  - Assert primary action is Start Collecting.
  - Assert Resume is not visible/enabled.
- Popup/view-model copy test:
  - Given `phase: "batch_safe_mode_completed"` and pending count > 0.
  - Assert status/help text says Start Collecting collects the next 10.
- Resume stale-session replacement test:
  - Paused state has stale/wrong-profile `capture_session_id`.
  - Resume creates fresh session and saves payload with fresh session.
  - Queue/calibration preserved.
- Pause in-flight save behavior test:
  - Pause requested after backend flush begins.
  - Assert expected behavior is documented: current save may finish, then next checkpoint pauses.
- Extension reload lifecycle test:
  - Simulate ownerless running collection recovery and assert Resume disabled, queue/calibration preserved, operator copy requires reload/rescan.

## Manual validation checklist

1. Open a healthy Douyin profile.
2. Run Scan Profile.
   - Confirm queue count and completion ratio remain correct.
3. Confirm calibration is present and valid.
4. Click Start Collecting.
5. After first safe batch completes:
   - Confirm `saved_count` increased by 10.
   - Confirm `failed_count` and `skipped_count` remain expected.
   - Confirm `pending_count` decreased by 10.
   - Confirm phase is `batch_safe_mode_completed`.
   - Confirm status is idle.
6. Confirm UI continuation is Start Collecting, not Resume.
7. Click Start Collecting again.
   - Confirm next 10 pending videos are selected, not the first 10 again.
   - Confirm backend session is reused only after profile verification.
8. During a later batch, click Pause.
   - Confirm UI moves to Pausing.
   - Confirm current item finishes or safe checkpoint is reached.
   - Confirm state becomes Paused with Resume available.
9. Click Resume.
   - Confirm safe Next 10 runner resumes from the next pending target.
   - Confirm legacy runner is not invoked.
10. Reload the extension during an active run only in a controlled test.
   - Confirm stale ownerless recovery preserves queue/calibration and instructs reload/rescan instead of unsafe Resume.

## Audit conclusion

The existing Pause/Resume behavior is logically correct and safe enough for continuing after a 10-item safe batch, with one important operator distinction: continuing after a normal batch limit uses Start Collecting, while Resume is only for actual paused/interrupted runs. The next phase should focus on UI clarity and focused tests, not broad scanner or backend refactoring.
