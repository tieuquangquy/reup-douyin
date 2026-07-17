import assert from "node:assert/strict";

import { createWholeProfileHarvestIdleState, type WholeProfileHarvestQueueItem, type WholeProfileHarvestTargetDetail } from "./wholeProfileHarvest/state.js";
import {
  enrichHarvestTargetsFromProfileRepository,
  syncActionableTargetsEvidenceFromHarvestState
} from "./wholeProfileHarvest/controller.js";
import {
  InMemoryProfileTargetRepository,
  profileIdentifierFromUrl,
  resetProfileTargetRepositoryForTests,
  setProfileTargetRepositoryFactoryForTests
} from "./wholeProfileHarvest/profileTargetRepository.js";
import { evidenceIsHybridFlushReady } from "./wholeProfileHarvest/hybridHydration.js";

const profileUrl = "https://www.douyin.com/user/MS4wLjABAAAA-pagination-test";

function flushReadyEvidence(awemeId: string): Record<string, unknown> {
  return {
    aweme_id: awemeId,
    duration_seconds: 12,
    like_count: 100,
    comment_count: 5,
    favorite_count: 3,
    share_count: 1,
    thumbnail_url: "https://example.com/cover.jpg",
    posted_at: "2026-01-01T00:00:00.000Z"
  };
}

function queueItem(awemeId: string, evidence?: Record<string, unknown> | null): WholeProfileHarvestQueueItem {
  return {
    index: 1,
    aweme_id: awemeId,
    capture_status: "new",
    status: "pending",
    attempts: 0,
    checkpoint_sequence: null,
    extraction_result: null,
    last_error: null,
    capture_inbox_item_id: null,
    source_url: `https://www.douyin.com/video/${awemeId}`,
    profile_card_evidence: evidence ?? { aweme_id: awemeId }
  };
}

function targetDetail(awemeId: string, evidence?: Record<string, unknown> | null): WholeProfileHarvestTargetDetail {
  return {
    index: 1,
    aweme_id: awemeId,
    source_url: `https://www.douyin.com/video/${awemeId}`,
    profile_url: profileUrl,
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
    candidate_validation: { status: "accepted", source: "video_link", reason: null, source_url: `https://www.douyin.com/video/${awemeId}` },
    metadata_completeness: { has_profile_identity: true, has_thumbnail: false, has_title_or_caption: false, has_posted_text: false, has_duration: false, has_view_count: false, has_detail_metrics: false },
    capture_status: "new",
    backend_item: null,
    extraction_source: "video_link",
    profile_card_evidence: evidence ?? null
  };
}

{
  const repository = new InMemoryProfileTargetRepository();
  setProfileTargetRepositoryFactoryForTests(() => repository);
  const profile = profileIdentifierFromUrl(profileUrl);
  const awemeBeyondFirstPage = "7307426266041388288";
  const queue = Array.from({ length: 600 }, (_, index) => {
    const awemeId = index === 599 ? awemeBeyondFirstPage : `700000000000000${String(index + 1).padStart(4, "0")}`;
    return queueItem(awemeId, flushReadyEvidence(awemeId));
  });
  const details = queue.map((item) => targetDetail(item.aweme_id, item.profile_card_evidence as Record<string, unknown>));
  await repository.upsertProfileTargets(profile, queue, details, "2026-07-13T05:00:00.000Z");

  const state = {
    ...createWholeProfileHarvestIdleState(),
    profile_url: profileUrl,
    profile_scan: { ...createWholeProfileHarvestIdleState().profile_scan, target_details: [] }
  };
  const enriched = await enrichHarvestTargetsFromProfileRepository(state, [
    { aweme_id: awemeBeyondFirstPage, profile_card_evidence: { aweme_id: awemeBeyondFirstPage } }
  ]);
  assert.equal(enriched.length, 1);
  assert.equal(evidenceIsHybridFlushReady(enriched[0]?.profile_card_evidence), true, "pagination must find evidence beyond page 500");
  resetProfileTargetRepositoryForTests();
}

{
  const scanEvidence = flushReadyEvidence("7291704782362840360");
  const state = {
    ...createWholeProfileHarvestIdleState(),
    profile_url: profileUrl,
    profile_scan: {
      ...createWholeProfileHarvestIdleState().profile_scan,
      target_details: [targetDetail("7291704782362840360", scanEvidence)]
    },
    harvest: {
      ...createWholeProfileHarvestIdleState().harvest,
      queue: [queueItem("7291704782362840360", scanEvidence)]
    }
  };
  const synced = syncActionableTargetsEvidenceFromHarvestState(state, [
    { aweme_id: "7291704782362840360", profile_card_evidence: { aweme_id: "7291704782362840360" } }
  ]);
  assert.equal(evidenceIsHybridFlushReady(synced[0]?.profile_card_evidence), true, "sync must merge scan detail evidence onto actionable targets");
}

console.log("repositoryEvidencePagination.test.ts: PASS");
