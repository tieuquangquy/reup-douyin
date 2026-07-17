# Phase 22A-0 — Scanner recovery fixes

Date: 2026-05-08

## Scope

Phase 22A-0 fixes three operator-facing scanner recovery issues in the Douyin capture extension:

1. Reset must be a hard scanner reset, not a partial idle rewrite.
2. Start Collecting must fail explicitly when the collector runner/content script is not connected, instead of appearing to no-op or leaving a stuck running state.
3. Calibration sync must be idempotent so the stored updated timestamp does not churn continuously.

The phase also prevents contradictory scanner UI states where stale collection state could show a Collecting header while the primary action was Start Collecting.

## Non-goals

- No crawler implementation.
- No new queue/backend/database behavior.
- No changes to Douyin extraction strategy.
- No auto-publishing behavior.
- No root API test repair; root smoke test currently has unrelated API failures documented below.

## Implementation summary

### Calibration idempotency

Calibration sync now compares stable fingerprints before writing canonical and bridge calibration storage. Identical canonical calibration does not rewrite storage, which prevents continuous updated timestamp churn.

Regression coverage: `apps/extension-douyin-capture/src/wholeProfileHarvest.calibration.test.ts` verifies that unchanged canonical calibration produces no storage write.

### Hard reset

`resetHarvest()` now recreates a clean idle scanner state while preserving operator recovery context:

- calibration
- profile URL/source URL/modal source linkage
- page context
- harvest options
- tab health diagnostics
- resume-check diagnostics

It explicitly clears transient/stuck execution state:

- run id
- capture session id
- scan/classification/collection workflow state
- active task/action lock
- queue/results/current target
- backend capture session/payload/flush state
- pause diagnostics
- collect trace
- transient last error

It also records preserved and cleared state summaries in debug diagnostics.

Regression coverage: `apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts` verifies reset clears stuck collection/save/session state while preserving calibration/settings/context.

### Start Collecting runner preflight

`runStartCollectingWorkflow()` now verifies the active tab and content-script readiness before entering modal extraction. If the collector runner is not available, it records a stable failure:

`Collector runner is not connected yet.`

The failure path clears `workflow.active_task` and `workflow.action_lock`, marks collection failed, and does not open modals or append collection trace entries.

Regression coverage: `apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts` includes a runner-disconnected Start Collecting case.

### Contradictory UI prevention and Pause wiring

Scanner readiness now treats collection as actively collecting only when canonical collection is running and the scanner busy state is non-stale. Scanner view-model headers and progress labels now derive from live busy/readiness state instead of raw stale collection status.

This prevents stale collection state from rendering a Collecting header while the primary action is Start Collecting.

Pause wiring was already present in popup primary action dispatch: scanner primary action `pause` routes to the stop/pause controller path. This phase preserves that wiring and adds regression coverage around non-stale vs stale collection UI behavior.

Regression coverage: `apps/extension-douyin-capture/src/wholeProfileHarvest.viewModel.test.ts` verifies stale workflow collection does not expose Pause, does not show Collecting headers, and keeps Start Collecting as the primary label.

### Advanced diagnostics

Advanced details now surface scanner recovery diagnostics:

- scanner busy state
- scanner next action
- active task
- action lock
- last scanner action
- last scanner result
- last scanner error

Regression coverage: `apps/extension-douyin-capture/src/wholeProfileHarvest.viewModel.test.ts` verifies these rows exist.

## Validation

Focused Phase 22A-0 extension tests passed:

```powershell
cd apps/extension-douyin-capture
npx tsx src/wholeProfileHarvest.calibration.test.ts && npx tsx src/wholeProfileHarvest.test.ts && npx tsx src/wholeProfileHarvest.readiness.test.ts && npx tsx src/wholeProfileHarvest.viewModel.test.ts
```

Output:

```text
whole profile calibration bridge tests passed
Phase 18I-E whole-profile safety scheduler and captcha pause tests passed
wholeProfileHarvest readiness/action gating tests passed
wholeProfileHarvest stepper/summary view-model tests passed
```

A previous root `npm test -- --runInBand apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts` invocation failed because the root smoke script ran unrelated API tests. Known unrelated failures included `test_post_valid_request_returns_collect_aweme_ids`, `test_post_valid_request_returns_counts`, and `test_post_valid_request_returns_result_schema_version` in API profile video classification coverage. Those API failures were not changed in Phase 22A-0.

## Operator outcome

After Phase 22A-0:

- Reset clears stuck Collecting state and returns the scanner to Scan Profile while keeping calibration/settings.
- Start Collecting fails visibly if the runner is not connected.
- Calibration updated timestamps do not churn when calibration has not changed.
- Stale collection state does not render contradictory Collecting/Start Collecting UI.
- Advanced details expose enough recovery diagnostics to inspect scanner locks and the last scanner action result.
