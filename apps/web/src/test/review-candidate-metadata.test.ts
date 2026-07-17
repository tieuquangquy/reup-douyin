import assert from "node:assert/strict";
import { buildCapturedItemFromReviewCandidate } from "../lib/operatorReupScore";
import { getReupScoreForCaptureItem } from "../lib/captureInboxReupScore";
import { getReviewCandidateMetadata, reviewCandidateDisplayScore, reviewCandidateViewsForSort } from "../lib/reviewCandidateMetadata";
import type { Candidate } from "../types/review-board";

const canonical = makeCandidate({
  estimated_views_display: "1.2K",
  estimated_views_mid: 1200,
  like_count: 0,
  comment_count: null,
  share_count: undefined,
  reup_score: 87,
  thumbnail_url: "https://cdn.example.test/thumb.jpg"
});
const canonicalMetadata = getReviewCandidateMetadata(canonical);
assert.equal(canonicalMetadata.estimated_views_display, "1.2K");
assert.equal(canonicalMetadata.estimatedViewsDisplay, "1.2K");
assert.equal(canonicalMetadata.estimated_views_mid, 1200);
assert.equal(canonicalMetadata.estimatedViewsMid, 1200);
assert.equal(canonicalMetadata.like_count, 0, "explicit source zero must remain zero");
assert.equal(canonicalMetadata.comment_count, null, "missing comments must stay null");
assert.equal(canonicalMetadata.share_count, null, "score fallback zero must not become fake source data");
assert.equal(canonicalMetadata.reup_score, 87);
assert.equal(canonicalMetadata.reupScore, 87);
assert.equal(canonicalMetadata.thumbnail_url, "https://cdn.example.test/thumb.jpg");
assert.equal(canonicalMetadata.thumbnailUrl, "https://cdn.example.test/thumb.jpg");
assert.equal(reviewCandidateViewsForSort(canonical), 1200);

const legacySource = makeCandidate({}, { estimated_views_display: "900", estimated_views_mid: 900, shares: 4 });
const legacyMetadata = getReviewCandidateMetadata(legacySource);
assert.equal(legacyMetadata.estimated_views_display, "900");
assert.equal(legacyMetadata.estimated_views_mid, 900);
assert.equal(legacyMetadata.share_count, 4);

const promotedCapture = makeCandidate({
  score: 21.1,
  reup_score: 42,
  aweme_id: "7621110952095665451",
  estimated_views_display: "4.1K-20.3K",
  estimated_views_min: 4100,
  estimated_views_max: 20300,
  estimated_views_mid: 12200,
  like_count: 203,
  comment_count: 7,
  share_count: 18,
  duration_seconds: 30,
  thumbnail_url: "https://cdn.example.test/thumb.jpg",
  posted_display: "23:00:00 24/3/2026"
});
const promotedMetadata = getReviewCandidateMetadata(promotedCapture);
const promotedOperatorScore = reviewCandidateDisplayScore(promotedCapture);
assert.equal(promotedMetadata.reupScore, 42);
assert.equal(
  promotedOperatorScore,
  getReupScoreForCaptureItem(buildCapturedItemFromReviewCandidate(promotedCapture)).reup_score,
  "Review Board operator score must match Capture Inbox formula"
);
assert.notEqual(promotedOperatorScore, 21.1, "Review Board operator score must not use internal candidate.score");
assert.equal(promotedMetadata.awemeId, "7621110952095665451");
assert.equal(promotedMetadata.estimatedViewsDisplay, "4.1K-20.3K");
assert.equal(promotedMetadata.postedDisplay, "23:00:00 24/3/2026");

