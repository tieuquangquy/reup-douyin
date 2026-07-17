import assert from "node:assert/strict";
import { formatReviewEstimatedViews } from "../lib/reviewCandidateMetadata";
import type { ReviewCandidateMetadata } from "../lib/reviewCandidateMetadata";

function baseMetadata(overrides: Partial<ReviewCandidateMetadata> = {}): ReviewCandidateMetadata {
  return {
    captureItemId: null,
    captureSessionId: null,
    source: null,
    sourceModule: null,
    awemeId: null,
    sourceVideoExternalId: null,
    sourceUrl: null,
    videoUrl: null,
    profileUrl: null,
    profileName: null,
    caption: null,
    title: null,
    description: null,
    thumbnailUrl: null,
    postedDisplay: null,
    postedSource: "missing",
    postedText: null,
    postedTextRaw: null,
    durationSeconds: null,
    durationText: null,
    durationSource: "missing",
    viewCount: null,
    viewCountText: null,
    estimatedViewsDisplay: null,
    estimatedViewsMin: null,
    estimatedViewsMax: null,
    estimatedViewsMid: null,
    likeCount: null,
    likeCountText: null,
    commentCount: null,
    commentCountText: null,
    shareCount: null,
    shareCountText: null,
    favoriteCount: null,
    favoriteCountText: null,
    engagementRate: null,
    reupScore: null,
    reupScoreLabel: null,
    reupScoreLevel: null,
    missingMetadataFields: null,
    capture_item_id: null,
    capture_session_id: null,
    source_video_external_id: null,
    source_url: null,
    thumbnail_url: null,
    posted_display: null,
    posted_text: null,
    duration_text: null,
    view_count: null,
    view_count_text: null,
    estimated_views_display: null,
    estimated_views_mid: null,
    like_count: null,
    like_count_text: null,
    comment_count: null,
    comment_count_text: null,
    share_count: null,
    share_count_text: null,
    favorite_count: null,
    favorite_count_text: null,
    engagement_rate: null,
    reup_score: null,
    reup_score_label: null,
    reup_score_level: null,
    ...overrides
  };
}

assert.equal(formatReviewEstimatedViews(baseMetadata({ estimatedViewsDisplay: "6.6K-8.8K" })), "6.6K-8.8K");
assert.equal(formatReviewEstimatedViews(baseMetadata({ estimatedViewsMin: 6600, estimatedViewsMax: 8800 })), "6,600-8,800");
assert.match(formatReviewEstimatedViews(baseMetadata({ likeCount: 1646 })), /32\.9K-164\.6K|32,920-164,600/);
assert.equal(formatReviewEstimatedViews(baseMetadata()), "—");

console.log("review-candidate-estimated-views tests passed");
