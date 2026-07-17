import assert from "node:assert/strict";

import { resolveHybridCollectBatchLimits } from "./wholeProfileHarvest/hybridCollectBatchLimits.js";

assert.deepEqual(
  resolveHybridCollectBatchLimits(0, 3),
  { writeBatchLimit: 3, preSkipScanLimit: 3 },
  "empty visible queue with 3 backend gap must keep positive batch limits"
);

assert.deepEqual(
  resolveHybridCollectBatchLimits(500, 3),
  { writeBatchLimit: 3, preSkipScanLimit: 3 },
  "large visible queue still caps to backend gap"
);

assert.deepEqual(
  resolveHybridCollectBatchLimits(0, 0),
  { writeBatchLimit: 0, preSkipScanLimit: 0 },
  "zero gap yields zero limits"
);

console.info("hybridTailGapRecovery.test.ts: all assertions passed");
