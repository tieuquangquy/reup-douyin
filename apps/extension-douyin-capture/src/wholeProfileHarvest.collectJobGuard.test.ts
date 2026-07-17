import assert from "node:assert/strict";

import { readWholeProfileHarvestState, writeWholeProfileHarvestState } from "./wholeProfileHarvest/controller.js";
import { WHOLE_PROFILE_HARVEST_STATE_KEY, createWholeProfileHarvestIdleState, type WholeProfileHarvestState } from "./wholeProfileHarvest/state.js";

// Minimal in-memory chrome.storage.local double used by the controller state
// read/write primitives. Mirrors the MemoryStorage helper used elsewhere.
class MemoryStorage {
  values: Record<string, unknown> = {};

  async get(key: string): Promise<Record<string, unknown>> {
    return { [key]: this.values[key] };
  }

  async set(items: Record<string, unknown>): Promise<void> {
    Object.assign(this.values, items);
  }
}

// === Stale-write rejection guard (collect-job freeze root cause) ===
// writeWholeProfileHarvestState is the single persistence chokepoint. The popup
// and service worker hold independent in-memory snapshots, so a slow writer that
// captured the state while a collect job was still "starting" (lower
// runtime_generation) can otherwise blindly clobber a newer completion write for
// the same job_id — a lost-update race. That is exactly what froze the
// "Collecting videos" UI on the pre-skip path (all queued videos already
// collected): the persisted collect_job.state reverted to "starting" with the
// hybrid completion escape hatch stripped, so deriveAuthoritativeRunnerLock kept
// the runner lock active forever. The guard enforces monotonic runtime_generation
// and forbids reverting a terminal collect job back to an active state.

// 1. A completed collect job is persisted (runtime_generation = 5).
const storage = new MemoryStorage();
const base = createWholeProfileHarvestIdleState("2026-07-03T01:00:00.000Z");
const completedState: WholeProfileHarvestState = {
  ...base,
  status: "completed",
  phase: "completed",
  collect_job: { ...base.collect_job, job_id: "collect_guard_job_1", state: "completed", lock_released: true, lock_owner: null, lock_expires_at: null, runtime_generation: 5 },
  active_collect_runtime: { ...base.active_collect_runtime, job_id: "collect_guard_job_1", runtime_generation: 5, canonical_state: "idle" },
  workflow: { ...base.workflow, collection: { ...base.workflow.collection, status: "idle", updated_at: "2026-07-03T01:00:05.000Z", completed_at: "2026-07-03T01:00:05.000Z" }, active_task: null, action_lock: null },
  debug: { ...base.debug, last_response_summary: { hybrid_collector_completed: "yes" } },
  updated_at: "2026-07-03T01:00:05.000Z"
};
await writeWholeProfileHarvestState(storage, completedState);

// 2. A stale pre-completion snapshot (collect_job="starting", lower generation)
//    tries to write back. It MUST be rejected, not clobber the completion.
const staleSnapshot: WholeProfileHarvestState = {
  ...base,
  status: "harvesting",
  phase: "session_verified",
  collect_job: { ...base.collect_job, job_id: "collect_guard_job_1", state: "starting", lock_released: false, runtime_generation: 3 },
  active_collect_runtime: { ...base.active_collect_runtime, job_id: "collect_guard_job_1", runtime_generation: 3, canonical_state: "starting" },
  workflow: { ...base.workflow, collection: { ...base.workflow.collection, status: "idle" } },
  debug: { ...base.debug, last_response_summary: {} },
  updated_at: "2026-07-03T01:00:10.000Z"
};
const afterStaleWrite = await writeWholeProfileHarvestState(storage, staleSnapshot);
assert.equal(afterStaleWrite.collect_job.state, "completed", "stale starting snapshot must not revert a completed collect job");
assert.equal(afterStaleWrite.collect_job.runtime_generation, 5, "stale write must not roll collect_job.runtime_generation backwards");
assert.equal(
  afterStaleWrite.debug.last_request_summary && (afterStaleWrite.debug.last_request_summary as Record<string, unknown>).trace_stale_state_write_rejected,
  "yes",
  "stale write rejection must leave an observable breadcrumb"
);

const afterStaleRead = await readWholeProfileHarvestState(storage, "2026-07-03T01:00:11.000Z");
assert.equal(afterStaleRead.collect_job.state, "completed", "persisted state must stay completed after a rejected stale write");
assert.equal(afterStaleRead.collect_job.runtime_generation, 5, "persisted collect_job.runtime_generation must stay at the completion value after a rejected stale write");

// 3. A legitimate restart reuses the same job_id but bumps
//    collect_job.runtime_generation strictly higher via startPersistentCollectJob,
//    so it MUST be accepted — even though completion cleanup reset the ACTIVE
//    runtime generation back to 1. This is the feedback #2 "subsequent runs don't
//    run" regression coverage at the guard level.
const restart: WholeProfileHarvestState = {
  ...staleSnapshot,
  collect_job: { ...staleSnapshot.collect_job, runtime_generation: 6 },
  active_collect_runtime: { ...staleSnapshot.active_collect_runtime, runtime_generation: 1, canonical_state: "starting" },
  updated_at: "2026-07-03T01:00:20.000Z"
};
const afterRestartWrite = await writeWholeProfileHarvestState(storage, restart);
assert.equal(afterRestartWrite.collect_job.state, "starting", "a higher collect_job-generation restart of the same job_id must be accepted (not rejected as stale)");
assert.equal(afterRestartWrite.collect_job.runtime_generation, 6, "restart write must advance collect_job.runtime_generation");

// 4. A reset produces a null/idle job (not a terminal->active revert) and MUST
//    always pass regardless of the previously completed job.
const idleWrite = await writeWholeProfileHarvestState(storage, createWholeProfileHarvestIdleState("2026-07-03T01:00:30.000Z"));
assert.equal(idleWrite.collect_job.job_id, null, "idle/reset write with a null job must never be blocked by the stale-write guard");

// 5. A different job_id is a fresh run and must never be blocked by a prior
//    job's terminal state (guard only applies to the SAME job_id).
const differentJobStorage = new MemoryStorage();
await differentJobStorage.set({ [WHOLE_PROFILE_HARVEST_STATE_KEY]: (await writeWholeProfileHarvestState(new MemoryStorage(), completedState)) });
const differentJob: WholeProfileHarvestState = {
  ...staleSnapshot,
  collect_job: { ...staleSnapshot.collect_job, job_id: "collect_guard_job_2", state: "starting", runtime_generation: 1 },
  active_collect_runtime: { ...staleSnapshot.active_collect_runtime, job_id: "collect_guard_job_2", runtime_generation: 1, canonical_state: "starting" },
  updated_at: "2026-07-03T01:00:40.000Z"
};
await writeWholeProfileHarvestState(storage, completedState);
const afterDifferentJob = await writeWholeProfileHarvestState(storage, differentJob);
assert.equal(afterDifferentJob.collect_job.state, "starting", "a different job_id must not be blocked by a prior job's terminal state");
assert.equal(afterDifferentJob.collect_job.job_id, "collect_guard_job_2", "a different job_id write must land");

console.log("collect-job stale-write rejection guard tests passed");
