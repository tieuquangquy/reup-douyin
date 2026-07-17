import assert from "node:assert/strict";

import {
  buildHybridRunnerFossilPreflightBlockedPatch,
  isChromeStorageWriteQuotaError,
  mergeHybridRunnerFossil,
  readHybridFossilMemoryBuffer,
  resetHybridFossilDiagnosticBuffer
} from "./wholeProfileHarvest/hybridDiagnosticStorage.js";

assert.equal(isChromeStorageWriteQuotaError(new Error("This request exceeds the MAX_WRITE_OPERATIONS_PER_HOUR quota.")), true);

resetHybridFossilDiagnosticBuffer();
await mergeHybridRunnerFossil({ hybrid_runner_probe_step: "step_2a_targets_selected", hybrid_runner_pre_skip_total: 10 });
assert.equal(readHybridFossilMemoryBuffer().hybrid_runner_probe_step, "step_2a_targets_selected");
assert.equal(readHybridFossilMemoryBuffer().hybrid_runner_pre_skip_total, 10);

resetHybridFossilDiagnosticBuffer();
await mergeHybridRunnerFossil({
  hybrid_runner_loop_phase: "loop_completed",
  hybrid_runner_write_ok_count: 71,
  hybrid_runner_per_item_count: 236,
  hybrid_runner_outcome: "phase_4_4d_loop_partial"
}, { force: true });
await mergeHybridRunnerFossil(buildHybridRunnerFossilPreflightBlockedPatch("Calibrate 4 Points first."), { force: true });
const blockedFossil = readHybridFossilMemoryBuffer();
assert.equal(blockedFossil.hybrid_runner_entry_hit, "blocked_before_dispatch");
assert.equal(blockedFossil.hybrid_runner_error, "Calibrate 4 Points first.");
assert.equal(blockedFossil.hybrid_runner_loop_phase, null, "preflight block must clear stale loop phase from prior run");
assert.equal(blockedFossil.hybrid_runner_write_ok_count, null, "preflight block must clear stale write counts from prior run");
assert.equal(blockedFossil.hybrid_runner_per_item_count, null, "preflight block must clear stale per-item summary counts");

console.log("wholeProfileHarvest.hybridDiagnosticStorage.test.ts: PASS");
