import assert from "node:assert/strict";
import {
  formatOffsetLoadMoreLabel,
  formatOffsetLoadedLabel,
  hasMoreOffsetItems,
  mergeOffsetItemsById,
  nextOffsetPageSize,
} from "../lib/offsetListPagination";

assert.equal(hasMoreOffsetItems(50, 120), true);
assert.equal(hasMoreOffsetItems(120, 120), false);
assert.equal(nextOffsetPageSize(50, 100, 120), 20);
assert.equal(formatOffsetLoadedLabel(50, 120, "jobs"), "Loaded 50 of 120 jobs.");
assert.equal(formatOffsetLoadedLabel(120, 120, "jobs"), "All 120 jobs loaded.");
assert.match(formatOffsetLoadMoreLabel(50, 100, 120), /Load more \(20\)/);
assert.match(formatOffsetLoadMoreLabel(50, 100, 120, true), /Loading more/);

const merged = mergeOffsetItemsById(
  [{ id: "a" }, { id: "b" }],
  [{ id: "b" }, { id: "c" }]
);
assert.deepEqual(
  merged.map((item) => item.id),
  ["a", "b", "c"]
);

console.log("offsetListPagination.test.ts: ok");
