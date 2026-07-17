import assert from "node:assert/strict";

import {
  discoverMissingAwemeIdsViaTailReconcileSources,
  finalizeTailGapDiscoveryDiagnostics,
  recoverTailGapCollectQueue
} from "./wholeProfileHarvest/hybridTailGapQueueRecovery.js";
import { createWholeProfileHarvestIdleState } from "./wholeProfileHarvest/state.js";

const at = "2026-07-09T06:30:00.000Z";
const baseState = {
  ...createWholeProfileHarvestIdleState(at),
  profile_url: "https://www.douyin.com/user/MS4wLjABAAAA-tail",
  source_url: "https://www.douyin.com/user/MS4wLjABAAAA-tail"
};

{
  const captured = new Set(["7000000000000000001"]);
  const tail = discoverMissingAwemeIdsViaTailReconcileSources({
    capturedIds: captured,
    limit: 3,
    profileUrl: baseState.profile_url!,
    passiveDiagnostics: {
      network_profile_post_targets: [
        { aweme_id: "7000000000000000001", source_url: "https://www.douyin.com/video/7000000000000000001", endpoint_kind: "profile_post", endpoint_path: "/aweme/v1/web/aweme/post/" },
        { aweme_id: "7632645553700031784", source_url: "https://www.douyin.com/video/7632645553700031784", endpoint_kind: "profile_post", endpoint_path: "/aweme/v1/web/aweme/post/" }
      ]
    },
    domProbeDiagnostics: {
      tail_reconcile_candidate_ids: ["7635333669418175794"]
    }
  });
  assert.deepEqual(tail.aweme_ids, ["7632645553700031784", "7635333669418175794"]);
  assert.equal(tail.stop_reason, "tail_reconcile_found");
}

{
  const captured = new Set(["7000000000000000001", "7000000000000000002"]);
  const recovered = await recoverTailGapCollectQueue({
    state: baseState,
    remaining: 3,
    at,
    capturedIds: captured,
    profileUrl: baseState.profile_url,
    profilePostPageBudget: 4,
    fetchProfilePostPage: async (cursor) => ({
      ok: true,
      verified_target_details: cursor === 0
        ? [{ aweme_id: "7000000000000000001", profile_card_evidence: { aweme_id: "7000000000000000001" } }]
        : [
          { aweme_id: "7163593122105052429", source_url: "https://www.douyin.com/video/7163593122105052429", profile_card_evidence: { aweme_id: "7163593122105052429", duration_seconds: 10, like_count: 1, comment_count: 1, favorite_count: 1, share_count: 1, thumbnail_url: "https://p3.douyinpic.com/a.jpg", posted_at: "2024-01-01T00:00:00.000Z" } },
          { aweme_id: "7195021188349922618", source_url: "https://www.douyin.com/video/7195021188349922618", profile_card_evidence: { aweme_id: "7195021188349922618", duration_seconds: 10, like_count: 1, comment_count: 1, favorite_count: 1, share_count: 1, thumbnail_url: "https://p3.douyinpic.com/b.jpg", posted_at: "2024-01-02T00:00:00.000Z" } }
        ],
      has_more: cursor === 0,
      next_cursor: cursor === 0 ? 20 : null,
      stop_reason: cursor === 0 ? "page_ok_has_more" : "has_more_false"
    }),
    rebuildQueue: async (missingIds) => ({
      ...baseState,
      harvest: {
        ...baseState.harvest,
        queue: missingIds.map((aweme_id, index) => ({
          aweme_id,
          index,
          status: "needs_metadata" as const,
          capture_status: "incomplete" as const,
          extraction_result: null,
          last_error: null,
          profile_card_evidence: { aweme_id }
        })),
        pending: missingIds.length
      },
      updated_at: at
    })
  });
  assert.deepEqual(recovered.discoveredIds, ["7163593122105052429", "7195021188349922618"]);
  assert.equal(recovered.state.harvest.queue.length, 2);
  const summary = recovered.state.debug.last_response_summary as Record<string, unknown>;
  assert.equal(summary.hybrid_exact_tail_gap_mode, "yes");
  assert.equal(summary.hybrid_backend_gap_missing_ids, "7163593122105052429,7195021188349922618");
  assert.equal(recovered.discoveryDiagnostics.hybrid_tail_gap_discovery_found, 2);
}

