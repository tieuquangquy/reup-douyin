/**
 * The default one-click path must produce a finished video.
 * Primary CTA runs auto_to_render; stopping after TTS is the explicit opt-out.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const testDir = dirname(fileURLToPath(import.meta.url));
const webSrc = resolve(testDir, "..");
const pageSource = readFileSync(resolve(webSrc, "components/reup-queue/ReupQueuePage.tsx"), "utf8");

const primaryHandler = pageSource.slice(
  pageSource.indexOf("onStartAutoReady={"),
  pageSource.indexOf("onStartAutoTtsOnlyReady={")
);
assert.ok(primaryHandler.length > 0, "Primary auto handler must precede the TTS-only handler");
assert.match(
  primaryHandler,
  /pipelineMode: "auto_to_render"/,
  "Primary Start auto must run the full chain through render"
);

const ttsOnlyHandler = pageSource.slice(
  pageSource.indexOf("onStartAutoTtsOnlyReady={"),
  pageSource.indexOf("onStartReady={")
);
assert.match(
  ttsOnlyHandler,
  /pipelineMode: "auto_to_tts"/,
  "The opt-out CTA must stop the pipeline after TTS"
);

// The bulk bar carries the same label, so it must carry the same stop point. Without an
// explicit mode the API falls back to auto_to_tts and the batch quietly stops early.
const bulkAutoOption = pageSource.slice(
  pageSource.indexOf('key: "START_AUTO_PIPELINE"'),
  pageSource.indexOf('key: "START_PROCESSING"')
);
assert.ok(bulkAutoOption.length > 0, "Bulk primary options must list START_AUTO_PIPELINE first");
assert.match(
  bulkAutoOption,
  /pipelineMode: "auto_to_render"/,
  "Bulk Start auto must reach render like the hero CTA"
);

assert.match(
  pageSource,
  /Auto→TTS/,
  "Stopping after TTS must be labelled by where it stops, not by what it renders"
);
assert.doesNotMatch(
  pageSource,
  /Auto→Render/,
  "Render is now the default, so a separate Auto→Render CTA must be gone"
);

console.log("reup-queue-auto-default tests passed");
