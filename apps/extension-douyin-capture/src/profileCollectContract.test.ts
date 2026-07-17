import assert from "node:assert/strict";

import {
  applyProfileCollectContractToPostScanSnapshot,
  buildProfileCollectContractFromState,
  countPendingHydrationInScopedQueue
} from "./wholeProfileHarvest/profileCollectContract.js";
import { createWholeProfileHarvestIdleState } from "./wholeProfileHarvest/state.js";

const at = new Date().toISOString();
const base = createWholeProfileHarvestIdleState(at);

const diagnostics = {
  displayed_profile_count: 3304,
  expected_profile_video_count: 3304,
  api_collectable_count: 3382,
  over_displayed_count: 78,
  collect_scope: "displayed_profile_only"
};

const queue = [
  ...Array.from({ length: 3 }, (_, index) => ({
    aweme_id: `ready-${index}`,
    status: "pending" as const,
    capture_status: "new" as const,
    source_url: `https://www.douyin.com/video/ready-${index}`,
    profile_card_evidence: {
      aweme_id: `ready-${index}`,
      discovery_source: "active_profile_post_22C12B",
      like_count: 10,
      comment_count: 1,
      favorite_count: 1,
      share_count: 1,
      duration_seconds: 15,
      thumbnail_url: "https://p3-sign.douyinpic.com/x.jpeg",
      posted_at: "2024-01-01T00:00:00.000Z"
    }
  })),
  ...Array.from({ length: 2 }, (_, index) => ({
    aweme_id: `stub-${index}`,
    status: "pending" as const,
    capture_status: "new" as const,
    source_url: `https://www.douyin.com/video/stub-${index}`,
    profile_card_evidence: { aweme_id: `stub-${index}`, caption: "thin" }
  }))
];

assert.equal(
  countPendingHydrationInScopedQueue(queue, diagnostics),
  2,
  "pending hydration must count stub-only in-scope items"
);

const state = {
  ...base,
  profile_scan: {
    ...base.profile_scan,
    status: "success" as const,
    diagnostics
  },
  scan_job: {
    ...base.scan_job,
    status: "completed" as const,
    expected_count: 3304,
    total_persisted: 3304
  },
  post_scan_counter_snapshot: {
    status: "applied" as const,
    source: "backend_capture_inbox_profile_summary" as const,
    profile_identifier: "test-profile",
    scanned_total: 3382,
    backend_captured: 586,
    backend_ready: 586,
    backend_dup: 0,
    backend_fail: 0,
    already_collected: 586,
    incomplete: 0,
    need_retry: 0,
    new: 2796,
    queue: 2796,
    backend_captured_aweme_ids: [],
    applied_at: at
  },
  harvest: {
    ...base.harvest,
    queue: queue as typeof base.harvest.queue
  }
};

const contract = buildProfileCollectContractFromState(state);
assert.equal(contract.displayed_total, 3304);
assert.equal(contract.captured, 586);
assert.equal(contract.new_count, 2718);
assert.equal(contract.queue_count, 2718);
assert.equal(contract.api_extra_count, 78);

const patched = applyProfileCollectContractToPostScanSnapshot(state.post_scan_counter_snapshot!, contract);
assert.equal(patched.scanned_total, 3304);
assert.equal(patched.new, 2718);
assert.equal(patched.queue, 2718);

console.info("profileCollectContract.test.ts: PASS");