{
  const captured = new Set(["7000000000000000001", "7000000000000000002", "7000000000000000003"]);
  const profileUrl = "https://www.douyin.com/user/MS4wLjABAAAA-tail";
  const recovered = await recoverTailGapCollectQueue({
    state: baseState,
    remaining: 3,
    at,
    capturedIds: captured,
    profileUrl,
    profilePostPageBudget: 2,
    fetchProfilePostPage: async () => ({
      ok: true,
      verified_target_details: [],
      has_more: false,
      next_cursor: null,
      stop_reason: "pagination_exhausted"
    }),
    discoverViaTailReconcile: async () => ({
      aweme_ids: ["7632645553700031784", "7635333669418175794", "7638128982059224371"],
      stop_reason: "tail_reconcile_found",
      candidate_count: 5,
      passive_count: 3,
      dom_count: 2
    }),
    rebuildQueue: async (missingIds) => ({
      ...baseState,
      harvest: {
        ...baseState.harvest,
        queue: missingIds.map((aweme_id, index) => ({
          aweme_id,
          index,
          status: "pending" as const,
          capture_status: "new" as const,
          extraction_result: null,
          last_error: null,
          profile_card_evidence: { aweme_id }
        })),
        pending: missingIds.length
      },
      updated_at: at
    })
  });
  assert.deepEqual(recovered.discoveredIds, ["7632645553700031784", "7635333669418175794", "7638128982059224371"]);
  assert.equal(recovered.discoveryDiagnostics.hybrid_tail_gap_tail_reconcile_found, 3);
  assert.equal(recovered.discoveryDiagnostics.hybrid_tail_gap_discovery_source, "tail_reconcile");
}

{
  const recovered = await recoverTailGapCollectQueue({
    state: baseState,
    remaining: 3,
    at,
    capturedIds: new Set(["7000000000000000001", "7000000000000000002", "7000000000000000003"]),
    profileUrl: baseState.profile_url,
    profilePostPageBudget: 1,
    fetchProfilePostPage: async () => ({
      ok: true,
      verified_target_details: [],
      has_more: false,
      next_cursor: null,
      stop_reason: "pagination_exhausted"
    }),
    discoverViaTailReconcile: async () => ({
      aweme_ids: [],
      stop_reason: "no_tail_reconcile_candidates",
      candidate_count: 0,
      passive_count: 0,
      dom_count: 0
    }),
    rebuildQueue: async () => null
  });
  assert.deepEqual(recovered.discoveredIds, []);
  assert.equal(recovered.discoveryDiagnostics.hybrid_tail_gap_tail_reconcile_stop_reason, "no_tail_reconcile_candidates");
  assert.equal(recovered.discoveryDiagnostics.hybrid_tail_gap_tail_reconcile_found, 0);
  assert.ok(
    typeof recovered.discoveryDiagnostics.hybrid_tail_gap_discovery_stop_reason === "string"
    && recovered.discoveryDiagnostics.hybrid_tail_gap_discovery_stop_reason.length > 0,
    "discovery stop reason must be populated"
  );
}

{
  const recovered = await recoverTailGapCollectQueue({
    state: baseState,
    remaining: 3,
    at,
    capturedIds: new Set(["7000000000000000001", "7000000000000000002", "7000000000000000003"]),
    profileUrl: baseState.profile_url,
    profilePostPageBudget: 1,
    fetchProfilePostPage: async () => ({
      ok: false,
      verified_target_details: [],
      has_more: null,
      next_cursor: null,
      stop_reason: "extractor_no_targets"
    }),
    discoverViaTailReconcile: async () => ({
      aweme_ids: [],
      stop_reason: "all_tail_reconcile_candidates_already_captured",
      candidate_count: 12,
      passive_count: 0,
      dom_count: 12
    }),
    rebuildQueue: async () => null
  });
  assert.deepEqual(recovered.discoveredIds, []);
  assert.equal(recovered.discoveryDiagnostics.hybrid_tail_gap_discovery_stop_reason, "gap_ids_unreachable_rescan_required");
  assert.ok(typeof recovered.discoveryDiagnostics.hybrid_tail_gap_operator_hint === "string");
}

