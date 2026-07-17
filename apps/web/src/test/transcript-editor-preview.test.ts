import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import {
  isDirectMediaPreviewUrl,
  resolveTranscriptPreviewSource,
  resolveTranscriptPreviewUrl
} from "../lib/transcriptEditorPresentation";
import type { AssetManifest } from "../types/transcript-editor";

const toContentUrl = (assetId: string) => `http://api.test/media-assets/${assetId}/content`;

const withRaw: AssetManifest = {
  source_video: {
    id: "video-1",
    external_id: "aweme-1",
    source_url: "https://www.douyin.com/video/123",
    caption: null,
    duration_seconds: 42
  },
  assets: [
    {
      id: "old-raw",
      asset_type: "SOURCE_VIDEO_RAW",
      status: "AVAILABLE",
      logical_key: null,
      source_url: null,
      mime_type: "video/mp4",
      is_current: false
    },
    {
      id: "raw-2",
      asset_type: "SOURCE_VIDEO_RAW",
      status: "AVAILABLE",
      logical_key: null,
      source_url: null,
      mime_type: "video/mp4",
      is_current: true
    }
  ]
};

assert.deepEqual(
  resolveTranscriptPreviewSource(withRaw),
  { kind: "media_asset", assetId: "raw-2" },
  "Preview source must prefer current SOURCE_VIDEO_RAW asset id"
);

assert.equal(
  resolveTranscriptPreviewUrl(withRaw, toContentUrl),
  "http://api.test/media-assets/raw-2/content",
  "Preview URL helper must map asset id to media-asset content path"
);

const douyinOnly: AssetManifest = {
  source_video: {
    id: "video-2",
    external_id: "aweme-2",
    source_url: "https://www.douyin.com/video/999",
    caption: null,
    duration_seconds: 10
  },
  assets: []
};

assert.equal(resolveTranscriptPreviewSource(douyinOnly), null, "Douyin page URLs must not be bound to <video>");
assert.equal(resolveTranscriptPreviewUrl(douyinOnly, toContentUrl), null, "Douyin page URLs must resolve to null");

assert.equal(isDirectMediaPreviewUrl("https://cdn.example.com/clip.mp4"), true);
assert.equal(isDirectMediaPreviewUrl("https://www.douyin.com/video/1"), false);
assert.equal(isDirectMediaPreviewUrl("https://v.douyin.com/abc"), false);

const directFallback: AssetManifest = {
  source_video: {
    id: "video-3",
    external_id: "x",
    source_url: "https://cdn.example.com/source.mp4?token=1",
    caption: null,
    duration_seconds: 5
  },
  assets: []
};

assert.deepEqual(resolveTranscriptPreviewSource(directFallback), {
  kind: "direct",
  url: "https://cdn.example.com/source.mp4?token=1"
});

const testDir = dirname(fileURLToPath(import.meta.url));
const previewSource = readFileSync(resolve(testDir, "../components/transcript-editor/TranscriptMediaPreview.tsx"), "utf8");
const apiSource = readFileSync(resolve(testDir, "../lib/api.ts"), "utf8");

assert.match(previewSource, /resolveTranscriptPreviewSource/, "Media preview must resolve auth-aware preview source");
assert.match(previewSource, /fetchMediaAssetObjectUrl/, "Media preview must fetch protected media with Bearer → blob URL");
assert.match(previewSource, /revokeObjectURL/, "Media preview must revoke blob URLs on cleanup");
assert.match(previewSource, /joinedTtsAssetId/, "Media preview must support joined TTS playback");
assert.match(previewSource, /<audio controls/, "Joined TTS must use compact audio controls");
assert.match(apiSource, /export async function fetchMediaAssetObjectUrl/, "API helper must fetch media assets with auth");
assert.match(apiSource, /export async function createTtsJob/, "API helper must create TTS jobs");
assert.doesNotMatch(
  previewSource,
  /summary\?\.manifest\.source_video\?\.source_url/,
  "Media preview must not bind Douyin catalog source_url directly"
);
assert.doesNotMatch(
  previewSource,
  /src=\{previewUrl\}/,
  "Media preview must not put protected /media-assets URL directly on <video src>"
);
assert.match(previewSource, /loadedmetadata|readyState/, "Play/Jump must wait until video metadata is ready");

console.log("transcript-editor preview tests passed");
