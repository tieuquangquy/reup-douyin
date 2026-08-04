import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import {
  DEFAULT_FINAL_REVIEW_CHECKLIST,
  buildOriginalPreviewUrl,
  checklistComplete,
  findCurrentSourceVideoAsset,
  formatBytes,
  formatRenderDuration,
  formatResolution,
  getRenderWarnings,
  hasFinalReviewOcrRun,
  isApproved,
  isFinalReviewOcrPrepComplete,
  isFinalReviewOcrReviewPending,
  isPublishReady,
  nextCompareMode,
  resolveFinalReviewCompareDiff,
  resolveFinalReviewPrepBriefing,
  resolveFinalReviewPrepFocus,
  resolveFinalReviewPrepStepProgress,
  resolveFinalReviewReadiness,
  isReviewableFinalRender,
  resolveFinalReviewWorkspaceRender,
  formatFinalReviewFailedRenderDetail,
  resolveRenderTechSpecs
} from "../lib/finalReviewState";
import { loadFinalReviewChecklist, saveFinalReviewChecklist } from "../lib/finalReviewChecklistStorage";
import type { RenderOutput, SourceVideoAssetManifest } from "../types/final-review";

const testDir = dirname(fileURLToPath(import.meta.url));
const pageSource = readFileSync(resolve(testDir, "../components/final-review/FinalReviewPage.tsx"), "utf8");

const render = makeRender({
  status: "READY_FOR_REVIEW",
  warning_summary_json: { warnings: ["subtitle timing mismatch"] },
  metadata_json: { manifest: { warnings: ["long narration segment"] } }
});

assert.deepEqual(getRenderWarnings(render), ["subtitle timing mismatch", "long narration segment"]);
assert.equal(isApproved(render), false);
assert.equal(isPublishReady(render), false);

const approved = makeRender({
  status: "APPROVED",
  metadata_json: { final_review: { approved_at: "2026-04-17T00:00:00Z", publish_ready_at: "2026-04-17T00:01:00Z" } }
});
assert.equal(isApproved(approved), true);
assert.equal(isPublishReady(approved), true);

assert.equal(nextCompareMode("side_by_side"), "final_only");
assert.equal(nextCompareMode("final_only"), "original_only");
assert.equal(nextCompareMode("original_only"), "side_by_side");

const manifest: SourceVideoAssetManifest = {
  source_video: { id: "video-1", source_url: "https://example.test/source.mp4" },
  assets: [
    { id: "old", asset_type: "SOURCE_VIDEO_RAW", status: "AVAILABLE", version: 1, storage_key: "old.mp4", is_current: false },
    { id: "raw", asset_type: "SOURCE_VIDEO_RAW", status: "AVAILABLE", version: 2, storage_key: "raw.mp4", is_current: true }
  ]
};
assert.equal(findCurrentSourceVideoAsset(manifest)?.id, "raw");
assert.equal(buildOriginalPreviewUrl(manifest, (id) => `/media/${id}`), "/media/raw");

assert.equal(
  checklistComplete({
    narration_clear: true,
    subtitle_ok: true,
    timing_ok: true,
    render_clean: true,
    playable: true,
    warnings_checked: true
  }),
  true
);
assert.deepEqual(DEFAULT_FINAL_REVIEW_CHECKLIST.narration_clear, false);
assert.equal(formatRenderDuration(72.4), "1:12");
assert.equal(formatRenderDuration(null), "—");

const sparse = makeRender({
  width: null,
  height: null,
  fps: null,
  duration_seconds: null,
  metadata_json: {
    manifest: {
      probe: {
        output: { width: 1080, height: 1920, fps: 30, duration_seconds: 45 }
      },
      output: { size_bytes: 2_500_000 },
      job_id: "job-9"
    },
    final_review: { approved_at: "2026-04-17T00:00:00Z" }
  }
});
const specs = resolveRenderTechSpecs(sparse, {
  source_video: { id: "video-1", duration_seconds: 99 }
});
assert.equal(formatResolution(specs.width, specs.height), "1080×1920");
assert.equal(specs.fps, 30);
assert.equal(specs.duration_seconds, 45);
assert.equal(formatBytes(specs.size_bytes), "2.4 MB");
assert.equal(specs.job_id, "job-9");
assert.equal(specs.approved_at, "2026-04-17T00:00:00Z");
assert.equal(specs.publish_ready_at, null);

