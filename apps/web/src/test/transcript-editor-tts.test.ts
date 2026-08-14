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
const temporalReportSource = readFileSync(resolve(testDir, "../components/transcript-editor/TranscriptTtsTemporalReport.tsx"), "utf8");
const enSource = readFileSync(resolve(testDir, "../lib/i18n/en.json"), "utf8");
const viSource = readFileSync(resolve(testDir, "../lib/i18n/vi.json"), "utf8");
const cssFull = readFileSync(resolve(testDir, "../app/globals.css"), "utf8");
const temporalReportCssStart = cssFull.indexOf(".transcript-temporal-report {");
assert.ok(temporalReportCssStart >= 0, "globals.css must define transcript-temporal-report");
const temporalReportCss = cssFull.slice(temporalReportCssStart, temporalReportCssStart + 12000);

assert.match(apiSource, /export async function createTtsJob/, "API must expose createTtsJob");
assert.match(apiSource, /export async function fetchTtsSummary/, "API must expose fetchTtsSummary");
assert.match(
  apiSource,
  /voice_id:\s*""/,
  "createTtsJob must omit client voice so backend production recipe can be authority"
);
assert.match(apiSource, /force_refresh/, "createTtsJob must allow force refresh");
assert.match(
  apiSource,
  /force_refresh:\s*options\.forceRefresh\s*\?\?\s*false/,
  "Generate TTS must be cache-first unless full regeneration is explicit"
);
assert.match(
  apiSource,
  /expected_stage_version:\s*CORE_STAGE_RUNTIME\.SYNTHESIZE_TTS/,
  "Generate TTS must bind the browser command to TTS Temporal V5"
);
assert.match(
  apiSource,
  /assertAcceptedCoreRuntime\([\s\S]*?"Synthesize TTS"[\s\S]*?CORE_STAGE_RUNTIME\.SYNTHESIZE_TTS/,
  "Generate TTS must reject an unexpected server runtime"
);
assert.match(
  apiSource,
  /expected_stage_version:\s*CORE_STAGE_RUNTIME\.SYNTHESIZE_TTS/,
  "Generate TTS must bind the browser command to TTS Temporal V5"
);
assert.match(
  apiSource,
  /assertAcceptedCoreRuntime\([\s\S]*?"Synthesize TTS"[\s\S]*?CORE_STAGE_RUNTIME\.SYNTHESIZE_TTS/,
  "Generate TTS must reject an unexpected server runtime"
);

assert.match(previewSource, /joinedTtsAssetId/, "Media preview must accept joined TTS asset id");
assert.match(previewSource, /<audio controls/, "Joined narration must play via audio controls");
assert.match(
  previewSource,
  /fetchMediaAssetObjectUrl\(joinedTtsAssetId\)/,
  "Joined TTS must use Bearer → blob URL, not raw media-assets src"
);

assert.match(headerSource, /onGenerateTts/, "Header must surface Generate TTS CTA");
assert.doesNotMatch(headerSource, /\/ops\/tts-ai/, "Header must not deep-link Ops TTS settings");
assert.doesNotMatch(
  headerSource,
  /Translate-only|translate only/i,
  "Command bar must not be Translate-only after TTS handoff"
);

assert.match(pageSource, /indexTtsClipFitsByTranslationId/, "Page must index TTS clip fits by translation id");
assert.match(pageSource, /clipFitsByTranslationId/, "Beat rail must receive clip fit map");
assert.match(pageSource, /ttsClipFit/, "Focus editor must receive selected clip fit");
assert.match(
  pageSource,
  /const forceRefresh = Boolean\(joinedTtsAssetId\)/,
  "Regenerate TTS must detect an existing joined narration"
);
assert.match(
  pageSource,
  /createTtsJob\(sourceVideoId, \{ forceRefresh \}\)/,
  "Regenerate TTS must create an explicit force-refresh job"
);
assert.match(
  pageSource,
  /if \(jobId && !forceRefresh\)/,
  "Regenerate TTS must not reattach the checkpoint's historical auto job"
);
assert.match(beatRailSource, /transcript-beat-rail__tts-fit/, "Beat rail must render TTS fit badge");
assert.match(focusSource, /transcript-tts-fit/, "Focus editor must render TTS fit panel");
assert.match(temporalReportSource, /transcript-temporal-report__summary/, "Temporal report must render a compact summary strip");
assert.match(temporalReportSource, /transcript-temporal-report__stats/, "Temporal report must render summary stats");
assert.match(temporalReportSource, /transcript-temporal-report__stat\b/, "Summary stats must render as individual pills");
assert.match(temporalReportSource, /transcript-temporal-report__stat[\s\S]{0,160}?<strong>/, "Summary stat pills must emphasize the value");
assert.match(
  temporalReportSource,
  /transcript-temporal-report__head"[\s\S]{0,700}?transcript-temporal-report__voice/,
  "Voice must live in the compact head row with title/Ready",
);
assert.doesNotMatch(temporalReportSource, /transcript-temporal-report__metrics/, "Temporal report must retire primary metric cards");
assert.doesNotMatch(temporalReportSource, /__stats[\s\S]*?<i aria-hidden/, "Summary stats must not use middot text glue");
assert.match(temporalReportCss, /transcript-temporal-report__stats\s*\{[^}]*width:\s*100%/, "Summary stats strip must span the full row");
assert.match(
  temporalReportCss,
  /transcript-temporal-report__stats\s*\{[^}]*grid-template-columns:\s*repeat\(auto-fit,\s*minmax\(/,
  "Summary stats strip must divide evenly across the available width",
);
assert.match(temporalReportCss, /transcript-temporal-report__stat\s*>\s*strong/, "CSS must style emphasized stat values");
assert.doesNotMatch(temporalReportCss, /transcript-temporal-report__stat\s*\{[^}]*width:\s*max-content/, "Stat cells must not stay content-width and leave a blank right rail");
assert.match(temporalReportSource, /<details[\s\S]*transcript-temporal-report__detail/, "Temporal report must collapse engineering fields in details");
assert.match(temporalReportSource, /transcript-temporal-report__tiles/, "Pipeline detail must render a visual tile grid");
assert.match(temporalReportSource, /transcript-temporal-report__tile/, "Pipeline detail must render individual metric tiles");
assert.match(
  temporalReportCss,
  /transcript-temporal-report__tiles\s*\{[^}]*grid-template-columns:\s*repeat\(auto-fill,\s*minmax\(/,
  "Pipeline detail tiles must spread across full-width auto-fill columns",
);
assert.match(temporalReportCss, /transcript-temporal-report__tile\s*\{/, "CSS must style detail metric tiles");
assert.doesNotMatch(
  temporalReportCss,
  /transcript-temporal-report__detail dl\s*\{[^}]*max-width:\s*42rem/,
  "Pipeline detail must not stay capped at 42rem",
);
assert.match(temporalReportSource, /temporalPipelineDetail/, "Temporal report must label the pipeline detail disclosure");
assert.match(temporalReportSource, /count > 0/, "Exception stats must only surface non-zero repair/correction counts");
assert.match(
  temporalReportSource,
  /const stats:[\s\S]*?key:\s*"groups"[\s\S]*?key:\s*"elapsed"[\s\S]*?key:\s*"gap"[\s\S]*?\];/,
  "Status line primary stats must be groups/elapsed/gap only",
);
assert.doesNotMatch(temporalReportSource, /temporalVoiceModel/, "Pipeline detail must not echo provider · model already on the voice line");
assert.match(temporalReportSource, /temporalBackground/, "Background audio must stay available in pipeline detail");
assert.match(temporalReportSource, /temporalArtifacts/, "QA artifacts must stay available in pipeline detail");
assert.match(temporalReportSource, /temporalSynthesisStrategy/, "Synthesis strategy must stay available in pipeline detail");
assert.doesNotMatch(
  temporalReportSource,
  /<dl>[\s\S]*dialogue_group_count[\s\S]*fitted_cache_hit_count[\s\S]*<\/dl>/,
  "Temporal report must not keep the old equal card-grid wall as the only surface",
);
assert.match(temporalReportSource, /fitted_cache_hit_count/, "Temporal report must expose fitted cache hits");
assert.match(temporalReportSource, /provider_synthesis_clip_count/, "Temporal report must expose real provider work");
assert.match(temporalReportSource, /provider_synthesis_call_count/, "Temporal report must expose provider request count");
assert.match(temporalReportSource, /single_request_video/, "Temporal report must expose whole-video single-request verification");
assert.match(temporalReportSource, /total_elapsed_ms/, "Temporal report must expose measured TTS elapsed time");
assert.match(temporalReportSource, /tts_authority/, "Temporal report must expose the exact active voice authority");
assert.match(temporalReportSource, /profile_name/, "Temporal report must identify the setup that generated narration");
assert.match(enSource, /"temporalPipelineDetail"/, "en.json must define temporalPipelineDetail");
assert.match(viSource, /"temporalPipelineDetail"/, "vi.json must define temporalPipelineDetail");
assert.match(enSource, /"temporalReportTitle":\s*"TTS timing"/, "en temporal title must be shortened for the strip");
assert.match(viSource, /"temporalReportTitle":/, "vi temporal title must remain defined");

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
