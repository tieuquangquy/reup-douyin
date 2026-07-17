import assert from "node:assert/strict";

import {
  capOrderedQueueToDisplayedProfileLimit,
  filterQueueToDisplayedProfileCollectScope,
  resolveDisplayedProfileVideoLimit,
  resolveOverDisplayedExtraAwemeIds
} from "./wholeProfileHarvest/displayedProfileQueueCap.js";

function makeQueue(count: number): Array<{ aweme_id: string; index: number }> {
  return Array.from({ length: count }, (_, index) => ({
    aweme_id: `aweme-${index}`,
    index: index + 1
  }));
}

assert.equal(resolveDisplayedProfileVideoLimit({ displayed_profile_count: 3303 }), 3303);
assert.equal(resolveDisplayedProfileVideoLimit({ expected_profile_video_count: 500 }), 500);

{
  const queue = makeQueue(3381);
  const extraIds = new Set(queue.slice(3303).map((item) => item.aweme_id));
  const capped = capOrderedQueueToDisplayedProfileLimit(queue, 3303, extraIds);
  assert.equal(capped.queue.length, 3303);
  assert.equal(capped.excludedCount, 78);
  assert.equal(capped.capped, true);
  assert.equal(capped.queue[0]?.aweme_id, "aweme-0");
  assert.equal(capped.queue[3302]?.aweme_id, "aweme-3302");
}

{
  const queue = makeQueue(3381);
  const capped = capOrderedQueueToDisplayedProfileLimit(queue, 3303);
  assert.equal(capped.queue.length, 3303);
  assert.equal(capped.excludedCount, 78);
}

{
  const queue = makeQueue(3381);
  const exactExtras = queue.slice(3303).map((item) => item.aweme_id);
  const filtered = filterQueueToDisplayedProfileCollectScope(queue, {
    displayed_profile_count: 3303,
    over_displayed_extra_ids_exact: exactExtras,
    over_displayed_count: 78
  });
  assert.equal(filtered.length, 3303);
  assert.ok(!filtered.some((item) => exactExtras.includes(item.aweme_id)));
}

{
  const queue = makeQueue(2000);
  const capped = capOrderedQueueToDisplayedProfileLimit(queue, 3303);
  assert.equal(capped.queue.length, 2000);
  assert.equal(capped.capped, false);
}

assert.deepEqual(
  resolveOverDisplayedExtraAwemeIds({
    over_displayed_extra_ids_exact: ["a", "b"],
    over_displayed_count: 2
  }),
  ["a", "b"]
);

console.info("displayedProfileQueueCap.test.ts: PASS");
