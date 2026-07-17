import assert from "node:assert/strict";
import {
  allVisibleSelected,
  selectedVisibleIds,
  selectAllOnPage,
  toggleSelectAllVisible,
  toggleSelection
} from "../lib/reviewBoardState";
import type { Candidate } from "../types/review-board";

const visible = [makeCandidate("a"), makeCandidate("b"), makeCandidate("c")];

let selected = toggleSelection(new Set(), "a");
assert.deepEqual([...selected], ["a"]);
selected = toggleSelectAllVisible(visible, selected);
assert.equal(allVisibleSelected(visible, selected), true);
selected = toggleSelectAllVisible(visible, selected);
assert.equal(selected.size, 0);
selected = selectAllOnPage(visible);
assert.deepEqual(selectedVisibleIds(visible, selected).sort(), ["a", "b", "c"]);
selected = toggleSelection(selected, "b");
assert.deepEqual(selectedVisibleIds(visible, selected).sort(), ["a", "c"]);

console.log("review-board-bulk tests passed");

function makeCandidate(id: string): Candidate {
  return {
    id,
    source_video_id: `video-${id}`,
    status: "SHORTLISTED",
    score: 50,
    reup_score: 50,
    estimated_views_mid: 1000,
    score_version: "REUP_SCORE_V1",
    score_label: "usable",
    score_breakdown_json: null,
    score_reason: null,
    preset_name: "viral_discovery",
    filter_config_json: {},
    inclusion_reasons_json: [],
    exclusion_reasons_json: [],
    warnings_json: [],
    evaluated_at: "2026-04-01T00:00:00Z",
    priority: 50,
    metadata_json: {},
    created_at: "2026-04-01T00:00:00Z",
    updated_at: "2026-04-01T00:00:00Z",
    source_video: null
  };
}
