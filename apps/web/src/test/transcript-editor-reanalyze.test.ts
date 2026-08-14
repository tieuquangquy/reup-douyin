import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { pollAnalyzeJobUntilSettled } from "../lib/transcriptEditorReanalyze";

{
  let calls = 0;
  const result = await pollAnalyzeJobUntilSettled({
    fetchStatus: async () => {
      calls += 1;
      if (calls < 2) return { status: "RUNNING", error_message: null, error_code: null };
      return { status: "SUCCEEDED", error_message: null, error_code: null };
    },
    sleep: async () => undefined,
    intervalMs: 1,
    maxAttempts: 5
  });
  assert.equal(result.outcome, "success");
}

{
  const result = await pollAnalyzeJobUntilSettled({
    fetchStatus: async () => ({ status: "FAILED", error_message: "boom", error_code: "X" }),
    sleep: async () => undefined,
    intervalMs: 1,
    maxAttempts: 5
  });
  assert.equal(result.outcome, "failed");
  if (result.outcome === "failed") {
    assert.equal(result.errorMessage, "boom");
  }
}

const testDir = dirname(fileURLToPath(import.meta.url));
const headerSource = readFileSync(resolve(testDir, "../components/transcript-editor/TranscriptEditorHeader.tsx"), "utf8");
const pageSource = readFileSync(resolve(testDir, "../components/transcript-editor/TranscriptEditorPage.tsx"), "utf8");
const focusSource = readFileSync(resolve(testDir, "../components/transcript-editor/TranscriptFocusEditor.tsx"), "utf8");
const apiSource = readFileSync(resolve(testDir, "../lib/api.ts"), "utf8");

assert.match(headerSource, /onReanalyze/, "Transcript header must expose Re-analyze audio CTA");
assert.match(headerSource, /reanalyzeAudio/, "Transcript header must label Re-analyze audio");
assert.match(headerSource, /onTranslateLiteral/, "Transcript header must expose Translate CTA");
assert.match(headerSource, /audioRecipeVersion/, "Transcript header must expose the active Analyze Audio recipe");
assert.match(headerSource, /editor-command__meta/, "Transcript header must render a compact recipe/quality meta strip");
{
  const leadChunk = headerSource.match(
    /className="transcript-header__lead"[\s\S]*?(?=className="editor-command")/
  )?.[0];
  assert.ok(leadChunk, "Transcript header must keep a command lead before the toolbar");
  assert.doesNotMatch(leadChunk, /editor-command__meta/, "Meta rail must not sit beside the pipeline inside the lead");
}
assert.match(
  headerSource,
  /role="toolbar"[\s\S]*editor-command__meta/,
  "Meta rail must render after the command toolbar (second row)"
);
assert.match(headerSource, /editor-command__meta-item/, "Meta rail must use quiet status items, not competing pipeline chips");
assert.doesNotMatch(headerSource, /editor-command__meta-chip|editor-command__meta-tag/, "Meta must not use chip/tag chrome beside the pipeline");
assert.doesNotMatch(headerSource, /Audio Â·/, "Audio recipe label must not use mojibake separator");
assert.match(headerSource, /shortAudioRecipe|audioRecipeVersion\.replace|split\("-"\)\.slice/, "Audio recipe display must shorten the long version id");
assert.match(pageSource, /audioRecipeVersion=\{summary\?\.audio_recipe_version\}/, "Transcript page must bind Audio recipe telemetry from the API");
assert.match(headerSource, /sourceReviewRequired/, "Header must expose the current source review gate");
assert.match(headerSource, /!guide\.sourceTranscriptApproved/, "Translate must stay disabled until source approval");
assert.match(headerSource, /literal_safe/, "Translate must enqueue literal_safe preset");
assert.doesNotMatch(headerSource, /natural_viral|translateNatural/, "Natural translate option must be removed");
assert.doesNotMatch(headerSource, /\/ops\/translation-ai/, "Transcript header must not deep-link Ops Translation settings");
assert.doesNotMatch(headerSource, /\/ops\/jobs/, "Transcript header must not deep-link Ops job monitor");
assert.doesNotMatch(headerSource, /<h1>/, "Transcript header must not duplicate shell title with h1");
assert.doesNotMatch(
  headerSource,
  /\/ops\/translation-prompt/,
  "Transcript header must not duplicate prompt link when settings tabs cover it"
);
assert.match(headerSource, /editor-command__translate/, "Translate must remain a primary command button when next");
assert.match(headerSource, /editor-command__reasr/, "Re-ASR must live on the main toolbar");
assert.doesNotMatch(headerSource, /editor-command__menu|<details/, "Translate must not use a legacy dropdown menu");
assert.doesNotMatch(headerSource, /onApproveSource/, "Approve source is not a primary CTA for non-Chinese operators");
assert.doesNotMatch(focusSource, /aiTools/, "AI job menu must not duplicate on the segment toolbar");
assert.match(pageSource, /createAudioAnalysis/, "Transcript page must enqueue ANALYZE_AUDIO via createAudioAnalysis");
assert.match(pageSource, /skipTranslation|true,\s*true/, "Re-analyze must request ASR-only (skip translation)");
assert.match(pageSource, /rerunTranslationDraft/, "Transcript page must enqueue Phase B translation job");
assert.match(
  apiSource,
  /Idempotency-Key[`"']?:\s*`translation:\$\{sourceVideoId\}:\$\{translationPreset\}:\$\{CORE_STAGE_RUNTIME\.BUILD_TRANSLATION_DRAFT\}`/,
  "Translation rerun must be single-flight across double-clicks and reconnects"
);
assert.match(apiSource, /expected_stage_version:\s*CORE_STAGE_RUNTIME\.ANALYZE_AUDIO/);
assert.match(apiSource, /expected_stage_version:\s*CORE_STAGE_RUNTIME\.BUILD_TRANSLATION_DRAFT/);
assert.match(pageSource, /fetchJob/, "Transcript page must poll job status after re-analyze/translate");
assert.match(pageSource, /clearDownstreamAuthorityUi/, "Successful Re-ASR must clear local Translation\/TTS authority");
assert.match(pageSource, /sessionStorage\.removeItem/, "Re-ASR must clear the old TTS fingerprint");
assert.match(pageSource, /isSourceTranscriptReadyForTranslation/, "Translate must be gated by current transcript authority");
assert.match(pageSource, /translationMatchesCurrentTranscript/, "Stale translations must not bind to a new transcript run");
assert.match(pageSource, /onTranslateLiteral/, "Transcript page must wire translate-literal handler");
assert.match(pageSource, /translateEmptyAfterJob/, "Translate literal must surface empty-VI after a completed job");
assert.match(pageSource, /translatePartialAfterJob/, "Translate literal must surface partial-VI when some beats stay empty");
assert.match(pageSource, /transcript-bench/, "Transcript page must use Dialogue Bench layout");
assert.match(focusSource, /source-textarea-primary/, "Chinese source must be the primary editable field");
assert.match(focusSource, /formatTranslationAuthorityChip/, "Focus surface must show translation authority chips");
assert.match(focusSource, /transcript-dual-pane/, "Focus surface must be ZH|VI dual pane");

console.log("transcript-editor reanalyze tests passed");
