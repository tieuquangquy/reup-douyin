import assert from "node:assert/strict";
import {
  candidateMatchesReviewBoardSearch,
  DEFAULT_FILTERS,
  effectiveReviewStatusFilter,
  filterCandidatesForSearch,
  visibleCandidates
} from "../lib/reviewBoardState";
import type { Candidate } from "../types/review-board";

function makeCandidate(overrides: Partial<Candidate> = {}): Candidate {
  return {
    id: "cand-11111111-1111-1111-1111-111111111111",
    source_video_id: "video-1",
    status: "SHORTLISTED",
    score: 80,
    score_version: null,
    score_label: null,
    score_breakdown_json: null,
    score_reason: null,
    preset_name: null,
    filter_config_json: null,
    inclusion_reasons_json: null,
    exclusion_reasons_json: null,
    warnings_json: null,
    evaluated_at: null,
    priority: 80,
    metadata_json: null,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    source_video: {
      id: "video-1",
      source_profile_id: "profile-1",
      source_video_external_id: "7628281732369796388",
      source_url: "https://www.douyin.com/video/7628281732369796388",
      caption: "Fixture caption",
      posted_at: "2026-01-01T00:00:00Z",
      duration_seconds: 30,
      metadata_json: null
    },
    aweme_id: "7628281732369796388",
    source_video_external_id: "7628281732369796388",
    caption: "Fixture caption",
    ...overrides
  };
}

const candidate = makeCandidate();
assert.equal(filterCandidatesForSearch([candidate], "7628281732369796388").length, 1, "Search must match summary aweme/video id");
assert.equal(filterCandidatesForSearch([candidate], "cand-11111111").length, 1, "Search must match candidate id");
assert.equal(
  filterCandidatesForSearch([makeCandidate({ source_video: null, aweme_id: "7631223404342857006", source_video_external_id: "7631223404342857006" })], "7631223404342857006").length,
  1,
  "Search must match top-level external id without nested source_video"
);
assert.equal(effectiveReviewStatusFilter({ ...DEFAULT_FILTERS, search: "7628281732369796388" }), "", "Active search should ignore status tab filter");

const metadataCaptionCandidate = makeCandidate({
  caption: null,
  source_video: {
    id: "video-1",
    source_profile_id: "profile-1",
    source_video_external_id: "7628281732369796388",
    source_url: "https://www.douyin.com/video/7628281732369796388",
    caption: null,
    posted_at: "2026-01-01T00:00:00Z",
    duration_seconds: 30,
    metadata_json: { caption: "Hidden metadata caption phrase" }
  },
  metadata_json: { profile_name: "Chef Minh Kitchen" }
});
assert.equal(
  candidateMatchesReviewBoardSearch(metadataCaptionCandidate, "Hidden metadata caption"),
  true,
  "Search must match caption stored in source_video metadata_json"
);
assert.equal(
  candidateMatchesReviewBoardSearch(metadataCaptionCandidate, "Chef Minh"),
  true,
  "Search must match profile_name in candidate metadata_json"
);

const serverResult = makeCandidate({
  id: "server-only-id",
  caption: "API matched this",
  source_video_external_id: "999",
  aweme_id: "999"
});
const visibleWithServerSearch = visibleCandidates([serverResult], { ...DEFAULT_FILTERS, search: "API matched" }, { serverSearch: true });
assert.equal(visibleWithServerSearch.length, 1, "Server search must not re-filter API results client-side");
const visibleWithoutServerSearch = visibleCandidates(
  [makeCandidate({ caption: "different", source_video_external_id: "888", aweme_id: "888" })],
  { ...DEFAULT_FILTERS, search: "API matched" },
  { serverSearch: false }
);
assert.equal(visibleWithoutServerSearch.length, 0, "Client search must still filter when server search is off");

console.log("review-board-search tests passed");
