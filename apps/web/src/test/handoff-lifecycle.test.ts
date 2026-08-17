/**
 * Publish Handoff lifecycle compacting — merge same-minute stamps.
 */
import assert from "node:assert/strict";
import { mergeLifecycleByMinute, type HandoffLifecycleStep } from "../lib/handoffLifecycle";

function format(iso: string) {
  return iso.slice(0, 16);
}

const steps: HandoffLifecycleStep[] = [
  { key: "created", label: "Created at", at: "2026-08-15T16:13:00.000Z", tone: "done" },
  { key: "ready", label: "Ready", at: "2026-08-15T16:13:20.000Z", tone: "done" },
  { key: "accepted", label: "Accepted at", at: null, tone: "pending" }
];

const merged = mergeLifecycleByMinute(steps, format);

assert.equal(merged.length, 2, "Same-minute created/ready must collapse to one node");
assert.equal(merged[0]?.label, "Created at · Ready");
assert.equal(merged[0]?.at, "2026-08-15T16:13:00.000Z");
assert.equal(merged[1]?.key, "accepted");

assert.equal(
  mergeLifecycleByMinute(
    [
      { key: "created", label: "Created at", at: "2026-08-15T16:13:00.000Z", tone: "done" },
      { key: "ready", label: "Ready", at: "2026-08-15T17:00:00.000Z", tone: "done" }
    ],
    format
  ).length,
  2,
  "Different minutes must stay separate"
);

console.log("handoff-lifecycle tests passed");
