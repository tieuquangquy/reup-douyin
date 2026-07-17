import assert from "node:assert/strict";
import {
  canOpenCompare,
  clampFocusIndex,
  focusIndexAfterRemove,
  removeStars,
  stepFocusIndex,
  toggleCompareStar
} from "../lib/reviewBoardDecisionState";

assert.equal(stepFocusIndex(0, 5, 1), 1);
assert.equal(clampFocusIndex(9, 3), 2);
assert.equal(focusIndexAfterRemove(2, 3), 1);

let starred = toggleCompareStar([], "a");
starred = toggleCompareStar(starred, "b");
assert.deepEqual(starred, ["a", "b"]);
assert.equal(canOpenCompare(starred), true);
starred = toggleCompareStar(starred, "a");
assert.deepEqual(starred, ["b"]);
assert.equal(canOpenCompare(starred), false);
assert.deepEqual(removeStars(["a", "b", "c"], ["b"]), ["a", "c"]);

console.log("review-board-decision tests passed");
