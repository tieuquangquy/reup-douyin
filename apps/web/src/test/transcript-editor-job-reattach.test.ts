import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import {
  isActiveTranscriptJobStatus,
  pickActiveTranscriptJob,
  transcriptJobKindFromType
} from "../lib/transcriptEditorJobReattach";
import type { Job } from "../types/jobs";

function job(partial: Partial<Job> & Pick<Job, "id" | "job_type" | "status">): Job {
  return {
    workspace_id: "ws",
    source_video_id: "sv",
    crawl_session_id: null,
    render_output_id: null,
    reference_type: null,
    reference_id: null,
    current_step_key: null,
    current_step_index: 0,
    progress_percent: 0,
    total_steps: 1,
    completed_steps: 0,
    failed_steps: 0,
    priority: 0,
    attempts: 0,
    max_attempts: 3,
    retryable: true,
    started_at: null,
    finished_at: null,
    error_code: null,
    error_message: null,
    created_at: "2026-07-20T01:00:00Z",
    updated_at: "2026-07-20T01:00:00Z",
    steps: [],
    ...partial
  };
}

assert.equal(transcriptJobKindFromType("SYNTHESIZE_TTS"), "tts");
assert.equal(transcriptJobKindFromType("BUILD_TRANSLATION_DRAFT"), "translate");
assert.equal(transcriptJobKindFromType("ANALYZE_AUDIO"), "reanalyze");
assert.equal(transcriptJobKindFromType("RENDER_FINAL"), null);

assert.equal(isActiveTranscriptJobStatus("RUNNING"), true);
assert.equal(isActiveTranscriptJobStatus("QUEUED"), true);
assert.equal(isActiveTranscriptJobStatus("COMPLETED"), false);

const picked = pickActiveTranscriptJob([
  job({
    id: "old-tts",
    job_type: "SYNTHESIZE_TTS",
    status: "RUNNING",
    created_at: "2026-07-20T01:00:00Z",
    updated_at: "2026-07-20T01:00:00Z"
  }),
  job({
    id: "new-tts",
    job_type: "SYNTHESIZE_TTS",
    status: "RUNNING",
    progress_percent: 40,
    created_at: "2026-07-20T02:00:00Z",
    updated_at: "2026-07-20T02:10:00Z"
  }),
  job({
    id: "done",
    job_type: "BUILD_TRANSLATION_DRAFT",
    status: "COMPLETED",
    created_at: "2026-07-20T03:00:00Z",
    updated_at: "2026-07-20T03:00:00Z"
  })
]);
assert.ok(picked);
assert.equal(picked?.id, "new-tts");
assert.equal(picked && transcriptJobKindFromType(picked.job_type), "tts");

assert.equal(pickActiveTranscriptJob([]), null);

const testDir = dirname(fileURLToPath(import.meta.url));
const pageSource = readFileSync(
  resolve(testDir, "../components/transcript-editor/TranscriptEditorPage.tsx"),
  "utf8"
);
const apiSource = readFileSync(resolve(testDir, "../lib/api.ts"), "utf8");

assert.match(pageSource, /resumeActiveTranscriptJob/, "Page must re-attach active transcript jobs after reload");
assert.match(apiSource, /source_video_id/, "fetchJobs must support source video filter for re-attach");

console.log("transcript-editor job reattach tests passed");
