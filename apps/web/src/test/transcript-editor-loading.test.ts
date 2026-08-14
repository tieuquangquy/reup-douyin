import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const testDir = dirname(fileURLToPath(import.meta.url));
const pageSource = readFileSync(resolve(testDir, "../components/transcript-editor/TranscriptEditorPage.tsx"), "utf8");
const statesSource = readFileSync(resolve(testDir, "../components/transcript-editor/TranscriptStates.tsx"), "utf8");
const cssSource = readFileSync(resolve(testDir, "../app/globals.css"), "utf8");
const enSource = readFileSync(resolve(testDir, "../lib/i18n/en.json"), "utf8");

assert.match(statesSource, /export function TranscriptLoadingState/, "Must expose a transcript-specific loading shell");
assert.match(statesSource, /transcript-loading/, "Loading shell must use a stable CSS root class");
assert.match(statesSource, /transcript-loading__header/, "Loading shell must ghost the command header");
assert.match(statesSource, /transcript-loading__bench/, "Loading shell must ghost the dialogue bench grid");
assert.match(statesSource, /transcript-loading__media/, "Loading shell must ghost the media panel");
assert.match(statesSource, /transcript-loading__beats/, "Loading shell must ghost the beat rail");
assert.match(statesSource, /transcript-loading__focus/, "Loading shell must ghost the focus editor");
assert.match(statesSource, /role="status"/, "Loading shell must announce as a status region");
assert.match(statesSource, /aria-busy/, "Loading shell must mark itself busy");
assert.match(statesSource, /transcriptEditorStates\.loading/, "Loading shell must use i18n loading copy");

assert.match(pageSource, /TranscriptLoadingState/, "Transcript page must mount the layout-matched loading shell");
assert.match(
  pageSource,
  /skeleton=\{<\s*TranscriptLoadingState\s*\/>\}|skeleton=\{<TranscriptLoadingState\s*\/>\}/,
  "Transcript page must pass TranscriptLoadingState via AsyncContentBoundary skeleton prop"
);
assert.doesNotMatch(
  pageSource,
  /skeletonVariant="detail"/,
  "Transcript initial load must not use the generic detail skeleton"
);

assert.match(cssSource, /\.transcript-loading\b/, "Loading shell must have stylesheet rules");
assert.match(cssSource, /\.transcript-loading__bench\b/, "Bench ghost grid must be styled");
assert.match(enSource, /"loading":\s*"Loading transcript/, "Loading copy must be short and operator-facing");

console.log("transcript-editor loading tests passed");
