import assert from "node:assert/strict";

import { createWholeProfileHarvestIdleState, type WholeProfileHarvestQueueItem, type WholeProfileHarvestTargetDetail } from "./wholeProfileHarvest/state.js";
import { FallbackProfileTargetRepository, InMemoryProfileTargetRepository, buildQueueWindowFromRecords, profileIdentifierFromUrl, type ProfileTargetRepository } from "./wholeProfileHarvest/profileTargetRepository.js";

function queueItem(index: number, status: WholeProfileHarvestQueueItem["status"] = "pending"): WholeProfileHarvestQueueItem {
  return {
    index,
    aweme_id: `700000000000000${String(index).padStart(4, "0")}`,
    capture_status: "new",
    status,
    attempts: 0,
    checkpoint_sequence: null,
    extraction_result: null,
    last_error: null,
    capture_inbox_item_id: null,
    source_url: `https://www.douyin.com/video/${index}`,
    profile_card_evidence: { profile_url: "https://www.douyin.com/user/MS4wLjABAAAA-large" }
  };
}

function targetDetail(item: WholeProfileHarvestQueueItem): WholeProfileHarvestTargetDetail {
  return {
    index: item.index,
    aweme_id: item.aweme_id,
    source_url: item.source_url,
    profile_url: "https://www.douyin.com/user/MS4wLjABAAAA-large",
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
    candidate_validation: { status: "accepted", source: "video_link", reason: null, source_url: item.source_url },
    metadata_completeness: { has_profile_identity: true, has_thumbnail: false, has_title_or_caption: false, has_posted_text: false, has_duration: false, has_view_count: false, has_detail_metrics: false },
    capture_status: item.capture_status,
    backend_item: null,
    extraction_source: "video_link",
    profile_card_evidence: item.profile_card_evidence
  };
}

{
  const repository = new InMemoryProfileTargetRepository();
  const profile = profileIdentifierFromUrl("https://www.douyin.com/user/MS4wLjABAAAA-large");
  const queue = Array.from({ length: 1001 }, (_, index) => queueItem(index + 1));
  const details = queue.map(targetDetail);
  const upsert = await repository.upsertProfileTargets(profile, queue, details, "2026-05-30T05:00:00.000Z");
  assert.equal(upsert.total, 1001, "repository must preserve more than 1000 targets");
  const firstWindow = await repository.getProfileTargetsByStatus(profile, ["pending"], 100, 0);
  assert.equal(firstWindow.total, 1001);
  assert.equal(firstWindow.records.length, 100);
  assert.equal(firstWindow.records[0]?.sequence, 1);
  assert.equal(firstWindow.records[99]?.sequence, 100);
  const secondWindow = await repository.getProfileTargetsByStatus(profile, ["pending"], 100, 100);
  assert.equal(secondWindow.records[0]?.sequence, 101, "offset window must start at cursor + 1");
  const built = buildQueueWindowFromRecords(secondWindow.records);
  assert.equal(built.queue.length, 100);
  assert.equal(built.queue[0]?.index, 101);
}

{
  const repository = new InMemoryProfileTargetRepository();
  const profile = "incremental_scan_profile";
  const firstPage = Array.from({ length: 60 }, (_, index) => queueItem(index + 1));
  const secondPage = Array.from({ length: 60 }, (_, index) => queueItem(index + 61));
  const firstResult = await repository.upsertProfileTargetPage(profile, firstPage, firstPage.map(targetDetail), "2026-05-30T05:00:00.000Z");
  assert.equal(firstResult.total, 60, "first scan page should persist all discovered targets");
  const secondResult = await repository.upsertProfileTargetPage(profile, secondPage, secondPage.map(targetDetail), "2026-05-30T05:01:00.000Z");
  assert.equal(secondResult.total, 120, "second scan page must append without deleting previous page targets");
  const duplicatePatch = [queueItem(30, "needs_metadata")];
  const duplicateResult = await repository.upsertProfileTargetPage(profile, duplicatePatch, duplicatePatch.map(targetDetail), "2026-05-30T05:02:00.000Z");
  assert.equal(duplicateResult.total, 120, "duplicate scan page targets must update in place without inflating totals");
  const firstWindow = await repository.getProfileTargetsByStatus(profile, ["pending", "needs_metadata"], 100, 0);
  assert.equal(firstWindow.total, 120, "incremental scan repository total should remain authoritative beyond preview window");
  assert.equal(firstWindow.records.length, 100, "preview window remains bounded");
  assert.equal(firstWindow.records.find((record) => record.aweme_id === duplicatePatch[0]!.aweme_id)?.status, "needs_metadata");
  const secondWindow = await repository.getProfileTargetsByStatus(profile, ["pending", "needs_metadata"], 100, 100);
  assert.equal(secondWindow.records.length, 20, "offset window should expose records beyond visible preview");
}

