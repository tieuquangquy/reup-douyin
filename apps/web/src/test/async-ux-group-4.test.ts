import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const read = (path: string) => readFileSync(`src/components/${path}`, "utf8");

const transcriptPage = read("transcript-editor/TranscriptEditorPage.tsx");
const transcriptHeader = read("transcript-editor/TranscriptEditorHeader.tsx");
const finalReviewPage = read("final-review/FinalReviewPage.tsx");
const finalReviewUi = [
  read("final-review/FinalReviewHeader.tsx"),
  read("final-review/FinalReviewActions.tsx"),
  read("final-review/FinalReviewStates.tsx"),
  read("final-review/FinalReviewVisualCheckpoint.tsx")
].join("\n");
const publishPage = read("publish-draft/PublishDraftPage.tsx");
const publishUi = [
  read("publish-draft/PublishDraftHeader.tsx"),
  read("publish-draft/PublishSchedulePanel.tsx"),
  read("publish-draft/PublishTargetSelector.tsx")
].join("\n");
const intakePage = read("intake/IntakePage.tsx");
const llmPage = read("ops-console/OpsLlmAiSetupsPage.tsx");
const promptPage = read("ops-console/OpsPromptSetupsPage.tsx");
const ttsPage = read("ops-console/OpsTtsAiPage.tsx");

for (const [name, source] of [
  ["Transcript Editor", transcriptPage],
  ["Final Review", finalReviewPage],
  ["Publish Draft", publishPage],
  ["Intake", intakePage],
  ["LLM settings", llmPage],
  ["Prompt settings", promptPage],
  ["TTS settings", ttsPage]
] as const) {
  assert.match(source, /useAsyncAction/, `${name} must gate async actions against double clicks`);
  assert.match(source, /useNotice/, `${name} must announce terminal async outcomes`);
}

for (const [name, source] of [
  ["Transcript Editor", transcriptHeader],
  ["Final Review", finalReviewUi],
  ["Publish Draft", publishUi],
  ["Intake", intakePage],
  ["LLM settings", llmPage],
  ["Prompt settings", promptPage],
  ["TTS settings", ttsPage]
] as const) {
  assert.match(source, /AsyncButton/, `${name} must render immediate button-level pending feedback`);
}

assert.match(llmPage, /useLatestRequest/, "LLM model/list requests must ignore stale responses");
assert.match(intakePage, /useLatestRequest/, "Intake run detail/compare requests must ignore stale responses");

assert.match(transcriptPage, /cancelRunningJob/, "Transcript cancellation semantics must remain inline");
assert.match(transcriptPage, /resumeActiveTranscriptJob/, "Transcript job re-attachment must remain");
assert.match(transcriptPage, /translatePartialAfterJob/, "Transcript partial translation must remain inline");
assert.match(transcriptPage, /jobId=\{analyzeJobId\}/, "Transcript job ID must remain visible");
assert.match(finalReviewPage, /maxAttempts:\s*900/, "Final Review OCR polling budget must remain");
assert.match(finalReviewPage, /renderQueued[\s\S]*notify/, "Final Review queued render job ID must announce via toast");
assert.doesNotMatch(
  finalReviewPage,
  /setActionMessage\(t\("finalReviewStates\.renderQueued"\)|setActionMessage\(queued\)/,
  "Final Review must not keep queued render status as an inline action message"
);
{
  const startRenderFn = finalReviewPage.match(
    /async function handleStartFirstRender\(\)[\s\S]*?(?=async function handleRerender\(\))/
  )?.[0] ?? "";
  const rerenderFn = finalReviewPage.match(
    /async function handleRerender\(\)[\s\S]*?(?=async function handleAnalyzeOcr\(\))/
  )?.[0] ?? "";
  assert.doesNotMatch(startRenderFn, /setError\((?!null\))/, "Start render must not keep failed status inline");
  assert.doesNotMatch(rerenderFn, /setError\((?!null\))/, "Rerender must not keep failed status inline");
}
assert.match(ttsPage, /pollInstallUntilDone/, "TTS install polling must remain");
assert.match(ttsPage, /onCancelPreview/, "TTS preview cancellation must remain");
assert.match(ttsPage, /previewPollCancelledRef/, "TTS preview cancellation guard must remain");

console.log("async UX group 4 tests passed");
