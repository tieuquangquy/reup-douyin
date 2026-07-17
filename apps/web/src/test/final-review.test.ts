import assert from "node:assert/strict";
import {
  DEFAULT_FINAL_REVIEW_CHECKLIST,
  buildOriginalPreviewUrl,
  checklistComplete,
  findCurrentSourceVideoAsset,
  formatRenderDuration,
  getRenderWarnings,
  isApproved,
  isPublishReady,
  nextCompareMode
} from "../lib/finalReviewState";
import type { RenderOutput, SourceVideoAssetManifest } from "../types/final-review";

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
assert.equal(buildOriginalPreviewUrl(manifest, (assetId) => `/media-assets/${assetId}/content`), "/media-assets/raw/content");

assert.equal(checklistComplete(DEFAULT_FINAL_REVIEW_CHECKLIST), false);
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
assert.equal(formatRenderDuration(72.4), "1:12");

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
