import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { isNoDialogueAnalysisSummary } from "../components/transcript-editor/TranscriptStates";

assert.equal(
  isNoDialogueAnalysisSummary({
    source_video_id: "x",
    analysis_version: "AUDIO_ANALYSIS_V1_RUN_1",
    transcript_count: 0,
    translation_count: 0,
    asset_count: 0,
    manifest: {},
    dialogue_phase: "no_dialogue",
    has_speech: false
  }),
  true
);
assert.equal(
  isNoDialogueAnalysisSummary({
    source_video_id: "x",
    analysis_version: null,
    transcript_count: 0,
    translation_count: 0,
    asset_count: 0,
    manifest: {}
  }),
  false,
  "Never analyzed must keep the Run analysis empty state"
);
assert.equal(
  isNoDialogueAnalysisSummary({
    source_video_id: "x",
    analysis_version: "AUDIO_ANALYSIS_V1_RUN_2",
    transcript_count: 3,
    translation_count: 0,
    asset_count: 1,
    manifest: {},
    dialogue_phase: "source_auto_approved",
    has_speech: true
  }),
  false
);

const testDir = dirname(fileURLToPath(import.meta.url));
const statesSource = readFileSync(resolve(testDir, "../components/transcript-editor/TranscriptStates.tsx"), "utf8");
const pageSource = readFileSync(resolve(testDir, "../components/transcript-editor/TranscriptEditorPage.tsx"), "utf8");
assert.match(statesSource, /TranscriptNoDialogueState/, "Must expose no-dialogue empty state");
assert.match(statesSource, /noDialogueBody/, "Must explain caption is not speech");
assert.match(pageSource, /isNoDialogueAnalysisSummary/, "Transcript page must branch empty states");
assert.match(pageSource, /TranscriptNoDialogueState/, "Transcript page must render no-dialogue state");

console.log("transcript no-dialogue state tests passed");
