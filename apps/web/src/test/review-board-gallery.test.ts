import assert from "node:assert/strict";
import { createEmptyBench } from "../lib/reviewBoardBenchState";
import {
  benchSlotIndexForCandidate,
  canOpenCompareMode,
  clampGalleryIndex,
  galleryIndexAfterRemove,
  pinCandidateToBench,
  stepGalleryIndex
} from "../lib/reviewBoardGalleryState";

assert.equal(stepGalleryIndex(0, 5, 1), 1);
assert.equal(stepGalleryIndex(4, 5, 1), 4);
assert.equal(stepGalleryIndex(0, 5, -1), 0);
assert.equal(clampGalleryIndex(9, 3), 2);
assert.equal(galleryIndexAfterRemove(3, 4), 2);
assert.equal(galleryIndexAfterRemove(0, 1), 0);

let bench = createEmptyBench();
bench = pinCandidateToBench(bench, "a", 0);
bench = pinCandidateToBench(bench, "b", 2);
assert.deepEqual(bench, ["a", null, "b"]);
assert.equal(benchSlotIndexForCandidate(bench, "b"), 2);
bench = pinCandidateToBench(bench, "a", 1);
assert.deepEqual(bench, ["a", null, "b"]);
assert.equal(canOpenCompareMode(2), true);
assert.equal(canOpenCompareMode(1), false);

console.log("review-board-gallery tests passed");
