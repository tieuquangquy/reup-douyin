import assert from "node:assert/strict";
import {
  applyMarqueeSelection,
  autoScrollVelocity,
  dragDistance,
  intersectingSelectionIds,
  normalizeSelectionRect,
  selectSelectionRange
} from "../lib/reupQueueDragSelection";

const rect = normalizeSelectionRect({ x: 180, y: 240 }, { x: 40, y: 80 });
assert.deepEqual(rect, { bottom: 240, left: 40, right: 180, top: 80 });
assert.equal(dragDistance({ x: 10, y: 10 }, { x: 13, y: 14 }), 5);

const hits = intersectingSelectionIds(rect, [
  { id: "before", rect: { bottom: 60, left: 40, right: 180, top: 20 } },
  { id: "first", rect: { bottom: 110, left: 20, right: 220, top: 70 } },
  { id: "second", rect: { bottom: 220, left: 20, right: 220, top: 180 } },
  { id: "hidden", rect: { bottom: 0, left: 0, right: 0, top: 0 } }
]);
assert.deepEqual(hits, ["first", "second"], "Marquee must select visible rows intersecting its rectangle");

assert.deepEqual(
  [...applyMarqueeSelection(new Set(["old"]), ["first", "second"], "replace")],
  ["first", "second"],
  "Plain drag replaces the previous selection"
);
assert.deepEqual(
  [...applyMarqueeSelection(new Set(["old", "first"]), ["first", "second"], "toggle")],
  ["old", "second"],
  "Ctrl-drag toggles hits against the selection captured at drag start"
);

const orderedIds = ["a", "b", "c", "d", "e"];
assert.deepEqual(
  [...selectSelectionRange(new Set(["outside"]), orderedIds, "b", "d", false)],
  ["b", "c", "d"],
  "Shift range replaces selection when Ctrl is not held"
);
assert.deepEqual(
  [...selectSelectionRange(new Set(["outside"]), orderedIds, "d", "b", true)],
  ["outside", "b", "c", "d"],
  "Ctrl+Shift range adds to selection and works in reverse"
);

assert.equal(autoScrollVelocity(0, 800), -18, "Pointer at the top edge must use maximum upward speed");
assert.equal(autoScrollVelocity(10, 800), -16, "Upward auto-scroll must ease with distance from the edge");
assert.equal(autoScrollVelocity(790, 800), 16, "Downward auto-scroll must ease with distance from the edge");
assert.equal(autoScrollVelocity(800, 800), 18, "Pointer at the bottom edge must use maximum downward speed");
assert.equal(autoScrollVelocity(400, 800), 0, "Pointer away from viewport edges must not auto-scroll");

console.log("reup-queue-drag-selection tests passed");
