import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const testDir = dirname(fileURLToPath(import.meta.url));
const statusSource = readFileSync(
  resolve(testDir, "../components/final-review/FinalReviewActionStatus.tsx"),
  "utf8"
);
const visualSource = readFileSync(
  resolve(testDir, "../components/final-review/FinalReviewVisualCheckpoint.tsx"),
  "utf8"
);
const pageSource = readFileSync(resolve(testDir, "../components/final-review/FinalReviewPage.tsx"), "utf8");
const actionsSource = readFileSync(
  resolve(testDir, "../components/final-review/FinalReviewActions.tsx"),
  "utf8"
);
const emptySource = readFileSync(
  resolve(testDir, "../components/final-review/FinalReviewStates.tsx"),
  "utf8"
);
const cssSource = readFileSync(resolve(testDir, "../app/globals.css"), "utf8");
const en = JSON.parse(readFileSync(resolve(testDir, "../lib/i18n/en.json"), "utf8")) as {
  finalReviewVisual: Record<string, string>;
  finalReviewStates: Record<string, string>;
};
const vi = JSON.parse(readFileSync(resolve(testDir, "../lib/i18n/vi.json"), "utf8")) as {
  finalReviewVisual: Record<string, string>;
  finalReviewStates: Record<string, string>;
};

assert.match(statusSource, /fr-action-status/, "Action status strip must use fr-action-status class");
assert.match(
  statusSource,
  /phase:\s*"queued"\s*\|\s*"running"\s*\|\s*"success"\s*\|\s*"warning"\s*\|\s*"error"|FinalReviewActionStatusPhase/,
  "Strip must model queued/running/success/warning/error phases"
);
assert.match(statusSource, /is-\$\{phase\}|is-\$\{props\.phase\}|`is-\$\{phase\}`/, "Phase must map to is-* tone class");
assert.match(statusSource, /is-running[\s\S]{0,200}fr-action-status__progress|fr-action-status__progress/, "Running phase must show indeterminate progress");

