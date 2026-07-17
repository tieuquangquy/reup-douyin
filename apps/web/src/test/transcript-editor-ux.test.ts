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
assert.match(headerSource, /editor-command__core/, "Save + Translate must form the core action pair");
assert.match(headerSource, /editor-command__translate/, "Translate must remain a mode dropdown");
assert.match(headerSource, /editor-command__tts/, "Generate TTS must sit in the command core");
assert.match(headerSource, /generateTtsConfirm/, "Generate TTS must confirm before enqueue");
assert.match(headerSource, /onGenerateTts/, "Header must wire Generate TTS handler");
assert.match(headerSource, /editor-command__rail/, "Secondary actions must live in one muted rail");
assert.match(headerSource, /editor-command__discard/, "Discard must be demoted visually");
assert.match(headerSource, /translateLiteralShort/, "Translate menu must offer Literal");
assert.match(headerSource, /translateNaturalShort/, "Translate menu must offer Natural");
assert.doesNotMatch(headerSource, /editor-toolbar__btn--save/, "Legacy multi-color button stack must be gone");

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
assert.match(cssSource, /\.transcript-focus-chrome\s*\{/, "CSS must style quiet focus chrome");
assert.match(cssSource, /\.transcript-focus-chrome__toolbar\s*\{/, "CSS must style timing/ops toolbar strip");
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
assert.match(cssSource, /\.segment-flags--machine/, "CSS must style machine flag panel");
assert.match(cssSource, /\.segment-flags__group/, "CSS must style machine flag groups");
assert.match(
  cssSource,
  /\.segment-flags--machine\s*\{[^}]*align-items:\s*(?:stretch|flex-start);/,
  "Machine flag panel must left-align (not center children)"
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
assert.match(cssSource, /\.editor-command__rail/, "CSS must style secondary action rail");
assert.match(
  cssSource,
  /\.transcript-header\.transcript-header--command\s*\{[\s\S]*?grid-template-columns:\s*minmax\([^,]+,\s*1fr\)\s+auto;/,
  "Command header must beat base 3-col grid so actions stay in the right column"
);
assert.match(
  cssSource,
  /\.transcript-header--command\s+\.editor-command\s*\{[\s\S]*?justify-self:\s*end;/,
  "Command toolbar must pin to the far right of the header"
);

console.log("transcript-editor ux tests passed");
