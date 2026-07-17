// Regression: the backend-gap collect path must NEVER fabricate placeholder
// metadata for videos whose real metrics are not available.
//
// Production bug (image evidence: Capture Inbox showed 165 "needs action" items
// with identical like=1 / comment=1 / share=1 / duration=00:15 / posted=capture-time
// and "Thumbnail not captured"): `hybridEvidenceFromClassificationTarget` injected
// synthetic values (duration:15, like/comment/favorite/share:1, posted:now) plus a
// non-image `douyin.com/video/{id}` thumbnail. That fake evidence passed the finalize
// gate and was written to the backend as garbage `needs_action` items.
//
// Correct behavior: evidence built for a gap target that has no real metrics must be
// NOT hybrid-flush-ready, so the runner leaves it pending / skips it as uncollectable
// instead of writing fabricated data.

import assert from "node:assert/strict";
import test from "node:test";

import { hybridEvidenceFromClassificationTarget } from "./wholeProfileHarvest/controller.js";
import {
  evidenceHasHybridRequiredMetrics,
  evidenceIsHybridFlushReady
} from "./wholeProfileHarvest/hybridHydration.js";
import type { DouyinProfileVideoClassificationTarget } from "./wholeProfileHarvest/profileClassification.js";

function gapTarget(
  overrides: Partial<DouyinProfileVideoClassificationTarget> = {}
): DouyinProfileVideoClassificationTarget {
  return {
    aweme_id: "7531672982574419219",
    classification: "new",
    collect: true,
    reason: "backend_gap_recovery",
    required_missing_fields: [],
    existing_item_id: null,
    metadata_status: null,
    review_status: null,
    video_url: null,
    source_url: null,
    thumbnail_url: null,
    caption: null,
    ...overrides
  };
}

test("gap-collect evidence without real metrics must not fabricate placeholders", () => {
  const evidence = hybridEvidenceFromClassificationTarget(gapTarget());

  // No fabricated metric values.
  assert.equal(evidence.like_count ?? null, null, "like_count must not be fabricated");
  assert.equal(evidence.comment_count ?? null, null, "comment_count must not be fabricated");
  assert.equal(evidence.favorite_count ?? null, null, "favorite_count must not be fabricated");
  assert.equal(evidence.share_count ?? null, null, "share_count must not be fabricated");
  assert.equal(evidence.duration_seconds ?? null, null, "duration_seconds must not be fabricated");
  assert.equal(evidence.posted_at ?? null, null, "posted_at must not be fabricated (capture time)");
  assert.equal(evidence.create_time ?? null, null, "create_time must not be fabricated");

  // Therefore the evidence is not finalizable and will be skipped, not written.
  assert.equal(
    evidenceHasHybridRequiredMetrics(evidence),
    false,
    "fabricated-free evidence must not report complete metrics"
  );
  assert.equal(
    evidenceIsHybridFlushReady(evidence),
    false,
    "gap evidence without real data must not be flush-ready (would be written as needs_action garbage)"
  );
});

test("gap-collect evidence must not use a video-page URL as a thumbnail", () => {
  const evidence = hybridEvidenceFromClassificationTarget(gapTarget({ thumbnail_url: null }));
  const thumb = String(evidence.thumbnail_url ?? "");
  assert.ok(
    !/\/video\//.test(thumb),
    `thumbnail must not be a douyin video-page URL, got: ${thumb || "(none)"}`
  );
});

test("gap-collect evidence carries a real cover URL when the scan captured one", () => {
  const realCover = "https://p3-sign.douyinpic.com/tos-cn-i-0813/abc123~tplv-dy-cropcenter.jpeg?x-signature=xyz";
  const evidence = hybridEvidenceFromClassificationTarget(gapTarget({ thumbnail_url: realCover }));
  assert.equal(evidence.thumbnail_url, realCover, "a real captured cover URL must be preserved");
});