assert.match(cssSource, /\.fr-action-status\s*\{/, "globals must style fr-action-status");
assert.match(cssSource, /\.fr-action-status\.is-queued/, "CSS must style queued phase");
assert.match(cssSource, /\.fr-action-status\.is-running/, "CSS must style running phase");
assert.match(cssSource, /\.fr-action-status\.is-success/, "CSS must style success phase");
assert.match(cssSource, /\.fr-action-status\.is-warning/, "CSS must style warning phase");
assert.match(cssSource, /\.fr-action-status\.is-error/, "CSS must style error phase");
assert.match(cssSource, /fr-action-status__progress/, "CSS must style indeterminate progress track");

assert.match(visualSource, /FinalReviewActionStatus/, "Visual checkpoint must render the action status strip");
assert.doesNotMatch(
  visualSource,
  /className="action-message"/,
  "Visual checkpoint must not use the flat action-message bar for OCR status"
);

assert.match(pageSource, /FinalReviewActionStatus|ocrStatus|setOcrStatus/, "Page must own OCR lifecycle status");
assert.match(pageSource, /phase:\s*"queued"|phase:\s*'queued'/, "OCR/render lifecycle must set queued before/at job create");
assert.match(pageSource, /phase:\s*"running"|phase:\s*'running'/, "OCR/render lifecycle must set running while polling");
assert.match(
  pageSource,
  /analyzeQueued|analyzeInProgress/,
  "Page must use OCR queued/in-progress copy keys"
);

assert.match(actionsSource, /FinalReviewActionStatus/, "Decision bar must use action status strip");
assert.match(
  actionsSource,
  /fr-decision-bar--compact/,
  "Decision bar must use compact sticky layout"
);
assert.match(
  cssSource,
  /\.fr-decision-bar--compact\s+\.fr-action-status|\.fr-decision-bar--compact\s+\.fr-decision-bar__copy[\s\S]{0,120}flex-direction:\s*row/,
  "Compact decision bar must keep status inline with meta (not a tall stacked card)"
);
assert.match(
  cssSource,
  /\.fr-decision-bar--compact\s+\.fr-action-status[\s\S]{0,200}box-shadow:\s*none/,
  "Compact status strip must drop heavy inset rail for a cleaner pill"
);
assert.match(
  cssSource,
  /\.fr-decision-bar--compact\s+\.fr-action-status[\s\S]{0,220}max-width:\s*none/,
  "Compact status strip must stretch full width between meta and actions"
);
assert.doesNotMatch(
  actionsSource,
  /className="action-message"/,
  "Decision bar must not use flat action-message"
);

assert.match(emptySource, /FinalReviewActionStatus/, "Prep empty/render panel must surface render lifecycle strip");

assert.ok(en.finalReviewVisual.analyzeQueued, "en must define OCR queued copy");
assert.ok(en.finalReviewVisual.analyzeInProgress, "en must define OCR in-progress copy");
assert.ok(en.finalReviewVisual.approveQueued || en.finalReviewVisual.approving, "en must define approve progress copy");
assert.ok(en.finalReviewStates.renderQueued, "en must keep render queued copy");
assert.ok(en.finalReviewStates.renderInProgress, "en must keep render in-progress copy");
assert.ok(vi.finalReviewVisual.analyzeQueued, "vi must define OCR queued copy");
assert.ok(vi.finalReviewVisual.analyzeInProgress, "vi must define OCR in-progress copy");
assert.ok(en.finalReviewVisual.pauseOcr, "en must define OCR pause label");
assert.ok(en.finalReviewVisual.resumeOcr, "en must define OCR resume label");
assert.ok(en.finalReviewVisual.cancelOcr, "en must define OCR cancel label");
assert.ok(en.finalReviewVisual.ocrWatchPaused, "en must define UI-paused OCR copy");
assert.ok(en.finalReviewVisual.ocrCancelled, "en must define cancelled OCR copy");
assert.ok(vi.finalReviewVisual.pauseOcr, "vi must define OCR pause label");
assert.ok(vi.finalReviewVisual.resumeOcr, "vi must define OCR resume label");
assert.ok(vi.finalReviewVisual.cancelOcr, "vi must define OCR cancel label");
assert.ok(vi.finalReviewVisual.ocrWatchPaused, "vi must define UI-paused OCR copy");
assert.ok(vi.finalReviewVisual.ocrCancelled, "vi must define cancelled OCR copy");
assert.match(
  statusSource,
  /fr-action-status__controls|fr-action-status__pause|fr-action-status__cancel/,
  "OCR status must expose Pause/Resume + Cancel icon controls"
);
assert.match(
  statusSource,
  /onPause[\s\S]{0,200}onCancel|onResume[\s\S]{0,120}onCancel/,
  "Status strip must wire separate pause/resume and cancel handlers"
);
assert.match(
  cssSource,
  /\.fr-action-status__cancel[\s\S]{0,160}border-radius:\s*(999px|50%)|\.fr-action-status__controls[\s\S]{0,120}gap:/,
  "Pause/Cancel controls must stay small round icon buttons"
);
assert.match(
  cssSource,
  /\.fr-action-status__pause[\s\S]{0,500}min-height:\s*(0|2[468]px)/,
  "Pause circle must override global button min-height so it stays round"
);
assert.match(
  cssSource,
  /\.fr-action-status__cancel[\s\S]{0,500}min-height:\s*(0|2[468]px)/,
  "Cancel circle must override global button min-height so it stays round"
);
assert.match(
  cssSource,
  /\.fr-action-status__pause[\s\S]{0,500}height:\s*2[468]px[\s\S]{0,500}width:\s*2[468]px|\.fr-action-status__pause[\s\S]{0,500}width:\s*2[468]px[\s\S]{0,500}height:\s*2[468]px/,
  "Pause control must be a equal-sided circle"
);
assert.match(
  cssSource,
  /\.fr-action-status__cancel[\s\S]{0,500}height:\s*2[468]px[\s\S]{0,500}width:\s*2[468]px|\.fr-action-status__cancel[\s\S]{0,500}width:\s*2[468]px[\s\S]{0,500}height:\s*2[468]px/,
  "Cancel control must be a equal-sided circle"
);
assert.match(
  cssSource,
  /\.fr-action-status__pause[\s\S]{0,400}background:[^;]*(accent|var\(--accent)/,
  "Pause circle should use a filled accent surface"
);
assert.match(
  cssSource,
  /\.fr-action-status__cancel[\s\S]{0,400}background:[^;]*(#b42318|#e11d48|rgb|color-mix)/,
  "Cancel circle should use a filled soft-danger surface"
);
assert.match(
  pageSource,
  /ocrWatchPausedRef|pauseOcrWatch|resumeOcrWatch/,
  "Pause must stop UI polling without cancelling the job"
);
assert.match(
  pageSource,
  /cancelOcrJob|cancelJob/,
  "Cancel must call cancelJob on the in-flight ANALYZE_OCR job"
);
assert.match(
  visualSource,
  /onPause|onCancel|onResume|pausePending|cancelPending/,
  "Visual checkpoint must pass pause/resume/cancel into the status strip"
);
assert.match(
  visualSource,
  /hideAnalyzeCta|ocrLifecycleActive|watchPaused[\s\S]{0,320}analyzeBusy/,
  "When OCR strip owns the job, Visual Clean must not also show a busy Analyze spinner CTA"
);
assert.ok(en.finalReviewVisual.analyzePausedShort, "en must define short Paused Analyze label");
assert.ok(vi.finalReviewVisual.analyzePausedShort, "vi must define short Paused Analyze label");

assert.match(
  statusSource,
  /FINAL_REVIEW_STATUS_AUTO_DISMISS_MS\s*=\s*\d+/,
  "Status strip must export a fixed auto-dismiss duration"
);
assert.match(
  statusSource,
  /setTimeout\([\s\S]{0,80}onDismiss|setTimeout\(onDismiss/,
  "Terminal status notices must auto-dismiss via a timer calling onDismiss"
);
assert.match(
  statusSource,
  /phase\s*===\s*"success"[\s\S]{0,120}warning[\s\S]{0,120}error|success[\s\S]{0,40}warning[\s\S]{0,40}error/,
  "Auto-dismiss must apply to success/warning/error terminal phases"
);
assert.doesNotMatch(
  statusSource,
  /queued[\s\S]{0,40}running[\s\S]{0,80}setTimeout\(onDismiss|AUTO_DISMISS[\s\S]{0,200}queued/,
  "In-flight queued/running strips must not auto-dismiss"
);

console.log("final-review action status tests passed");