const fromAssets = makeRender({
  media_asset_id: "final-asset",
  created_by_job_id: null,
  size_bytes: null,
  metadata_json: { manifest: { output: {}, job_id: null } }
});
const assetSpecs = resolveRenderTechSpecs(fromAssets, {
  source_video: { id: "video-1" },
  assets: [
    {
      id: "final-asset",
      asset_type: "FINAL_RENDER_VIDEO",
      status: "AVAILABLE",
      version: 9,
      storage_key: "renders/final.mp4",
      size_bytes: 4_194_304,
      created_by_job_id: "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    }
  ]
});
assert.equal(formatBytes(assetSpecs.size_bytes), "4.0 MB");
assert.equal(assetSpecs.job_id, "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee");

assert.equal(isFinalReviewOcrPrepComplete(null), false);
assert.equal(resolveFinalReviewPrepFocus(null), "ocr");
assert.equal(
  hasFinalReviewOcrRun(null),
  false,
  "null summary must not count as a prior OCR run"
);
assert.equal(
  hasFinalReviewOcrRun({
    cleaned_video_asset_id: null,
    ocr_events_asset_id: null,
    pipeline_version: null,
    text_object_count: 0,
    frame_detection_count: 0,
    hardsub_events: [],
    warnings: []
  }),
  false,
  "empty API OCR summary shell (never analyzed) must not count as a prior run"
);
assert.equal(
  hasFinalReviewOcrRun({ ocr_events_asset_id: "ocr-1" }),
  true,
  "OCR events asset means a prior run"
);
assert.equal(
  hasFinalReviewOcrRun({ cleaned_video_asset_id: "clean-1" }),
  true,
  "cleaned video asset means a prior run"
);
assert.equal(
  hasFinalReviewOcrRun({ pipeline_version: "v1", hardsub_events: [] }),
  true,
  "pipeline_version means a prior run even with zero events"
);
assert.equal(
  hasFinalReviewOcrRun({ frame_detection_count: 3 }),
  true,
  "frame detections mean a prior run"
);
assert.equal(isFinalReviewOcrReviewPending(null), false);
assert.equal(
  isFinalReviewOcrReviewPending({
    workflow_stage: "WAITING_OCR_REVIEW",
    review_required: 10,
    review_objects: []
  }),
  true,
  "completed OCR with required decisions must be modeled as an operator checkpoint"
);
assert.equal(
  isFinalReviewOcrReviewPending({
    workflow_stage: "WAITING_VISUAL_REVIEW",
    review_required: 10,
    review_objects: []
  }),
  false,
  "review count alone must not reopen an old OCR checkpoint after the workflow advances"
);
assert.equal(isFinalReviewOcrPrepComplete({ cleaned_video_asset_id: null, ocr_events_asset_id: null, warnings: [] }), false);
assert.equal(
  isFinalReviewOcrPrepComplete({ cleaned_video_asset_id: null, ocr_events_asset_id: "ocr-1", warnings: [] }),
  false,
  "orphan OCR events without cleaned video or skip warning must not mark OCR prep complete"
);
assert.equal(
  isFinalReviewOcrPrepComplete({ cleaned_video_asset_id: null, ocr_events_asset_id: "ocr-1", clean_produced: false, warnings: [] }),
  false,
  "clean_produced=false alone must not mark OCR prep complete"
);
assert.equal(
  isFinalReviewOcrPrepComplete({ cleaned_video_asset_id: "clean-1", ocr_events_asset_id: null, warnings: [] }),
  true
);
assert.equal(
  isFinalReviewOcrPrepComplete({
    cleaned_video_asset_id: null,
    ocr_events_asset_id: "ocr-1",
    warnings: ["no_hardsub_detected"]
  }),
  true
);
assert.equal(resolveFinalReviewPrepFocus({ cleaned_video_asset_id: "clean-1" }), "render");
assert.equal(resolveFinalReviewPrepFocus({ cleaned_video_asset_id: null, ocr_events_asset_id: "ocr-1" }), "ocr");
assert.equal(
  isFinalReviewOcrPrepComplete({
    workflow_version: "QUALITY_LOCALIZATION_V24_1",
    workflow_stage: "WAITING_VISUAL_REVIEW",
    can_render_final: false,
    cleaned_video_asset_id: "preview-1"
  }),
  false,
  "Quality preview must remain locked until visual approval"
);
assert.equal(
  isFinalReviewOcrPrepComplete({
    workflow_version: "QUALITY_LOCALIZATION_V24_1",
    workflow_stage: "VISUAL_APPROVED",
    can_render_final: true
  }),
  true
);
assert.equal(
  isFinalReviewOcrPrepComplete({
    workflow_version: "QUALITY_LOCALIZATION_V24_1",
    workflow_stage: "FINAL_READY",
    can_render_final: true
  }),
  true
);

assert.equal(isReviewableFinalRender(null), false);
assert.equal(isReviewableFinalRender(makeRender({ status: "FAILED", media_asset_id: null })), false);
assert.equal(
  isReviewableFinalRender(makeRender({ status: "FAILED", media_asset_id: "orphan-final" })),
  false,
  "FAILED latest render must not open compare/review workspace after refresh"
);
assert.equal(isReviewableFinalRender(makeRender({ status: "READY_FOR_REVIEW" })), true);
assert.equal(isReviewableFinalRender(makeRender({ status: "APPROVED" })), true);
assert.equal(isReviewableFinalRender(makeRender({ status: "RENDERING" })), true);
assert.equal(
  resolveFinalReviewWorkspaceRender(makeRender({ status: "FAILED", error_message: "missing_render_prep_manifest: Current render-prep manifest is missing" })),
  null,
  "Workspace gate must treat FAILED latest-render as prep (no final yet)"
);
assert.equal(
  resolveFinalReviewWorkspaceRender(makeRender({ status: "READY_FOR_REVIEW" }))?.status,
  "READY_FOR_REVIEW"
);
assert.equal(
  formatFinalReviewFailedRenderDetail("missing_render_prep_manifest: Current render-prep manifest is missing"),
  "Current render-prep manifest is missing"
);
assert.equal(formatFinalReviewFailedRenderDetail(null), null);
assert.match(
  pageSource,
  /isReviewableFinalRender|resolveFinalReviewWorkspaceRender/,
  "Final Review load must gate workspace on reviewable render, not raw latest-render including FAILED"
);

assert.deepEqual(
  resolveFinalReviewPrepStepProgress({ ocrSummary: null }),
  { clean: 0, render: 0, compare: 0 },
  "Idle prep steps start at 0%"
);
assert.deepEqual(
  resolveFinalReviewPrepStepProgress({ ocrSummary: { ocr_events_asset_id: "ocr-partial" } }),
  { clean: 0, render: 0, compare: 0 },
  "Incomplete OCR summary must stay at 0% Clean until a live job percent or completion (not a fake 25%)"
);
assert.deepEqual(
  resolveFinalReviewPrepStepProgress({ ocrSummary: null, ocrBusy: true }),
  { clean: 8, render: 0, compare: 0 },
  "OCR running without job percent must show a low in-flight Clean fill (not a fake 50%)"
);
assert.deepEqual(
  resolveFinalReviewPrepStepProgress({
    ocrSummary: null,
    ocrBusy: true,
    ocrProgressPercent: 42
  }),
  { clean: 42, render: 0, compare: 0 },
  "OCR running must mirror job.progress_percent on Clean"
);
assert.deepEqual(
  resolveFinalReviewPrepStepProgress({
    ocrSummary: { ocr_events_asset_id: "ocr-partial" },
    ocrBusy: false,
    ocrProgressPercent: 68
  }),
  { clean: 68, render: 0, compare: 0 },
  "UI-paused OCR must keep last job.progress_percent (not drop to idle 0%)"
);
assert.deepEqual(
  resolveFinalReviewPrepStepProgress({ ocrSummary: { cleaned_video_asset_id: "clean-1" } }),
  { clean: 100, render: 0, compare: 0 },
  "Completed OCR prep should fill Clean to 100%"
);
assert.deepEqual(
  resolveFinalReviewPrepStepProgress({
    ocrSummary: { cleaned_video_asset_id: "clean-1" },
    startRenderPending: true,
    renderProgressPercent: 67
  }),
  { clean: 100, render: 67, compare: 0 },
  "Start-render pending must mirror job.progress_percent on Render"
);
assert.deepEqual(
  resolveFinalReviewPrepStepProgress({
    ocrSummary: { cleaned_video_asset_id: "clean-1" },
    startRenderPending: false,
    renderProgressPercent: 78
  }),
  { clean: 100, render: 78, compare: 0 },
  "UI-paused render must keep last job.progress_percent (not drop to 0%)"
);
assert.match(
  pageSource,
  /ocrProgressPercent|onSnapshot[\s\S]{0,120}progress_percent/,
  "Final Review must feed live job progress into prep step percents while polling"
);
assert.doesNotMatch(
  pageSource,
  /analyzeBusy=\{ocrBusy\s*\|\|\s*ocrWatchPaused\}|analyzeBusy=\{ocrInFlight\}/,
  "Watch-paused must not drive Analyze pending spinner (strip owns Resume/Cancel)"
);
assert.match(
  pageSource,
  /ocrWatchPaused/,
  "Page must keep watch-paused state for Quiet Paused CTA / strip controls"
);
assert.match(
  pageSource,
  /renderWatchPausedRef|pauseRenderWatch|resumeRenderWatch/,
  "Render Pause must stop UI polling without cancelling the job"
);
assert.match(
  pageSource,
  /cancelRenderJob|cancelJob\(renderJobId|cancelJob\(jobId\)/,
  "Render Cancel must call cancelJob on the in-flight RENDER_FINAL job"
);

assert.equal(
  resolveFinalReviewPrepBriefing({
    sourceVideoId: "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
    manifest: null,
    ocrSummary: null,
    ocrBusy: false,
    startRenderPending: false,
    prepFocus: "ocr"
  }).phase,
  "clean",
  "Prep briefing phase follows OCR focus"
);
assert.equal(
  resolveFinalReviewPrepBriefing({
    sourceVideoId: "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
    manifest: {
      source_video: { id: "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee", caption: "Cooking clip", duration_seconds: 65 }
    },
    ocrSummary: null,
    ocrBusy: false,
    startRenderPending: false,
    prepFocus: "ocr"
  }).caption,
  "Cooking clip"
);
assert.equal(
  resolveFinalReviewPrepBriefing({
    sourceVideoId: "sv-1",
    manifest: null,
    ocrSummary: null,
    ocrBusy: true,
    startRenderPending: false,
    prepFocus: "ocr"
  }).ocrStatus,
  "running"
);
assert.equal(
  resolveFinalReviewPrepBriefing({
    sourceVideoId: "sv-1",
    manifest: null,
    ocrSummary: {
      workflow_stage: "WAITING_OCR_REVIEW",
      review_required: 10,
      review_objects: [{}]
    },
    ocrBusy: false,
    startRenderPending: false,
    prepFocus: "ocr"
  }).ocrStatus,
  "review",
  "a completed OCR job awaiting decisions must say Needs review, not In progress"
);
assert.equal(
  resolveFinalReviewPrepBriefing({
    sourceVideoId: "sv-1",
    manifest: null,
    ocrSummary: { cleaned_video_asset_id: "clean-1" },
    ocrBusy: false,
    startRenderPending: false,
    prepFocus: "render"
  }).ocrStatus,
  "ready"
);
assert.equal(
  resolveFinalReviewPrepBriefing({
    sourceVideoId: "sv-1",
    manifest: null,
    ocrSummary: { cleaned_video_asset_id: "clean-1" },
    ocrBusy: false,
    startRenderPending: true,
    prepFocus: "render"
  }).renderStatus,
  "running"
);

const readyChecklist = {
  narration_clear: true,
  subtitle_ok: true,
  timing_ok: true,
  render_clean: true,
  playable: true,
  warnings_checked: true
};
const readyReadiness = resolveFinalReviewReadiness({
  checklist: readyChecklist,
  render: makeRender({ status: "APPROVED", metadata_json: { final_review: { publish_ready_at: "2026-01-01T00:00:00Z" } } }),
  riskSummary: { gate: { can_continue: true, requires_operator_decision: false }, latest_decision: { id: "d1" } }
});
assert.equal(readyReadiness.publishReady, true);
assert.deepEqual(readyReadiness.blockers, []);

const blockedReadiness = resolveFinalReviewReadiness({
  checklist: DEFAULT_FINAL_REVIEW_CHECKLIST,
  render: makeRender({ status: "READY_FOR_REVIEW" }),
  riskSummary: { gate: { can_continue: false, requires_operator_decision: true }, latest_decision: null }
});
assert.ok(blockedReadiness.blockers.includes("checklist"));
assert.ok(blockedReadiness.blockers.includes("approve"));
assert.ok(blockedReadiness.blockers.includes("risk"));

const compareDiff = resolveFinalReviewCompareDiff(
  makeRender({ duration_seconds: 62, subtitle_burned: true, width: 1080, height: 1920, size_bytes: 2_000_000 }),
  { source_video: { id: "sv-1", duration_seconds: 60 } }
);
assert.equal(compareDiff.durationDeltaSeconds, 2);
assert.equal(compareDiff.subtitleBurned, true);
assert.equal(compareDiff.resolution, "1080×1920");

{
  const memory = new Map<string, string>();
  const original = globalThis.localStorage;
  Object.defineProperty(globalThis, "localStorage", {
    configurable: true,
    value: {
      getItem: (key: string) => memory.get(key) ?? null,
      setItem: (key: string, value: string) => {
        memory.set(key, value);
      },
      removeItem: (key: string) => {
        memory.delete(key);
      }
    }
  });
  try {
    saveFinalReviewChecklist("render-persist", readyChecklist);
    assert.deepEqual(loadFinalReviewChecklist("render-persist"), readyChecklist);
    assert.equal(loadFinalReviewChecklist("missing-render"), null);
  } finally {
    Object.defineProperty(globalThis, "localStorage", { configurable: true, value: original });
  }
}

console.log("final-review state tests passed");

function makeRender(patch: Partial<RenderOutput>): RenderOutput {
  return {
    id: "render-1",
    workspace_id: "workspace-1",
    source_video_id: "video-1",
    media_asset_id: "asset-1",
    status: "READY_FOR_REVIEW",
    target_platform: "generic",
    version: 1,
    render_type: "final",
    output_format: "mp4",
    width: 1080,
    height: 1920,
    fps: 30,
    duration_seconds: 72.4,
    video_codec: "h264",
    audio_codec: "aac",
    subtitle_burned: true,
    audio_strategy: "replace_with_vietnamese_narration",
    render_version: "RENDER_V1_RUN_1",
    created_by_job_id: null,
    size_bytes: null,
    warning_summary_json: null,
    render_settings_json: {},
    metadata_json: {},
    error_message: null,
    started_at: "2026-04-17T00:00:00Z",
    finished_at: "2026-04-17T00:02:00Z",
    created_at: "2026-04-17T00:00:00Z",
    updated_at: "2026-04-17T00:02:00Z",
    ...patch
  };
}
