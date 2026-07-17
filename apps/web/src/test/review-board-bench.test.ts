import assert from "node:assert/strict";
import {
  addCandidateToBench,
  benchOccupiedIds,
  clearBench,
  createEmptyBench,
  pickBestBenchCandidateId,
  poolCandidatesForBench,
  removeBenchSlot,
  splitApproveBestTargets
} from "../lib/reviewBoardBenchState";
import type { Candidate } from "../types/review-board";

const candidateA = makeCandidate("a", 82);
const candidateB = makeCandidate("b", 48);
const candidateC = makeCandidate("c", 71);

let bench = createEmptyBench();
bench = addCandidateToBench(bench, "a", 0);
bench = addCandidateToBench(bench, "b", 1);
assert.deepEqual(bench, ["a", "b", null]);
assert.deepEqual(benchOccupiedIds(bench), ["a", "b"]);

bench = addCandidateToBench(bench, "c", 1);
assert.equal(bench[1], "c", "Replacing a slot must move the candidate into that slot");
assert.equal(bench[0], "a");

assert.equal(pickBestBenchCandidateId([candidateA, candidateB, candidateC], benchOccupiedIds(bench)), "a");

const pool = poolCandidatesForBench([candidateA, candidateB, candidateC], benchOccupiedIds(bench));
assert.deepEqual(pool.map((candidate) => candidate.id), ["b"]);

const split = splitApproveBestTargets(["a", "b", "c"], "a");
assert.deepEqual(split, { approveId: "a", rejectIds: ["b", "c"] });

bench = removeBenchSlot(bench, 0);
assert.deepEqual(bench, [null, "c", null]);
assert.deepEqual(clearBench(), [null, null, null]);

console.log("review-board-bench tests passed");

function makeCandidate(id: string, reupScore: number): Candidate {
  return {
    id,
    source_video_id: `video-${id}`,
    status: "SHORTLISTED",
    score: reupScore,
    reup_score: reupScore,
    score_version: "REUP_SCORE_V1",
    score_label: "usable",
    score_breakdown_json: null,
    score_reason: null,
    preset_name: null,
    filter_config_json: null,
    inclusion_reasons_json: null,
    exclusion_reasons_json: null,
    warnings_json: null,
    evaluated_at: null,
    priority: reupScore,
    metadata_json: null,
    created_at: "2026-04-10T00:00:00Z",
    updated_at: "2026-04-10T00:00:00Z",
    source_video: null
  };
}
