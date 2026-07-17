import assert from "node:assert/strict";

import {
  collectKnownScannedAwemeIds,
  diffAwemeIdsMissingFromCaptured,
  isHybridTailGapCollect,
  queueMatchesExactGapAwemeIds,
  reopenTailGapQueueItemForCollect,
  resolveExactBackendGapAwemeIds
} from "./wholeProfileHarvest/hybridBackendGapAwemeIds.js";
import { createWholeProfileHarvestIdleState } from "./wholeProfileHarvest/state.js";

assert.equal(isHybridTailGapCollect(3), true);
assert.equal(isHybridTailGapCollect(26), false);

{
  const state = createWholeProfileHarvestIdleState("2026-07-09T02:00:00.000Z");
  state.profile_url = "https://www.douyin.com/user/MS4wLjABAAAA-gap";
  state.classification.collect_aweme_ids = [
    "7000000000000000001",
    "7000000000000000002",
    "7000000000000000003",
    "7000000000000000004"
  ];
  const captured = new Set(["7000000000000000001", "7000000000000000002"]);
  const missing = diffAwemeIdsMissingFromCaptured(collectKnownScannedAwemeIds(state), captured, 3);
  assert.deepEqual(missing, ["7000000000000000003", "7000000000000000004"]);
}

{
  const state = createWholeProfileHarvestIdleState("2026-07-09T02:00:00.000Z");
  state.profile_url = "https://www.douyin.com/user/MS4wLjABAAAA-gap";
  state.profile_scan.target_details = Array.from({ length: 739 }, (_, index) => ({
    index: index + 1,
    aweme_id: `7330000000000${String(index).padStart(3, "0")}`,
    source_url: `https://www.douyin.com/video/7330000000000${String(index).padStart(3, "0")}`,
    profile_url: state.profile_url,
    thumbnail_url: null,
    title: null,
    caption: null,
    text_sample: null,
    posted_text: null,
    posted_at: null,
    duration_text: null,
    duration_seconds: null,
    view_text: null,
    view_count: null,
    candidate_validation: { status: "accepted", source: "video_link", reason: null, source_url: null },
    metadata_completeness: {
      has_profile_identity: true,
      has_thumbnail: false,
      has_title_or_caption: false,
      has_posted_text: false,
      has_duration: false,
      has_view_count: false,
      has_detail_metrics: false
    },
    capture_status: "new",
    backend_item: null,
    extraction_source: "video_link",
    profile_card_evidence: {}
  }));
  const captured = new Set(
    state.profile_scan.target_details.slice(0, 736).map((detail) => detail.aweme_id)
  );
  const missing = diffAwemeIdsMissingFromCaptured(collectKnownScannedAwemeIds(state), captured, 5);
  assert.equal(missing.length, 3, "739 scanned minus 736 captured leaves exactly 3 gap ids");
  assert.equal(missing[0], "7330000000000736");
}

{
  const state = createWholeProfileHarvestIdleState("2026-07-09T02:00:00.000Z");
  state.profile_url = "https://www.douyin.com/user/MS4wLjABAAAA-gap";
  state.classification.collect_aweme_ids = ["7000000000000000009"];
  const exact = await resolveExactBackendGapAwemeIds({
    state,
    capturedIds: new Set(["7000000000000000001"]),
    limit: 2
  });
  assert.deepEqual(exact, ["7000000000000000009"]);
}

{
  const reopened = reopenTailGapQueueItemForCollect({
    status: "skipped",
    capture_status: "complete",
    last_error: "missing_hybrid_metrics",
    profile_card_evidence: { hybrid_uncollectable: true, hybrid_uncollectable_reason: "metrics_miss" }
  });
  assert.equal(reopened.status, "needs_metadata");
  assert.equal(reopened.capture_status, "incomplete");
  assert.equal(reopened.last_error, null);
  assert.equal(reopened.profile_card_evidence?.hybrid_uncollectable, false);
}

assert.equal(
  queueMatchesExactGapAwemeIds(["7001", "7002", "7003"], ["7001", "7002"]),
  false
);
assert.equal(
  queueMatchesExactGapAwemeIds(["7001", "7002"], ["7001", "7002"]),
  true
);

console.info("hybridBackendGapAwemeIds.test.ts: all assertions passed");
