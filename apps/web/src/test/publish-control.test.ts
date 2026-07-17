import assert from "node:assert/strict";
import { defaultAssignmentReason, healthTone, queueAttentionCount } from "../lib/publishControlState";
import type { PublishQueueItem } from "../types/publish-control";

assert.equal(healthTone("HEALTHY"), "good");
assert.equal(healthTone("DEGRADED"), "warn");
assert.equal(healthTone("UNHEALTHY"), "danger");
assert.equal(healthTone("HELD"), "muted");

const item: PublishQueueItem = {
  publish_draft_id: "draft-1",
  source_video_id: "video-1",
  title: "Draft",
  status: "READY",
  target_platform: "FACEBOOK_REELS",
  planned_publish_at: null,
  assigned_platform_account_id: null,
  assignment_status: "UNASSIGNED",
  assigned_reason: null,
  recommended_platform_account_id: "account-1",
  recommended_account_name: "Page A",
  recommendation_reasons: ["Matched routing rule recommendation"],
  warnings: []
};

assert.equal(defaultAssignmentReason(item), "Matched routing rule recommendation");
assert.equal(queueAttentionCount([item, { ...item, publish_draft_id: "draft-2", assignment_status: "OVERRIDDEN" }]), 1);
assert.equal(queueAttentionCount([{ ...item, warnings: ["Account degraded"] }]), 1);

console.log("publish-control state tests passed");