const fishCapture = makeCandidate({
  score: 21.05,
  reup_score: null,
  aweme_id: "stale-aweme",
  estimated_views_display: null,
  like_count: null,
  comment_count: null,
  share_count: null,
  posted_display: null,
  source_metadata: {
    source_metadata_version: "22F-1F",
    aweme_id: "7622664109737250084",
    reup_score: 42,
    estimated_views_display: "3.7K-18.3K",
    estimated_views_min: 3660,
    estimated_views_max: 18300,
    estimated_views_mid: 6039,
    like_count: 183,
    comment_count: 12,
    share_count: 13,
    duration_seconds: 30,
    thumbnail_url: "https://cdn.example.test/thumb.jpg",
    posted_display: "23:00:00 28/3/2026"
  }
});
const fishMetadata = getReviewCandidateMetadata(fishCapture);
const fishOperatorScore = reviewCandidateDisplayScore(fishCapture);
assert.equal(
  fishOperatorScore,
  getReupScoreForCaptureItem(buildCapturedItemFromReviewCandidate(fishCapture)).reup_score,
  "fish Review Board score must use the shared operator formula, not internal candidate.score"
);
assert.notEqual(fishOperatorScore, 21.05, "fish Review Board score must not use internal candidate.score");
assert.equal(fishMetadata.estimatedViewsDisplay, "3.7K-18.3K");
assert.equal(fishMetadata.likeCount, 183);
assert.equal(fishMetadata.commentCount, 12);
assert.equal(fishMetadata.shareCount, 13);
assert.equal(fishMetadata.durationText, "0:30");
assert.equal(fishMetadata.postedDisplay, "23:00:00 28/3/2026");

const internalScoreOnly = makeCandidate({
  score: 21.05,
  reup_score: null,
  source_metadata: {}
});
assert.equal(reviewCandidateDisplayScore(internalScoreOnly), 0, "empty metadata should operator-score to zero, not internal candidate.score");
assert.equal(getReviewCandidateMetadata(internalScoreOnly).reupScore, null);

const missingViews = makeCandidate({
  estimated_views_display: null,
  estimated_views_min: null,
  estimated_views_max: null,
  estimated_views_mid: null,
  view_count: null,
  source_metadata: {}
});
const missingViewsMetadata = getReviewCandidateMetadata(missingViews);
assert.equal(missingViewsMetadata.estimatedViewsDisplay, null, "missing estimated views must remain missing, not 0");
assert.equal(missingViewsMetadata.estimatedViewsMin, null);
assert.equal(missingViewsMetadata.estimatedViewsMax, null);
assert.equal(missingViewsMetadata.estimatedViewsMid, null);
assert.equal(missingViewsMetadata.viewCount, null);

const raccoonCapture = makeCandidate({
  source_metadata: {
    caption: "114浣熊与黑熊 fixture",
    posted_at: "2026-04-02T16:00:00Z",
    posted_display: "23:00:00 2/4/2026",
    posted_text_raw: "2/4/2026",
    duration_seconds: 734,
    duration_text: "12:14"
  },
  source_video: {
    id: "video-1",
    source_profile_id: "profile-1",
    source_video_external_id: "7621140000000000000",
    source_url: "https://www.douyin.com/video/7621140000000000000",
    caption: "114浣熊与黑熊 fixture",
    posted_at: "2026-04-02T16:00:00Z",
    duration_seconds: 734,
    metadata_json: {}
  }
});
const raccoonMetadata = getReviewCandidateMetadata(raccoonCapture);
assert.equal(raccoonMetadata.postedDisplay, "23:00:00 2/4/2026");
assert.equal(raccoonMetadata.postedSource, "source_metadata.posted_display");
assert.notEqual(raccoonMetadata.postedDisplay, "03/04/2026");
assert.equal(raccoonMetadata.durationText, "12:14");
assert.equal(raccoonMetadata.durationSource, "source_metadata.duration_text");
assert.equal(raccoonMetadata.durationSeconds, 734);

