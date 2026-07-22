import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const testDir = dirname(fileURLToPath(import.meta.url));
const headerSource = readFileSync(resolve(testDir, "../components/transcript-editor/TranscriptEditorHeader.tsx"), "utf8");
const pageSource = readFileSync(resolve(testDir, "../components/transcript-editor/TranscriptEditorPage.tsx"), "utf8");
const focusSource = readFileSync(resolve(testDir, "../components/transcript-editor/TranscriptFocusEditor.tsx"), "utf8");
const railSource = readFileSync(resolve(testDir, "../components/transcript-editor/TranscriptBeatRail.tsx"), "utf8");
const flagsSource = readFileSync(resolve(testDir, "../components/transcript-editor/TranscriptSegmentFlags.tsx"), "utf8");
const actionBarSource = readFileSync(resolve(testDir, "../components/transcript-editor/TranscriptActionBar.tsx"), "utf8");
const cssSource = readFileSync(resolve(testDir, "../app/globals.css"), "utf8");

assert.doesNotMatch(headerSource, /<h1>/, "Header must not duplicate Operator shell title with h1");
assert.match(headerSource, /transcript-header--command/, "Header must use command-bar layout");
assert.match(headerSource, /transcript-header__back-icon/, "Back to review board must show a leading icon");
assert.match(headerSource, /resolveTranscriptPipelineGuide/, "Header must resolve guided pipeline stage");
assert.match(headerSource, /editor-command__pipeline/, "Header must show Review→Translate→TTS→Final stepper");
assert.match(headerSource, /editor-command__pipeline-badge/, "Pipeline steps must render as pill badges");
assert.match(headerSource, /editor-command__pipeline-connector/, "Pipeline badges must show step-by-step connectors");
assert.match(headerSource, /editor-command__primary/, "Header must promote a single primary pipeline CTA");
assert.match(headerSource, /editor-command__save/, "Save draft must remain available beside the pipeline");
assert.match(headerSource, /editor-command__translate/, "Translate must remain wired");
assert.match(headerSource, /editor-command__tts/, "Generate TTS must remain wired");
assert.match(headerSource, /generateTtsConfirm/, "Generate TTS must confirm before enqueue");
assert.match(headerSource, /onGenerateTts/, "Header must wire Generate TTS handler");
assert.match(headerSource, /hasVietnamese|ttsRequiresVi|!guide\.hasVietnamese/, "Generate TTS must soft-gate when VI is empty");
assert.match(headerSource, /isTranscriptPipelineActionUnlocked/, "Toolbar CTAs must gate on pipeline unlock");
assert.match(headerSource, /editor-command__pipeline-lock/, "Locked pipeline steps must show a lock affordance");
assert.match(headerSource, /pipelineLocked/, "Locked steps must expose a locked title/hint");
assert.doesNotMatch(headerSource, /editor-command__more|<details/, "Toolbar must not hide actions behind a More menu");
assert.match(headerSource, /translateAgain|regenerateTts/, "Rework actions must use again/regenerate labels");
assert.match(headerSource, /translateAgainCascadeConfirm|reanalyzeCascadeConfirm/, "Cascade confirms must warn about downstream invalidation");
assert.match(headerSource, /editor-command__freshness|ttsFreshness/, "Header must surface TTS freshness when narration may be stale");
assert.match(headerSource, /ttsFreshness\s*!==\s*["']hidden["']|ttsFreshness\s*===\s*["'](current|outdated)["']/, "Freshness chip must gate on resolved freshness, not bare hasJoinedTts");
assert.match(headerSource, /transcriptPipelineActionLabelKey/, "Action labels must resolve through pipeline helper");
assert.match(pageSource, /fingerprintVietnameseDraft|ttsSourceFingerprint|ttsViFp/, "Page must persist VI fingerprint used for TTS freshness");
assert.match(headerSource, /editor-command__icon/, "Command actions must show icon + text");
assert.match(headerSource, /literal_safe/, "Single Translate button must enqueue literal_safe");
assert.match(headerSource, /reanalyzeShort|Re-ASR|reanalyzeAudio/, "Re-ASR must stay available as advanced action");
assert.match(
  headerSource,
  /primary === "translate"[\s\S]*editor-command__translate/,
  "When Translate is next, it must render as the single primary CTA"
);
assert.match(
  headerSource,
  /isTranscriptPipelineActionUnlocked\("tts"/,
  "Generate TTS must stay hidden until Translate is passed"
);
assert.match(
  headerSource,
  /isTranscriptPipelineActionUnlocked\("final"/,
  "Final must stay hidden until TTS is passed"
);
assert.match(
  headerSource,
  /editor-command__save[\s\S]*editor-command__focus[\s\S]*editor-command__reasr[\s\S]*editor-command__discard/,
  "Toolbar order must be Save → primary/focus → Re-ASR → Discard"
);
assert.doesNotMatch(headerSource, /editor-command__menu/, "Legacy translate dropdown menu must stay removed");
assert.doesNotMatch(headerSource, /natural_viral|translateNaturalShort|translateLiteralShort/, "Literal/Natural translate options must be removed");
assert.doesNotMatch(headerSource, /editor-toolbar__btn--save/, "Legacy multi-color button stack must be gone");
assert.match(cssSource, /\.editor-command__pipeline/, "CSS must style the transcript pipeline stepper");
assert.match(
  cssSource,
  /\.editor-command__pipeline-badge\s*\{[^}]*border-radius:\s*999px/,
  "Pipeline badges must use pill shape"
);
assert.match(
  cssSource,
  /@keyframes\s+editor-pipeline-active-pulse/,
  "Active pipeline step must pulse so current stage is noticeable"
);
assert.match(
  cssSource,
  /@keyframes\s+editor-pipeline-connector-flow/,
  "Reached connectors must animate to show step-by-step flow"
);
assert.match(
  cssSource,
  /prefers-reduced-motion:\s*reduce[\s\S]*editor-command__pipeline/,
  "Pipeline motion must respect reduced-motion preference"
);
assert.match(
  cssSource,
  /\.editor-command__pipeline-connector/,
  "CSS must style step-by-step connectors between pipeline badges"
);
assert.match(
  cssSource,
  /\.editor-command__pipeline-step\.is-active\s+\.editor-command__pipeline-index\s*\{[^}]*background:\s*var\(--accent-strong\)/,
  "Active pipeline step must use a filled index so current stage is obvious"
);
assert.match(
  cssSource,
  /\.editor-command__pipeline-lock/,
  "CSS must style lock icon on pending pipeline steps"
);
assert.match(
  cssSource,
  /\.transcript-header--command\s+\.transcript-header__back\s*\{[^}]*inline-flex/,
  "Back link must render as an inline-flex control (icon + label)"
);
assert.match(cssSource, /\.editor-command__primary/, "CSS must emphasize the primary pipeline CTA");
assert.match(cssSource, /\.editor-command__discard/, "CSS must style Discard as a danger toolbar control");
assert.match(cssSource, /\.editor-command__quiet/, "Non-primary command buttons must stay quiet");

assert.match(pageSource, /transcript-bench/, "Page must use Dialogue Bench workspace");
assert.match(pageSource, /TranscriptBeatRail/, "Page must mount beat rail");
assert.match(pageSource, /TranscriptFocusEditor/, "Page must mount focus editor");
assert.match(pageSource, /createTtsJob/, "Page must create SYNTHESIZE_TTS jobs");
assert.match(pageSource, /fetchTtsSummary/, "Page must refresh TTS summary after job success");
assert.match(pageSource, /joinedTtsAssetId/, "Page must pass joined TTS asset into media preview");
assert.match(pageSource, /ttsEmptyVi/, "Page must guard Generate TTS when VI is empty");
assert.doesNotMatch(pageSource, /TranscriptComparePanel/, "Always-on Compare column must be removed");
assert.match(
  cssSource,
  /\.transcript-bench\s*\{[^}]*grid-template-columns:\s*minmax\([^,]+,\s*(?:4[2-9]\d|5\d{2})px\)/,
  "Dialogue Bench left rail must be wide enough for a usable video preview"
);
assert.match(
  cssSource,
  /\.transcript-bench-media\s+\.media-box\s*\{[^}]*min-height:\s*(?:2[2-9]\d|[3-9]\d{2})px/,
  "Bench media box must enforce a usable minimum video height"
);
assert.match(
  cssSource,
  /\.media-box\s*\{[^}]*overflow:\s*hidden/,
  "Base media-box must clip intrinsic video size so it cannot cover the focus editor"
);
assert.match(
  cssSource,
  /\.media-box\s+video\s*\{[^}]*width:\s*100%[^}]*height:\s*100%|\.media-box\s+video\s*\{[^}]*height:\s*100%[^}]*width:\s*100%/,
  "Base media-box video must fill the framed box (width/height 100%)"
);
assert.match(
  cssSource,
  /\.editor-command__discard\s*\{[^}]*color:\s*#b91c1c/,
  "Discard on the toolbar must stay visually demoted as danger"
);

assert.match(focusSource, /transcript-dual-pane/, "Focus editor must use ZH|VI dual pane");
assert.match(focusSource, /source-textarea-primary/, "Focus editor must expose ZH primary field");
assert.doesNotMatch(focusSource, /onTranslateLiteral/, "Translate jobs live only in the header bar");
assert.match(focusSource, /transcript-focus-chrome/, "Focus editor must use quiet chrome shell");
assert.match(focusSource, /transcript-focus-chrome__title/, "Segment title must be the chrome hero");
assert.match(focusSource, /transcript-focus-chrome__range/, "Timing range must sit beside the segment title");
assert.match(focusSource, /transcript-focus-chrome__run/, "Pipeline meta must live in a demoted details block");
assert.match(focusSource, /runDetails/, "Run details summary must be i18n-labeled");
assert.match(focusSource, /transcript-focus-chrome__toolbar/, "Timing + segment ops must share one toolbar strip");
assert.match(
  focusSource,
  /transcript-focus-chrome__run[\s\S]*sourceVideoId[\s\S]*translation-authority-chip/,
  "Job id / analysis / authority chips must live inside Run details"
);
assert.match(focusSource, /segment-ops__btn--play/, "Play remains the primary segment op");
assert.match(focusSource, /segment-ops__icon/, "Segment ops must use icon + text");
assert.match(focusSource, /isPlaying|transcriptEditorRow\.pause|kind=\{isPlaying \? "pause"/, "Focus Play control must toggle to Pause while video is playing");
assert.match(
  focusSource,
  /segment-ops__btn--play[\s\S]*SegmentOpsIcon[\s\S]*(?:play|pause)[\s\S]*segment-ops__btn[\s\S]*SegmentOpsIcon[\s\S]*split/,
  "Play/Pause and Split must both render icon + text"
);
assert.match(pageSource, /pauseRequestId|onPlayingChange/, "Page must wire preview pause + playing state into focus Play control");
assert.match(cssSource, /\.transcript-focus-chrome\s*\{/, "CSS must style quiet focus chrome");
assert.match(cssSource, /\.transcript-focus-chrome__toolbar\s*\{/, "CSS must style timing/ops toolbar strip");
assert.match(
  cssSource,
  /\.transcript-focus-chrome__toolbar \.segment-ops__btn--play:hover:not\(:disabled\)\s*\{[^}]*color:\s*#fff/,
  "Toolbar Play/Pause hover must keep white label on accent (not bleached white-on-white)"
);
assert.match(cssSource, /\.timing-editor--compact/, "CSS must define compact timing editor");

assert.match(railSource, /segmentsList/, "Beat rail must use Segments list label");
assert.match(flagsSource, /partitionSegmentFlags/, "Flags component must use quiet operator partition");
assert.match(flagsSource, /segment-flags--machine/, "Machine details must use structured machine flag panel");
assert.match(flagsSource, /segment-flags__group--attention/, "Machine panel must group attention flags");
assert.match(flagsSource, /segment-flags__group--pipeline/, "Machine panel must group pipeline telemetry");
assert.doesNotMatch(
  flagsSource,
  /<details className="segment-flags__pipeline">/,
  "Pipeline must not nest a second details toggle inside Machine details"
);
assert.match(focusSource, /compare-machine-details/, "Focus editor keeps Machine details disclosure");
assert.match(focusSource, /compare-machine-details__title/, "Machine details summary must expose title");
assert.match(focusSource, /compare-machine-details__hint/, "Machine details summary must expose hint");
assert.match(cssSource, /\.compare-machine-details/, "CSS must style Machine details disclosure");
assert.match(
  cssSource,
  /\.compare-machine-details\s*>\s*summary\s*\{[^}]*display:\s*flex;[^}]*gap:/,
  "Machine details summary must flex title+hint with gap (no smashed text)"
);
assert.match(cssSource, /\.compare-machine-details__title/, "CSS must style Machine details title");
assert.match(cssSource, /\.compare-machine-details__hint/, "CSS must style Machine details hint");
assert.match(cssSource, /\.segment-flags--machine/, "CSS must style machine flag panel");
assert.match(cssSource, /\.segment-flags__group/, "CSS must style machine flag groups");
assert.match(
  cssSource,
  /\.segment-flags--machine\s*\{[^}]*align-items:\s*(?:stretch|flex-start);/,
  "Machine flag panel must left-align (not center children)"
);
assert.match(
  cssSource,
  /\.segment-flags--machine\s*\{[^}]*gap:\s*[1-4]px;/,
  "Machine flag panel must stay vertically compact"
);
assert.match(
  cssSource,
  /\.segment-flags__group\s*\{[^}]*grid-template-columns:/,
  "Machine groups must be compact label|chips rows"
);
assert.match(actionBarSource, /if \(dirtyCount === 0\) return null/, "Floating dock must be dirty-only");

assert.match(cssSource, /\.editor-command \{/, "CSS must define professional command bar");
assert.match(cssSource, /\.editor-command__tts/, "CSS must style Generate TTS as secondary to Translate");
assert.match(cssSource, /\.transcript-bench-media__tts/, "CSS must style joined TTS audio player");
assert.match(cssSource, /\.transcript-header__bar/, "Command header must use a flex bar (not competing 3-col grid)");
assert.match(
  cssSource,
  /\.transcript-header\.transcript-header--command\s*\{[\s\S]*?display:\s*block;/,
  "Command header must override base grid so the bar owns layout"
);
assert.match(
  cssSource,
  /\.transcript-header--command\s+\.editor-command\s*\{[\s\S]*?margin-left:\s*auto;/,
  "Command toolbar must pin to the far right of the header"
);

console.log("transcript-editor ux tests passed");
