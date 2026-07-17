// Part A regression: the profile target repository must NEVER downgrade a
// flush-ready profile_card_evidence to a thinner one on re-upsert.
//
// Production bug: repository upserts do a blind `store.put`, so a later collect /
// gap / reconcile pass that persisted thin (or previously fabricated) evidence
// overwrote the rich per-video metrics captured during scan. The oldest ~168
// videos then had no real metrics at collect time and could not be collected.

import assert from "node:assert/strict";
import test from "node:test";

import {
  InMemoryProfileTargetRepository,
  mergeProfileCardEvidencePreservingRicher
} from "./wholeProfileHarvest/profileTargetRepository.js";
import { evidenceIsHybridFlushReady } from "./wholeProfileHarvest/hybridHydration.js";
import type { WholeProfileHarvestQueueItem } from "./wholeProfileHarvest/state.js";

const richEvidence = (): Record<string, unknown> => ({
  aweme_id: "v1",
  source_url: "https://www.douyin.com/video/v1",
  duration_seconds: 15,
  like_count: 1234,
  comment_count: 56,
  favorite_count: 7,
  share_count: 8,
  thumbnail_url: "https://p3-sign.douyinpic.com/tos-cn-i/abc~tplv.jpeg?x-signature=z",
  posted_at: "2024-05-01T00:00:00.000Z"
});

const thinEvidence = (): Record<string, unknown> => ({
  aweme_id: "v1",
  source_url: "https://www.douyin.com/video/v1",
  caption: "hello"
});

test("mergeProfileCardEvidencePreservingRicher keeps rich metrics when incoming is thin", () => {
  const merged = mergeProfileCardEvidencePreservingRicher(richEvidence(), thinEvidence());
  assert.equal(evidenceIsHybridFlushReady(merged), true, "must stay flush-ready");
  assert.equal(merged.like_count, 1234, "rich like_count preserved");
  assert.equal(merged.duration_seconds, 15, "rich duration preserved");
  assert.equal(merged.caption, "hello", "incoming caption merged in");
});

test("mergeProfileCardEvidencePreservingRicher upgrades thin existing with rich incoming", () => {
  const merged = mergeProfileCardEvidencePreservingRicher(thinEvidence(), richEvidence());
  assert.equal(evidenceIsHybridFlushReady(merged), true, "rich incoming wins");
  assert.equal(merged.like_count, 1234);
});

test("mergeProfileCardEvidencePreservingRicher handles null/empty inputs", () => {
  assert.deepEqual(mergeProfileCardEvidencePreservingRicher(null, thinEvidence()), thinEvidence());
  assert.deepEqual(mergeProfileCardEvidencePreservingRicher(richEvidence(), null), richEvidence());
});

test("repository upsertProfileTargetPage must not overwrite rich evidence with thin", async () => {
  const repo = new InMemoryProfileTargetRepository();
  const profile = `evidence-merge-test-${Date.now()}`;
  const mkItem = (evidence: Record<string, unknown>): WholeProfileHarvestQueueItem => ({
    index: 1,
    aweme_id: "v1",
    capture_status: "new",
    status: "pending",
    attempts: 0,
    checkpoint_sequence: null,
    extraction_result: null,
    last_error: null,
    capture_inbox_item_id: null,
    source_url: "https://www.douyin.com/video/v1",
    thumbnail_url: null,
    caption: null,
    profile_card_evidence: evidence
  } as WholeProfileHarvestQueueItem);

  // Scan persisted rich evidence first.
  await repo.upsertProfileTargets(profile, [mkItem(richEvidence())], [], "2024-05-01T00:00:00.000Z");
  // A later thin page/reconcile must NOT wipe the rich metrics.
  await repo.upsertProfileTargetPage(profile, [mkItem(thinEvidence())], [], "2024-05-02T00:00:00.000Z");

  const window = await repo.getProfileTargetsByStatus(profile, ["pending"], 10, 0);
  const stored = window.records[0]?.queue_item?.profile_card_evidence as Record<string, unknown> | undefined;
  assert.ok(stored, "record present");
  assert.equal(evidenceIsHybridFlushReady(stored!), true, "stored evidence must remain flush-ready after thin re-upsert");
  assert.equal(stored!.like_count, 1234, "rich like_count preserved through re-upsert");
});
