import assert from "node:assert/strict";

import { readWholeProfileHarvestState, writeWholeProfileHarvestState } from "./wholeProfileHarvest/controller.js";
import { createWholeProfileHarvestIdleState, type WholeProfileHarvestState } from "./wholeProfileHarvest/state.js";

// === Post-completion stale-write rejection (freeze protection) ===
//
// History: a realm-wide write-serialization mutex was added on a TOCTOU theory
// (a slow popup probe-sync write clobbering the runner's completion write). The
// mutex was removed because a single non-settling write in the shared chain
// could wedge EVERY later write in the realm — including the runner's ACK write
// on a re-click — which is a worse and more likely failure than the unproven
// race it defended against.
//
// The durable, order-independent guarantee now lives entirely at the write
// chokepoint (writeWholeProfileHarvestState): once a collect job has been
// persisted as completed, any later write that would revert the SAME job_id back
// to an active state WITHOUT a strictly higher collect_job.runtime_generation is
// rejected. This test asserts that guarantee directly with sequential writes (no
// dependence on mutex timing), which is the realistic ordering: the runner's
// completion lands, then a stale probe-sync snapshot tries to write "running".

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

const base = createWholeProfileHarvestIdleState("2026-07-03T02:00:00.000Z");
const JOB_ID = "serialize_job_1";

// Store starts with the collect job in the ACK "running" phase. Both writes below
// belong to the SAME run, so they carry the SAME collect_job.runtime_generation.
const ackRunning: WholeProfileHarvestState = {
  ...base,
  status: "harvesting",
  phase: "session_verified",
  collect_job: { ...base.collect_job, job_id: JOB_ID, state: "running", lock_released: false, lock_owner: JOB_ID, runtime_generation: 2 },
  active_collect_runtime: { ...base.active_collect_runtime, job_id: JOB_ID, runtime_generation: 2, canonical_state: "running" },
  workflow: { ...base.workflow, collection: { ...base.workflow.collection, status: "idle" } },
  debug: { ...base.debug, last_response_summary: { hybrid_runner_outcome: "hybrid_runner_acknowledged_proceeding" } },
  updated_at: "2026-07-03T02:00:02.000Z"
};

const storage = new MemoryStorage();
storage.values["douyinWholeProfileHarvestState"] = ackRunning;

// The runner completion write lands first: terminal completed, escape hatch set.
// Same collect_job.runtime_generation as the run (2) — completion does not bump it.
const completed: WholeProfileHarvestState = {
  ...ackRunning,
  status: "completed",
  phase: "completed",
  collect_job: { ...ackRunning.collect_job, state: "completed", lock_released: true, lock_owner: null, lock_expires_at: null, completed_at: "2026-07-03T02:00:05.000Z" },
  active_collect_runtime: { ...ackRunning.active_collect_runtime, runtime_generation: 4, canonical_state: "idle" },
  workflow: { ...ackRunning.workflow, collection: { ...ackRunning.workflow.collection, status: "idle", completed_at: "2026-07-03T02:00:05.000Z" }, active_task: null, action_lock: null },
  debug: { ...ackRunning.debug, last_response_summary: { hybrid_collector_completed: "yes", hybrid_runner_outcome: "phase_4_4d_loop_completed" } },
  updated_at: "2026-07-03T02:00:05.000Z"
};
await writeWholeProfileHarvestState(storage, completed);

// The stale probe-sync write: captured the ACK "running" snapshot BEFORE
// completion (same collect_job generation), rebuilt last_response_summary WITHOUT
// hybrid_collector_completed, and now tries to write it back AFTER completion has
// already landed. The chokepoint guard MUST reject it (terminal->active revert,
// no higher generation).
const staleProbeSync: WholeProfileHarvestState = {
  ...ackRunning,
  debug: { ...ackRunning.debug, last_request_summary: { diagnostics_write_source: "popup.live_network_probe_sync" }, last_response_summary: { diagnostics_write_source: "popup.live_network_probe_sync" } },
  updated_at: "2026-07-03T02:00:06.000Z"
};
const afterStale = await writeWholeProfileHarvestState(storage, staleProbeSync);

assert.equal(
  afterStale.collect_job.state,
  "completed",
  "a stale 'running' probe-sync write arriving after completion must be rejected (collect job stays completed)"
);

const finalState = await readWholeProfileHarvestState(storage, "2026-07-03T02:00:10.000Z");
assert.equal(
  finalState.collect_job.state,
  "completed",
  "persisted collect job must stay completed after the rejected stale write"
);
assert.equal(
  (finalState.debug.last_response_summary as Record<string, unknown> | undefined)?.hybrid_collector_completed,
  "yes",
  "hybrid_collector_completed escape hatch must survive the rejected stale write"
);

console.log("post-completion stale-write rejection tests passed");