{
  const repository = new InMemoryProfileTargetRepository();
  const profile = "cursor_profile";
  const queue = Array.from({ length: 12 }, (_, index) => queueItem(index + 1));
  await repository.upsertProfileTargets(profile, queue, queue.map(targetDetail), "2026-05-30T05:00:00.000Z");
  await repository.updateTargetStatus(profile, queue[4]!.aweme_id, { status: "extracted", attempts: 1, updated_at: "2026-05-30T05:01:00.000Z" }, {
    collect_cursor: 5,
    last_processed_aweme_id: queue[4]!.aweme_id,
    last_checkpoint_at: "2026-05-30T05:01:00.000Z",
    chunk_processed_count: 5,
    chunk_total_count: 12
  });
  const checkpoint = await repository.getCheckpoint(profile);
  assert.equal(checkpoint?.collect_cursor, 5);
  assert.equal(checkpoint?.last_processed_aweme_id, queue[4]!.aweme_id);
  const pending = await repository.getProfileTargetsByStatus(profile, ["pending"], 20, 0);
  assert.equal(pending.total, 11, "status update must remove extracted target from pending window");
  const extracted = await repository.getProfileTargetsByStatus(profile, ["extracted"], 20, 0);
  assert.equal(extracted.records[0]?.capture_status, "complete", "terminal extracted status must sync record capture_status");
  assert.equal(extracted.records[0]?.queue_item.capture_status, "complete", "terminal extracted status must sync queue item capture_status");
  assert.equal(extracted.records[0]?.target_detail.capture_status, "complete", "terminal extracted status must sync target detail capture_status");
  await repository.updateTargetStatus(profile, queue[0]!.aweme_id, { status: "already_collected", updated_at: "2026-05-30T05:02:00.000Z" });
  const collected = await repository.getProfileTargetsByStatus(profile, ["already_collected"], 20, 0);
  assert.equal(collected.records[0]?.capture_status, "complete", "already_collected status must sync record capture_status");
  assert.equal(collected.records[0]?.queue_item.capture_status, "complete", "already_collected status must sync queue item capture_status");
  assert.equal(collected.records[0]?.target_detail.capture_status, "complete", "already_collected status must sync target detail capture_status");
  const counts = await repository.countProfileTargetsByStatus(profile);
  assert.equal(counts.total, 12);
  assert.equal(counts.counts.find((item) => item.status === "extracted")?.count, 1);
  assert.equal(counts.counts.find((item) => item.status === "already_collected")?.count, 1);
  assert.equal(counts.counts.find((item) => item.status === "pending")?.count, 10);
}

{
  class FailingProfileTargetRepository extends InMemoryProfileTargetRepository implements ProfileTargetRepository {
    override async countProfileTargetsByStatus(): ReturnType<ProfileTargetRepository["countProfileTargetsByStatus"]> {
      throw new Error("indexeddb unavailable for test");
    }
  }
  const fallback = new InMemoryProfileTargetRepository();
  const profile = "degraded_profile";
  const queue = Array.from({ length: 3 }, (_, index) => queueItem(index + 1));
  await fallback.upsertProfileTargets(profile, queue, queue.map(targetDetail), "2026-05-30T05:00:00.000Z");
  const repository = new FallbackProfileTargetRepository(new FailingProfileTargetRepository(), fallback);
  const counts = await repository.countProfileTargetsByStatus(profile);
  assert.equal(counts.backend, "local");
  assert.equal(counts.degraded, true);
  assert.equal(counts.degraded_reason, "indexeddb unavailable for test");
  assert.equal(counts.total, 3);
}

{
  const state = createWholeProfileHarvestIdleState("2026-05-30T05:00:00.000Z");
  assert.equal(state.harvest.queue.length, 0, "idle fixture sanity check");
}
