import assert from "node:assert/strict";

import {
  resolveTailGapDomScrollPolicy,
  runtimeSupportsHybridTailGapDiscovery,
  TAIL_GAP_DOM_SCROLL_MAX_DURATION_MS,
  TAIL_GAP_DOM_SCROLL_MAX_ROUNDS
} from "./wholeProfileHarvest/hybridTailGapTabRuntime.js";

assert.equal(runtimeSupportsHybridTailGapDiscovery({}), false);
assert.equal(runtimeSupportsHybridTailGapDiscovery({
  fetchProfilePostPageFromTab: async () => ({ ok: true, verified_target_details: [], has_more: false, next_cursor: null, stop_reason: "ok" })
}), false);
assert.equal(runtimeSupportsHybridTailGapDiscovery({
  fetchProfilePostPageFromTab: async () => ({ ok: true, verified_target_details: [], has_more: false, next_cursor: null, stop_reason: "ok" }),
  readDomTailReconcileProbeFromTab: async () => ({})
}), true);

{
  const policy = resolveTailGapDomScrollPolicy({ forceDomScroll: true, quickProbeIdCount: 40 });
  assert.equal(policy.shouldScroll, false, "tail-gap must not force full-grid scroll when quick probe already has IDs");
  assert.equal(policy.maxRounds, TAIL_GAP_DOM_SCROLL_MAX_ROUNDS);
  assert.ok(TAIL_GAP_DOM_SCROLL_MAX_ROUNDS <= 8, "capped scroll must stay far below full scan 80 rounds");
  assert.ok(TAIL_GAP_DOM_SCROLL_MAX_DURATION_MS <= 20_000, "capped scroll must stay far below full scan 120s");
}

{
  const policy = resolveTailGapDomScrollPolicy({ forceDomScroll: false, quickProbeIdCount: 0 });
  assert.equal(policy.shouldScroll, false, "default tail-gap path skips DOM scroll entirely");
}

{
  const policy = resolveTailGapDomScrollPolicy({ allowCappedDomScroll: true, quickProbeIdCount: 0 });
  assert.equal(policy.shouldScroll, true, "capped scroll only when explicitly allowed and quick probe empty");
  assert.equal(policy.maxRounds, TAIL_GAP_DOM_SCROLL_MAX_ROUNDS);
}

console.info("hybridTailGapTabRuntime.test.ts: all assertions passed");