{
  // Operator fossil: has_more_false + DOM already-captured is proven unreachable (736/739 case).
  const recovered = await recoverTailGapCollectQueue({
    state: baseState,
    remaining: 3,
    at,
    capturedIds: new Set(["7000000000000000001", "7000000000000000002", "7000000000000000003"]),
    profileUrl: baseState.profile_url,
    profilePostPageBudget: 4,
    fetchProfilePostPage: async () => ({
      ok: true,
      verified_target_details: [
        { aweme_id: "7000000000000000001", profile_card_evidence: { aweme_id: "7000000000000000001" } }
      ],
      has_more: false,
      next_cursor: null,
      stop_reason: "has_more_false"
    }),
    discoverViaTailReconcile: async () => ({
      aweme_ids: [],
      stop_reason: "all_tail_reconcile_candidates_already_captured",
      candidate_count: 20,
      passive_count: 0,
      dom_count: 20
    }),
    rebuildQueue: async () => null
  });
  assert.deepEqual(recovered.discoveredIds, []);
  assert.equal(
    recovered.discoveryDiagnostics.hybrid_tail_gap_discovery_stop_reason,
    "gap_ids_unreachable_rescan_required",
    "has_more_false + DOM already-captured must upgrade to unreachable"
  );
  assert.equal(recovered.discoveryDiagnostics.hybrid_unreachable_tail_gap_offer, "yes");
}

{
  // Proven unreachable in fossil/state must not re-run profile-post or DOM discovery.
  let profilePostCalls = 0;
  let reconcileCalls = 0;
  const provenState = {
    ...baseState,
    debug: {
      ...baseState.debug,
      last_response_summary: {
        hybrid_tail_gap_discovery_stop_reason: "gap_ids_unreachable_rescan_required",
        hybrid_tail_gap_live_remaining: 3
      }
    }
  };
  const recovered = await recoverTailGapCollectQueue({
    state: provenState,
    remaining: 3,
    at,
    capturedIds: new Set(["7000000000000000001"]),
    profileUrl: baseState.profile_url,
    profilePostPageBudget: 24,
    priorFossil: {
      hybrid_tail_gap_discovery_stop_reason: "gap_ids_unreachable_rescan_required",
      hybrid_tail_gap_live_remaining: 3
    },
    fetchProfilePostPage: async () => {
      profilePostCalls += 1;
      throw new Error("must_not_rediscover_profile_post");
    },
    discoverViaTailReconcile: async () => {
      reconcileCalls += 1;
      throw new Error("must_not_rediscover_tail_reconcile");
    },
    rebuildQueue: async () => {
      throw new Error("must_not_rebuild_queue");
    }
  });
  assert.equal(profilePostCalls, 0, "must skip profile-post rediscovery");
  assert.equal(reconcileCalls, 0, "must skip DOM rediscovery");
  assert.deepEqual(recovered.discoveredIds, []);
  assert.equal(recovered.discoveryDiagnostics.hybrid_tail_gap_discovery_stop_reason, "gap_ids_unreachable_rescan_required");
  assert.equal(recovered.discoveryDiagnostics.hybrid_tail_gap_rediscovery_skipped, "yes");
  assert.equal(recovered.discoveryDiagnostics.hybrid_unreachable_tail_gap_offer, "yes");
}

{
  const finalized = finalizeTailGapDiscoveryDiagnostics({}, [], 3);
  assert.equal(finalized.hybrid_tail_gap_discovery_stop_reason, "discovery_exhausted");
  assert.equal(finalized.hybrid_tail_gap_discovery_found, undefined);
  assert.equal(finalized.hybrid_tail_gap_live_remaining, 3);
}

{
  const tail = discoverMissingAwemeIdsViaTailReconcileSources({
    capturedIds: new Set([
      "7000000000000000001",
      "7000000000000000002",
      "7000000000000000003",
      "7000000000000000004",
      "7000000000000000005"
    ]),
    limit: 2,
    profileUrl: baseState.profile_url!,
    passiveDiagnostics: {},
    domProbeDiagnostics: {
      tail_reconcile_candidate_ids: [
        "7000000000000000001",
        "7000000000000000002",
        "7000000000000000003",
        "7000000000000000006",
        "7000000000000000007"
      ]
    }
  });
  assert.deepEqual(tail.aweme_ids, ["7000000000000000006", "7000000000000000007"]);
}

console.info("hybridTailGapQueueRecovery.test.ts: all assertions passed");
