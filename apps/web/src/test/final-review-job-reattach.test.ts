import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import {
  isActiveFinalReviewJobStatus,
  isOcrJobType,
  isRenderJobType,
  isVisualCleanJobType,
  pickActiveOcrJob,
  pickActiveRenderJob,
  pickActiveVisualCleanJob
} from "../lib/finalReviewJobReattach";
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

assert.equal(isOcrJobType("ANALYZE_OCR"), true);
assert.equal(isOcrJobType("RENDER_PREVIEW"), false);
assert.equal(isOcrJobType("RENDER_FINAL"), false);
assert.equal(isOcrJobType("ANALYZE_AUDIO"), false);
assert.equal(isRenderJobType("RENDER_FINAL"), true);
assert.equal(isRenderJobType("ANALYZE_OCR"), false);
assert.equal(isVisualCleanJobType("RENDER_PREVIEW"), true);
assert.equal(isVisualCleanJobType("ANALYZE_OCR"), false);

assert.equal(isActiveFinalReviewJobStatus("RUNNING"), true);
assert.equal(isActiveFinalReviewJobStatus("QUEUED"), true);
assert.equal(isActiveFinalReviewJobStatus("COMPLETED"), false);

const picked = pickActiveOcrJob([
  job({
    id: "old-ocr",
    job_type: "ANALYZE_OCR",
    status: "RUNNING",
    created_at: "2026-07-20T01:00:00Z",
    updated_at: "2026-07-20T01:00:00Z"
  }),
  job({
    id: "new-ocr",
    job_type: "ANALYZE_OCR",
    status: "RUNNING",
    progress_percent: 20,
    created_at: "2026-07-20T02:00:00Z",
    updated_at: "2026-07-20T02:10:00Z"
  }),
  job({
    id: "render",
    job_type: "RENDER_FINAL",
    status: "RUNNING",
    created_at: "2026-07-20T03:00:00Z",
    updated_at: "2026-07-20T03:00:00Z"
  }),
  job({
    id: "done",
    job_type: "ANALYZE_OCR",
    status: "COMPLETED",
    created_at: "2026-07-20T04:00:00Z",
    updated_at: "2026-07-20T04:00:00Z"
  })
]);
assert.ok(picked);
assert.equal(picked?.id, "new-ocr");

const pickedPreview = pickActiveVisualCleanJob([
  job({
    id: "quality-preview",
    job_type: "RENDER_PREVIEW",
    status: "RUNNING",
    created_at: "2026-07-20T02:20:00Z",
    updated_at: "2026-07-20T02:21:00Z"
  })
]);
assert.equal(pickedPreview?.id, "quality-preview");
assert.equal(
  pickActiveOcrJob([
    job({ id: "quality-preview", job_type: "RENDER_PREVIEW", status: "RUNNING" })
  ]),
  null
);

assert.equal(pickActiveOcrJob([]), null);
assert.equal(
  pickActiveOcrJob([
    job({ id: "tts", job_type: "SYNTHESIZE_TTS", status: "RUNNING" }),
    job({ id: "done-ocr", job_type: "ANALYZE_OCR", status: "FAILED" })
  ]),
  null
);

const pickedRender = pickActiveRenderJob([
  job({
    id: "old-render",
    job_type: "RENDER_FINAL",
    status: "RUNNING",
    created_at: "2026-07-20T01:00:00Z",
    updated_at: "2026-07-20T01:00:00Z"
  }),
  job({
    id: "new-render",
    job_type: "RENDER_FINAL",
    status: "QUEUED",
    created_at: "2026-07-20T02:00:00Z",
    updated_at: "2026-07-20T02:05:00Z"
  }),
  job({
    id: "ocr-noise",
    job_type: "ANALYZE_OCR",
    status: "RUNNING",
    created_at: "2026-07-20T03:00:00Z",
    updated_at: "2026-07-20T03:00:00Z"
  }),
  job({
    id: "done-render",
    job_type: "RENDER_FINAL",
    status: "COMPLETED",
    created_at: "2026-07-20T04:00:00Z",
    updated_at: "2026-07-20T04:00:00Z"
  })
]);
assert.ok(pickedRender);
assert.equal(pickedRender?.id, "new-render");
assert.equal(pickActiveRenderJob([]), null);
assert.equal(
  pickActiveRenderJob([job({ id: "ocr-only", job_type: "ANALYZE_OCR", status: "RUNNING" })]),
  null
);

const testDir = dirname(fileURLToPath(import.meta.url));
const pageSource = readFileSync(resolve(testDir, "../components/final-review/FinalReviewPage.tsx"), "utf8");
assert.match(pageSource, /resumeActiveOcrJob/, "Page must re-attach active OCR jobs after reload");
assert.match(pageSource, /pickActiveOcrJob/, "Page must pick the newest in-flight ANALYZE_OCR job");
assert.match(
  pageSource,
  /pickActiveVisualCleanJob/,
  "Page must identify RENDER_PREVIEW as a distinct Visual Clean job"
);
assert.match(
  pageSource,
  /visualCleanInProgress/,
  "RENDER_PREVIEW must not be labeled as Analyze OCR"
);
assert.match(pageSource, /resumeActiveRenderJob/, "Page must re-attach active RENDER_FINAL jobs after reload");
assert.match(pageSource, /pickActiveRenderJob/, "Page must pick the newest in-flight RENDER_FINAL job");
assert.match(pageSource, /fetchJobs/, "Job re-attach must load jobs from the jobs API authority");
assert.match(pageSource, /jobType:\s*["']RENDER_PREVIEW["']/, "Quality review re-attach must query preview jobs");
assert.match(
  pageSource,
  /jobType:\s*[\"']RENDER_FINAL[\"']/,
  "Render re-attach must query RENDER_FINAL jobs for the source video"
);
assert.match(
  pageSource,
  /const \[renderBusy,\s*setRenderBusy\]\s*=\s*useState\(false\)/,
  "Render in-flight must use durable React busy state (like ocrBusy), not only asyncAction pending"
);
assert.match(
  pageSource,
  /resumeActiveRenderJob[\s\S]{0,500}setRenderBusy\(true\)/,
  "Render re-attach must turn on Rerender loading spinner"
);
assert.match(
  pageSource,
  /rerenderPending=\{[^}]*renderBusy/,
  "Header Rerender pending must follow durable renderBusy after F5/reopen"
);

console.log("final-review job reattach tests passed");