const birdCapture = makeCandidate({
  score: 55,
  reup_score: 7,
  posted_display: "03/04/2026",
  postedDisplay: "03/04/2026",
  metadata_json: { posted_display: "metadata-stale", posted_text_raw: "metadata-raw-stale" },
  source_metadata: {
    caption: "190最聪明的鱼和最奇怪的鸟",
    posted_at: "2026-04-02T16:00:00Z",
    posted_display: "23:00:00 2/4/2026",
    posted_text_raw: "2/4/2026",
    duration_seconds: 734,
    duration_text: "12:14",
    reup_score: 42,
    estimated_views_display: "3.8K-19K",
    estimated_views_min: 3800,
    estimated_views_mid: 11400,
    estimated_views_max: 19000,
    like_count: 190,
    comment_count: 7,
    share_count: 5
  },
  source_video: {
    id: "video-bird",
    source_profile_id: "profile-1",
    source_video_external_id: "7621900000000000000",
    source_url: "https://www.douyin.com/video/7621900000000000000",
    caption: "190最聪明的鱼和最奇怪的鸟",
    posted_at: "2026-04-02T16:00:00Z",
    duration_seconds: 734,
    metadata_json: {}
  }
});
const birdMetadata = getReviewCandidateMetadata(birdCapture);
assert.equal(birdMetadata.caption, "190最聪明的鱼和最奇怪的鸟");
assert.equal(birdMetadata.postedDisplay, "23:00:00 2/4/2026");
assert.equal(birdMetadata.postedSource, "source_metadata.posted_display");
assert.notEqual(birdMetadata.postedDisplay, "03/04/2026");
assert.equal(birdMetadata.durationText, "12:14");
assert.equal(birdMetadata.reupScore, 42);
assert.equal(birdMetadata.estimatedViewsDisplay, "3.8K-19K");
assert.equal(birdMetadata.estimatedViewsMid, 11400);
assert.equal(birdMetadata.likeCount, 190);
assert.equal(birdMetadata.commentCount, 7);
assert.equal(birdMetadata.shareCount, 5);

const camelSourceMetadataBird = makeCandidate({
  posted_display: "03/04/2026",
  postedDisplay: "03/04/2026",
  sourceMetadata: {
    posted_display: "23:00:00 2/4/2026",
    posted_text_raw: "2/4/2026"
  }
} as Partial<Candidate> & { sourceMetadata: Record<string, unknown> });
assert.equal(getReviewCandidateMetadata(camelSourceMetadataBird).postedDisplay, "23:00:00 2/4/2026");
assert.equal(getReviewCandidateMetadata(camelSourceMetadataBird).postedSource, "source_metadata.posted_display");

const postedRawFallback = makeCandidate({
  source_metadata: { posted_text_raw: "23:00:00 2/4/2026" }
});
assert.equal(getReviewCandidateMetadata(postedRawFallback).postedDisplay, "23:00:00 2/4/2026");
assert.equal(getReviewCandidateMetadata(postedRawFallback).postedSource, "source_metadata.posted_text_raw");

const buffaloYakCapture = makeCandidate({
  posted_display: "03/05/2026",
  postedDisplay: "03/05/2026",
  metadata_json: { posted_display: "03/05/2026", posted_display_exact: "metadata-exact-stale" },
  source_metadata: {
    caption: "103麝牛 无法抵抗的命运",
    posted_at: "2026-05-03T02:40:00+00:00",
    posted_display_exact: "09:40:00 3/5/2026",
    posted_display: "09:40:00 3/5/2026",
    posted_text_raw: "1周前",
    duration_text: "10:37",
    reup_score: 43,
    estimated_views_display: "2.1K-10.3K",
    estimated_views_min: 2060,
    estimated_views_mid: 3399,
    estimated_views_max: 10300,
    like_count: 103,
    comment_count: 5,
    share_count: 11
  }
});
const buffaloYakMetadata = getReviewCandidateMetadata(buffaloYakCapture);
assert.equal(buffaloYakMetadata.postedDisplay, "09:40:00 3/5/2026");
assert.equal(buffaloYakMetadata.postedSource, "source_metadata.posted_display_exact");
assert.notEqual(buffaloYakMetadata.postedDisplay, "03/05/2026");
assert.equal(buffaloYakMetadata.reupScore, 43);
assert.equal(buffaloYakMetadata.estimatedViewsDisplay, "2.1K-10.3K");
assert.equal(buffaloYakMetadata.likeCount, 103);
assert.equal(buffaloYakMetadata.commentCount, 5);
assert.equal(buffaloYakMetadata.shareCount, 11);
assert.equal(buffaloYakMetadata.durationText, "10:37");

const postedAtFallback = makeCandidate({ posted_at: "2026-04-02T16:00:00Z" });
assert.equal(getReviewCandidateMetadata(postedAtFallback).postedDisplay, "2026-04-02T16:00:00Z");
assert.equal(getReviewCandidateMetadata(postedAtFallback).postedSource, "candidate.posted_at");

