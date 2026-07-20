import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import {
  findJoinedTtsAssetId,
  indexTtsClipFitsByTranslationId,
  isTtsFitProblem,
  type TtsSummaryResponse
} from "../types/tts";
import { beatRailShowsTtsFit, classifyTtsFitTone, formatTtsFitRatio } from "../lib/ttsFitPresentation";

const testDir = dirname(fileURLToPath(import.meta.url));
const apiSource = readFileSync(resolve(testDir, "../lib/api.ts"), "utf8");
const previewSource = readFileSync(resolve(testDir, "../components/transcript-editor/TranscriptMediaPreview.tsx"), "utf8");
const headerSource = readFileSync(resolve(testDir, "../components/transcript-editor/TranscriptEditorHeader.tsx"), "utf8");
const pageSource = readFileSync(resolve(testDir, "../components/transcript-editor/TranscriptEditorPage.tsx"), "utf8");
const beatRailSource = readFileSync(resolve(testDir, "../components/transcript-editor/TranscriptBeatRail.tsx"), "utf8");
const focusSource = readFileSync(resolve(testDir, "../components/transcript-editor/TranscriptFocusEditor.tsx"), "utf8");
const enSource = readFileSync(resolve(testDir, "../lib/i18n/en.json"), "utf8");
const viSource = readFileSync(resolve(testDir, "../lib/i18n/vi.json"), "utf8");

assert.match(apiSource, /export async function createTtsJob/, "API must expose createTtsJob");
assert.match(apiSource, /export async function fetchTtsSummary/, "API must expose fetchTtsSummary");
assert.match(
  apiSource,
  /voice_id:\s*""/,
  "createTtsJob must omit client voice so active Ops TTS profile can be authority"
);
assert.match(apiSource, /force_refresh/, "createTtsJob must allow force refresh");

assert.match(previewSource, /joinedTtsAssetId/, "Media preview must accept joined TTS asset id");
assert.match(previewSource, /<audio controls/, "Joined narration must play via audio controls");
assert.match(
  previewSource,
  /fetchMediaAssetObjectUrl\(joinedTtsAssetId\)/,
  "Joined TTS must use Bearer → blob URL, not raw media-assets src"
);

assert.match(headerSource, /generateTts/, "Header must surface Generate TTS CTA");
assert.doesNotMatch(headerSource, /\/ops\/tts-ai/, "Header must not deep-link Ops TTS settings");
assert.doesNotMatch(
  headerSource,
  /Translate-only|translate only/i,
  "Command bar must not be Translate-only after TTS handoff"
);

assert.match(pageSource, /indexTtsClipFitsByTranslationId/, "Page must index TTS clip fits by translation id");
assert.match(pageSource, /clipFitsByTranslationId/, "Beat rail must receive clip fit map");
assert.match(pageSource, /ttsClipFit/, "Focus editor must receive selected clip fit");
assert.match(beatRailSource, /transcript-beat-rail__tts-fit/, "Beat rail must render TTS fit badge");
assert.match(focusSource, /transcript-tts-fit/, "Focus editor must render TTS fit panel");

const en = JSON.parse(enSource) as {
  transcriptEditorHeader: { generateTts: string };
  transcriptEditorPage: { ttsEmptyVi: string };
  transcriptEditorBench: { ttsNarration: string };
  transcriptEditorTts: {
    fitLabel: string;
    fitShort: Record<string, string>;
    fitHint: Record<string, string>;
  };
};
const vi = JSON.parse(viSource) as {
  transcriptEditorHeader: { generateTts: string };
  transcriptEditorPage: { ttsEmptyVi: string };
  transcriptEditorBench: { ttsNarration: string };
  transcriptEditorTts: {
    fitLabel: string;
    fitShort: Record<string, string>;
    fitHint: Record<string, string>;
  };
};

assert.equal(en.transcriptEditorHeader.generateTts, "Generate TTS");
assert.ok(en.transcriptEditorPage.ttsEmptyVi.length > 0);
assert.ok(en.transcriptEditorBench.ttsNarration.length > 0);
assert.ok(en.transcriptEditorTts.fitLabel.length > 0);
assert.ok(en.transcriptEditorTts.fitShort.too_long.length > 0);
assert.ok(en.transcriptEditorTts.fitHint.too_long.length > 0);
assert.ok(vi.transcriptEditorHeader.generateTts.length > 0);
assert.ok(vi.transcriptEditorPage.ttsEmptyVi.length > 0);
assert.ok(vi.transcriptEditorBench.ttsNarration.length > 0);
assert.ok(vi.transcriptEditorTts.fitShort.slightly_long.length > 0);

const summary: TtsSummaryResponse = {
  source_video_id: "sv_1",
  tts_asset_count: 2,
  subtitle_count: 0,
  warnings: [],
  clips: [
    {
      asset_id: "clip_1",
      translation_segment_id: "tr_1",
      fit_status: "too_long",
      fit_ratio: 1.4,
      warnings: ["too_long"]
    },
    {
      asset_id: "clip_2",
      translation_segment_id: "tr_2",
      fit_status: "fits_well",
      fit_ratio: 0.95,
      warnings: []
    }
  ],
  timing_fit_summary: { fits_well: 1, slightly_long: 0, too_long: 1, too_short: 0 },
  assets: [
    { id: "clip_1", asset_type: "TTS_AUDIO_CLIP" },
    { id: "joined_1", asset_type: "TTS_AUDIO_JOINED" }
  ]
};
assert.equal(findJoinedTtsAssetId(summary), "joined_1");
assert.equal(findJoinedTtsAssetId({ ...summary, assets: [] }), null);

const byId = indexTtsClipFitsByTranslationId(summary);
assert.equal(byId.get("tr_1")?.fit_status, "too_long");
assert.equal(byId.get("tr_2")?.fit_status, "fits_well");
assert.equal(isTtsFitProblem("too_long"), true);
assert.equal(isTtsFitProblem("fits_well"), false);
assert.equal(beatRailShowsTtsFit(byId.get("tr_1")), true);
assert.equal(beatRailShowsTtsFit(byId.get("tr_2")), false);
assert.equal(classifyTtsFitTone("slightly_long"), "warn");
assert.equal(formatTtsFitRatio(1.12), "112%");

console.log("transcript-editor tts tests passed");
