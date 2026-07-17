import assert from "node:assert/strict";

import { isBackendVerifyItemFullyCollectedForHybridPreSkip } from "./wholeProfileHarvest/hybridBackendVerify.js";

assert.equal(
  isBackendVerifyItemFullyCollectedForHybridPreSkip({ aweme_id: "7000000000000000001" }),
  true,
  "minimal verify payloads without metadata signals stay pre-skippable for idempotency"
);

assert.equal(
  isBackendVerifyItemFullyCollectedForHybridPreSkip({
    aweme_id: "7000000000000000002",
    metadata_status: "complete",
    source_url: null,
    share_url: null
  }),
  false,
  "metadata_status complete without source/share must not block re-collect"
);

assert.equal(
  isBackendVerifyItemFullyCollectedForHybridPreSkip({
    aweme_id: "7000000000000000003",
    metadata_status: "partial",
    source_url: "https://www.douyin.com/video/7000000000000000003",
    share_url: "https://www.douyin.com/video/7000000000000000003",
    has_likes: true,
    has_duration: true,
    has_posted: true,
    has_thumbnail: true
  }),
  false,
  "partial rows must be eligible for hybrid re-hydration"
);

assert.equal(
  isBackendVerifyItemFullyCollectedForHybridPreSkip({
    aweme_id: "7000000000000000004",
    has_all_core_metadata: true
  }),
  true,
  "has_all_core_metadata is authoritative"
);

assert.equal(
  isBackendVerifyItemFullyCollectedForHybridPreSkip({
    aweme_id: "7000000000000000005",
    metadata_status: "complete",
    source_url: "https://www.douyin.com/video/7000000000000000005",
    share_url: "https://www.douyin.com/video/7000000000000000005",
    has_likes: true,
    has_duration: true,
    has_posted: true,
    has_thumbnail: true
  }),
  true,
  "fully finalized hybrid rows remain pre-skippable"
);

console.info("hybridBackendVerify.test.ts: PASS");