const durationSecondsFallback = makeCandidate({ source_metadata: { duration_seconds: 75 } });
const durationSecondsFallbackMetadata = getReviewCandidateMetadata(durationSecondsFallback);
assert.equal(durationSecondsFallbackMetadata.durationText, "1:15");
assert.equal(durationSecondsFallbackMetadata.durationSource, "source_metadata.duration_seconds");

const sourceEstimatedViews = makeCandidate(
  { estimated_views_display: null, metadata_json: { estimated_views_display: "candidate-metadata" } },
  { estimated_views_display: "source-metadata" }
);
assert.equal(getReviewCandidateMetadata(sourceEstimatedViews).estimatedViewsDisplay, "source-metadata");

const estimatedViewsRange = makeCandidate({
  estimated_views_display: null,
  estimated_views_min: 4100,
  estimated_views_max: 20300,
  views_display: "20.3K views"
});
const estimatedRangeMetadata = getReviewCandidateMetadata(estimatedViewsRange);
assert.equal(estimatedRangeMetadata.estimatedViewsDisplay, null);
assert.equal(estimatedRangeMetadata.estimatedViewsMin, 4100);
assert.equal(estimatedRangeMetadata.estimatedViewsMax, 20300);
assert.equal(estimatedRangeMetadata.estimatedViewsMid, 12200);

const legacyNestedMetadata = makeCandidate({
  score: 21.05,
  metadata_json: { operator_notes: "keep note" },
  source_video: {
    id: "video-legacy",
    source_profile_id: "profile-1",
    source_video_external_id: "legacy-aweme",
    source_url: "https://www.douyin.com/video/legacy-aweme",
    caption: "Legacy nested",
    posted_at: null,
    duration_seconds: null,
    metadata_json: {
      source_metadata: {
        reup_score: 42,
        estimated_views_display: "3.7K-18.3K",
        estimated_views_min: 3660,
        estimated_views_max: 18300,
        estimated_views_mid: 6039,
        duration_text: "13:37",
        duration_seconds: 817,
        thumbnail_url: "https://cdn.example.test/thumb.jpg",
        posted_display: "23:00:00 28/3/2026",
        like_count: 183,
        comment_count: 12,
        share_count: 13
      }
    }
  }
});
const legacyNested = getReviewCandidateMetadata(legacyNestedMetadata);
assert.equal(
  reviewCandidateDisplayScore(legacyNestedMetadata),
  getReupScoreForCaptureItem(buildCapturedItemFromReviewCandidate(legacyNestedMetadata)).reup_score
);
assert.equal(legacyNested.estimatedViewsDisplay, "3.7K-18.3K");
assert.equal(legacyNested.durationText, "13:37");
assert.equal(legacyNested.likeCount, 183);
assert.equal(legacyNested.commentCount, 12);
assert.equal(legacyNested.shareCount, 13);

console.log("review candidate metadata tests passed");

function makeCandidate(candidateFields: Partial<Candidate>, sourceMetadata: Record<string, unknown> = {}): Candidate {
  return {
    id: "candidate-1",
    source_video_id: "video-1",
    status: "SHORTLISTED",
    score: 55,
    score_version: "REUP_SCORE_V1",
    score_label: "usable",
    score_breakdown_json: {
      engagement_quality: {
        raw_input: { views: 0, likes: 0, comments: 0, shares: 0 },
        normalized_subscore: 0,
        weight: 0.22,
        weighted_contribution: 0
      }
    },
    score_reason: null,
    preset_name: null,
    filter_config_json: {},
    inclusion_reasons_json: [],
    exclusion_reasons_json: [],
    warnings_json: [],
    evaluated_at: null,
    priority: 55,
    metadata_json: {},
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    source_video: {
      id: "video-1",
      source_profile_id: "profile-1",
      source_video_external_id: "7420000000000000001",
      source_url: "https://www.douyin.com/video/7420000000000000001",
      caption: "Fixture",
      posted_at: null,
      duration_seconds: null,
      metadata_json: sourceMetadata
    },
    ...candidateFields
  };
}
