import assert from "node:assert/strict";
import {
  formatReupScoreBadgeValue,
  reupScoreBadgeLevel,
  reupScoreBadgeLevelForCaptureItem,
  reupScoreBadgeTier
} from "../lib/reupScoreBadge";

assert.equal(formatReupScoreBadgeValue(83.6), "84");
assert.equal(formatReupScoreBadgeValue(null), "Unscored");
assert.equal(reupScoreBadgeTier(83), "Excellent");
assert.equal(reupScoreBadgeTier(65), "Strong");
assert.equal(reupScoreBadgeTier(45), "Medium");
assert.equal(reupScoreBadgeTier(20), "Low");
assert.equal(reupScoreBadgeLevel(83), "excellent");
assert.equal(
  reupScoreBadgeLevelForCaptureItem(83, { hasAllCoreMetadata: false }),
  "needs_metadata",
  "Capture Inbox must keep metadata-aware badge level"
);
assert.equal(reupScoreBadgeLevelForCaptureItem(83, { hasAllCoreMetadata: true }), "excellent");

console.log("reup-score-badge tests passed");
