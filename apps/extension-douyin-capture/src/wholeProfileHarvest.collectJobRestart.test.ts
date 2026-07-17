import assert from "node:assert/strict";

import { readWholeProfileHarvestState, writeWholeProfileHarvestState } from "./wholeProfileHarvest/controller.js";
import { createWholeProfileHarvestIdleState, type WholeProfileHarvestState } from "./wholeProfileHarvest/state.js";

// === Collect-job RESTART acceptance (feedback #2 regression root cause) ===
// Symptom reported by the operator: "I press Collecting videos the 1st time and
// it runs, but subsequent times it does NOT run."
//
// Root cause: the stale-write rejection guard keyed its monotonic comparison off
// active_collect_runtime.runtime_generation. That value is UNRELIABLE across
// restarts because finalizeHybridCollectionCleanup nulls
// active_collect_runtime.job_id on completion, so the next
// syncActiveCollectRuntimeFromJob resets the active generation back to 1 (the
// "previousRuntime.job_id !== collect_job.job_id" branch). Run 2 therefore
// carried active generation 1, which is LOWER than run 1's finalized active
// generation, so the guard mistook the legitimate restart for a stale snapshot
// and REJECTED run 2's "starting" write. The runner then read a still-terminal
// collect job and its idempotency guard skipped the invocation — the exact log
// signature: hybrid_runner_entry_hit=pending_before_dispatch, invocation_seq=2,
// all probe fields pending.
//
// Fix: key the guard off collect_job.runtime_generation, which
// startPersistentCollectJob sets to (previous active + 1) — strictly higher than
// the finished run — and which stays CONSTANT within a run. That is the only
// signal that both (a) increases across restarts and (b) survives cleanup.
//
// This test models a completed run 1 in the store (nulled active runtime, high
// active generation, LOW collect_job generation) and a run 2 "starting" write
// (same job_id, HIGHER collect_job generation, active state). The restart MUST
// be accepted, not rejected.

class MemoryStorage {
  values: Record<string, unknown> = {};

  async get(key: string): Promise<Record<string, unknown>> {
    await Promise.resolve();
    return { [key]: this.values[key] };
  }

  async set(items: Record<string, unknown>): Promise<void> {
    await Promise.resolve();
    Object.assign(this.values, items);
  }
}

const base = createWholeProfileHarvestIdleState("2026-07-03T03:00:00.000Z");
const JOB_ID = "restart_job_1";

// Store = run 1 finished. finalizeHybridCollectionCleanup nulled the active
// runtime job_id and bumped the ACTIVE generation high (7), while the collect_job
// keeps run 1's OWN generation (3, lower than the active counter) and stays
// terminal + lock_released.
const run1Completed: WholeProfileHarvestState = {
  ...base,
  status: "completed",
  phase: "completed",
  collect_job: {
    ...base.collect_job,
    job_id: JOB_ID,
    state: "completed",
    lock_released: true,
    lock_owner: null,
    lock_expires_at: null,
    runtime_generation: 3,
    completed_at: "2026-07-03T03:00:05.000Z"
  },
  active_collect_runtime: {
    ...base.active_collect_runtime,
    job_id: null,
    runtime_generation: 7,
    canonical_state: "idle"
  },
  workflow: { ...base.workflow, collection: { ...base.workflow.collection, status: "idle" } },
  debug: { ...base.debug, last_response_summary: { hybrid_collector_completed: "yes" } },
  updated_at: "2026-07-03T03:00:05.000Z"
};

const storage = new MemoryStorage();
storage.values["douyinWholeProfileHarvestState"] = run1Completed;

// Run 2 "starting" write from startPersistentCollectJob. Same job_id (run_id is
// reused), state back to active "starting", lock re-acquired, and
// collect_job.runtime_generation bumped to previous_active + 1 = 8 (strictly
// higher than run 1's collect_job generation of 3). The active runtime generation
// is reset to 1 here — exactly the misleading value that used to trip the guard.
const run2Starting: WholeProfileHarvestState = {
  ...run1Completed,
  status: "harvesting",
  phase: "session_verified",
  collect_job: {
    ...run1Completed.collect_job,
    state: "starting",
    lock_released: false,
    lock_owner: JOB_ID,
    completed_at: null,
    runtime_generation: 8
  },
  active_collect_runtime: {
    ...run1Completed.active_collect_runtime,
    job_id: JOB_ID,
    runtime_generation: 1,
    canonical_state: "starting"
  },
  debug: { ...run1Completed.debug, last_response_summary: { hybrid_runner_entry_hit: "pending_before_dispatch" } },
  updated_at: "2026-07-03T03:00:10.000Z"
};

const afterRestart = await writeWholeProfileHarvestState(storage, run2Starting);
assert.equal(
  afterRestart.collect_job.state,
  "starting",
  "a legitimate run-2 restart (same job_id, higher collect_job generation) MUST be accepted, not rejected as a stale terminal->active revert"
);
assert.equal(
  afterRestart.collect_job.runtime_generation,
  8,
  "the restart's collect_job.runtime_generation must be persisted"
);

const persisted = await readWholeProfileHarvestState(storage, "2026-07-03T03:00:11.000Z");
assert.equal(
  persisted.collect_job.state,
  "starting",
  "the persisted store must reflect the accepted restart so the runner reads an active job and does NOT hit the idempotency skip"
);
assert.equal(
  persisted.collect_job.lock_released,
  false,
  "the restart must re-acquire the lock (lock_released=false) so the runner proceeds"
);

// Guard negative case: a genuinely stale write for run 1 (its OLD lower collect_job
// generation) arriving AFTER run 2 started must still be rejected so it cannot
// clobber the fresh run.
const staleRun1Snapshot: WholeProfileHarvestState = {
  ...run1Completed,
  status: "harvesting",
  collect_job: {
    ...run1Completed.collect_job,
    state: "running",
    lock_released: false,
    runtime_generation: 3
  },
  updated_at: "2026-07-03T03:00:12.000Z"
};

const afterStale = await writeWholeProfileHarvestState(storage, staleRun1Snapshot);
assert.equal(
  afterStale.collect_job.runtime_generation,
  8,
  "a stale run-1 snapshot (lower collect_job generation) must be rejected and must not roll the generation back"
);
assert.equal(
  afterStale.collect_job.state,
  "starting",
  "the stale lower-generation write must not overwrite the active run-2 state"
);

console.log("collect-job restart acceptance tests passed");
