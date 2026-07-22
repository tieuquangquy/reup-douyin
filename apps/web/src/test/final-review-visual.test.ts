import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const testDir = dirname(fileURLToPath(import.meta.url));
const apiSource = readFileSync(resolve(testDir, "../lib/api.ts"), "utf8");
const pageSource = readFileSync(resolve(testDir, "../components/final-review/FinalReviewPage.tsx"), "utf8");
const headerSource = readFileSync(resolve(testDir, "../components/final-review/FinalReviewHeader.tsx"), "utf8");
const actionsSource = readFileSync(resolve(testDir, "../components/final-review/FinalReviewActions.tsx"), "utf8");
const statesSource = readFileSync(resolve(testDir, "../components/final-review/FinalReviewStates.tsx"), "utf8");
const visualSource = readFileSync(resolve(testDir, "../components/final-review/FinalReviewVisualCheckpoint.tsx"), "utf8");
const cssSource = readFileSync(resolve(testDir, "../app/globals.css"), "utf8");
const en = JSON.parse(readFileSync(resolve(testDir, "../lib/i18n/en.json"), "utf8")) as {
  finalReviewVisual: Record<string, string>;
  finalReviewStates: Record<string, string>;
  finalReviewTabs: Record<string, string>;
  finalReviewActions: Record<string, string>;
  finalReviewHeader: Record<string, string>;
  transcriptEditorHeader: Record<string, string>;
};
const vi = JSON.parse(readFileSync(resolve(testDir, "../lib/i18n/vi.json"), "utf8")) as {
  finalReviewVisual: Record<string, string>;
  finalReviewStates: Record<string, string>;
  finalReviewTabs: Record<string, string>;
  finalReviewActions: Record<string, string>;
  finalReviewHeader: Record<string, string>;
};

assert.match(apiSource, /export async function createOcrJob/, "API must expose createOcrJob");
assert.match(apiSource, /export async function fetchOcrSummary/, "API must expose fetchOcrSummary");
assert.match(apiSource, /export async function approveOcrVisual/, "API must expose approveOcrVisual");
assert.match(pageSource, /FinalReviewVisualCheckpoint/, "Final Review must mount visual checkpoint");
assert.match(pageSource, /maxAttempts:\s*900/, "OCR poll must allow ~30 minutes on CPU Paddle");
assert.match(apiSource, /sample_fps:\s*1\.0/, "OCR create should default to 1 fps for hard-sub pilot");
assert.match(pageSource, /handleApproveVisual/, "Final Review must run visual approve");
assert.match(
  visualSource,
  /analyzeBusy|approveBusy/,
  "Visual CTAs must use separate analyze/approve busy flags so Approve is not stuck on Analyzing"
);
{
  const prepVisual = pageSource.match(
    /final-review-side[\s\S]*?<FinalReviewVisualCheckpoint[\s\S]*?\/>/
  )?.[0] ?? "";
  assert.ok(prepVisual.includes('presentation="prep"'), "Prep layout must mount Visual checkpoint with presentation=prep");
  assert.match(prepVisual, /analyzeBusy=\{ocrBusy\}/, "Prep Visual checkpoint must busy only on OCR, not on Start-render actionBusy");
  assert.doesNotMatch(
    prepVisual,
    /analyzeBusy=\{ocrBusy \|\| actionBusy\}/,
    "Prep must not show Analyzing OCR while Start first render is pending"
  );
}
assert.ok(en.finalReviewVisual.approving.length > 0);
assert.ok(vi.finalReviewVisual.approving.length > 0);
assert.match(pageSource, /handleStartFirstRender/, "Empty Final Review must start first render");
assert.match(
  pageSource,
  /announceRenderLifecycle|renderQueued[\s\S]{0,220}tone:\s*"info"/,
  "Start/rerender must toast when the render job is queued (pre-render)"
);
assert.match(
  pageSource,
  /notify\(\{[\s\S]*renderInProgress[\s\S]*tone:\s*"info"[\s\S]*durationMs:\s*null/,
  "Start/rerender must toast sticky progress while the render job runs"
);
assert.match(
  pageSource,
  /notify\(\{[\s\S]*renderSuccess[\s\S]*tone:\s*"success"/,
  "Start/rerender must toast when the first render completes"
);
assert.match(
  pageSource,
  /const queued = t\("finalReviewStates\.renderQueued"\)[\s\S]*notify\(\{ id: `\$\{noticeId\}-queued`/,
  "Queued toast must use the renderQueued copy with a distinct notice id"
);
assert.doesNotMatch(
  pageSource,
  /setOcrMessage\(t\("finalReviewStates\.renderQueued"\)|setActionMessage\(queued\)/,
  "Render queued copy must not appear as inline OCR/action message — toast only"
);
assert.match(
  pageSource,
  /renderFailed[\s\S]*tone:\s*"error"/,
  "Start/rerender must toast when the render job fails"
);
{
  const startRenderFn = pageSource.match(
    /async function handleStartFirstRender\(\)[\s\S]*?(?=async function handleRerender\(\))/
  )?.[0] ?? "";
  const rerenderFn = pageSource.match(
    /async function handleRerender\(\)[\s\S]*?(?=async function handleAnalyzeOcr\(\))/
  )?.[0] ?? "";
  assert.ok(startRenderFn.length > 0 && rerenderFn.length > 0, "Must locate start/rerender handlers");
  assert.doesNotMatch(startRenderFn, /setError\((?!null\))/, "Start first render failures must toast only, not inline error");
  assert.doesNotMatch(rerenderFn, /setError\((?!null\))/, "Rerender failures must toast only, not inline error");
}
assert.ok(en.finalReviewStates.renderInProgress.length > 0);
assert.ok(vi.finalReviewStates.renderInProgress.length > 0);
assert.match(
  pageSource,
  /async function handleRerender\(\)[\s\S]*?(?:pollAnalyzeJobUntilSettled|pollRenderJob)[\s\S]*?loadData\(\)/,
  "Rerender must poll job and reload latest render so Warnings panel is not stale"
);
assert.match(pageSource, /fr-rail/, "Final Review must use tabbed rail");
assert.match(pageSource, /railTab/, "Final Review must keep rail tab state");
assert.match(pageSource, /fr-workspace/, "Final Review must use cinema workspace layout");
assert.match(
  cssSource,
  /\.fr-workspace\s*\{[^}]*grid-template-columns:\s*minmax\(0,\s*1fr\)\s+minmax\(380px,\s*440px\)/,
  "Final Review rail must be wider (~400–440px) so checklist/warnings are readable"
);
assert.match(actionsSource, /fr-decision-bar/, "Decision actions must render sticky decision bar");
assert.match(
  pageSource,
  /railTab\s*===\s*["']review["'][\s\S]*?FinalReviewActions|FinalReviewActions[\s\S]*?railTab\s*===\s*["']review["']/,
  "Decision bar must mount only on Review tab (Phase 1 focus)"
);
assert.doesNotMatch(
  headerSource,
  /onApprove|onPublishReady|approveExport|markPublishReady/,
  "Header must not duplicate Approve / Publish-ready CTAs"
);
assert.match(headerSource, /fr-topbar--compact|fr-topbar__status/, "Header must use compact Phase 1 status strip");
assert.match(headerSource, /fr-topbar__actions/, "Header tools must stay visible in a compact action row");
assert.doesNotMatch(headerSource, /fr-topbar__more|<details/, "Header must not hide tools in a More menu");
assert.match(headerSource, /onRerender|rerender/, "Rerender must stay a visible header action");
assert.doesNotMatch(
  headerSource,
  /transcript-editor|\/publish|review-board/,
  "Cross-page nav (Transcript / Publish / Board) must live in Operator shell topbar, not Final Review header"
);
assert.doesNotMatch(
  pageSource,
  /final-review-preheader__actions/,
  "Prep preheader must not duplicate shell topbar Transcript link"
);
assert.doesNotMatch(
  headerSource,
  /fr-topbar__gates[\s\S]*fr-gate[\s\S]*fr-gate/,
  "Header must not show two always-visible readiness gates"
);
assert.match(headerSource, /fr-chip/, "Header must show compact meta chips");
assert.match(cssSource, /aspect-ratio:\s*16\s*\/\s*9/, "Compare panes must use landscape 16:9");
assert.doesNotMatch(cssSource, /aspect-ratio:\s*9\s*\/\s*16/, "Compare panes must not force portrait 9:16");
assert.match(statesSource, /startRender/, "Empty state must expose start render CTA");
assert.doesNotMatch(statesSource, /onAnalyzeOcr/, "Analyze OCR belongs on the Visual Clean side card, not embedded in First Render");
assert.match(statesSource, /resolveFinalReviewPrepFocus|prepFocus|ocrPrep/, "Prep empty state must resolve OCR-first vs render focus");
assert.match(
  statesSource,
  /is-active|prepFocus\s*===\s*["']ocr["']|prepFocus\s*===\s*["']render["']/,
  "Prep step rail must mark the active OCR or render step"
);
assert.match(
  statesSource,
  /prepFocus\s*===\s*["']render["'][\s\S]*primary|renderIsPrimary[\s\S]*primary/,
  "Start first render must be primary only after OCR prep focus moves to render"
);
assert.match(
  pageSource,
  /FinalReviewEmptyState[\s\S]*prepFocus=\{|prepFocus=\{resolveFinalReviewPrepFocus/,
  "Prep page must pass prepFocus from OCR summary into empty state"
);
assert.match(
  visualSource,
  /is-prep-focus|presentation === "prep"/,
  "Visual Clean prep card must emphasize Analyze OCR while OCR focus is active"
);
assert.match(
  en.finalReviewStates.emptyBody + en.finalReviewStates.emptyPrepHint,
  /Visual Clean|right/i,
  "Prep copy must point operators at Visual Clean on the right"
);
assert.match(
  en.transcriptEditorHeader.finalReviewShort,
  /Open Final Review/,
  "Transcript Final CTA must read as Open Final Review, not bare Final"
);
assert.match(
  statesSource,
  /final-review-empty final-review-prep-panel/,
  "Empty state must use the prep studio panel shell"
);
assert.match(statesSource, /final-review-empty__step-rail/, "Empty state must show a numbered prep step rail");
assert.match(statesSource, /final-review-empty__secondary/, "Empty state secondary nav must be a compact link row");
assert.match(
  statesSource,
  /WorkItemActionIcon[\s\S]*kind="process"|leadingIcon=\{<WorkItemActionIcon[\s\S]*kind="process"/,
  "Start render CTA must use the shared process icon"
);
assert.match(statesSource, /kind="transcript"/, "Prep Transcript link must use the shared transcript icon");
assert.match(statesSource, /kind="details"/, "Prep Review Board link must use the shared details icon");
assert.match(
  visualSource,
  /leadingIcon=\{<WorkItemActionIcon[\s\S]*kind="recheck"/,
  "Analyze OCR must use the shared recheck icon"
);
assert.match(
  visualSource,
  /leadingIcon=\{<WorkItemActionIcon[\s\S]*kind="approve"/,
  "Approve visual must use the shared approve icon"
);
assert.doesNotMatch(
  statesSource,
  /className="state-panel final-review-empty"/,
  "Empty state must leave the generic state-panel shell"
);
assert.match(
  pageSource,
  /final-review-preheader[\s\S]*fr-topbar__kicker|final-review-preheader--studio/,
  "Prep preheader must use studio kicker grammar"
);
assert.match(
  cssSource,
  /\.final-review--prep[\s\S]*\.final-review-prep-panel/,
  "Prep Final Review must style empty + visual panels as soft studio shells"
);
assert.match(
  cssSource,
  /\.final-review-empty__step-rail/,
  "Prep empty state must style the numbered step rail"
);
assert.match(visualSource, /warnNoHardsub|warnCleanSkipped/, "Visual checkpoint must label no-hardsub warnings");
assert.match(
  visualSource,
  /priorCleanedKept|clean_skipped_no_hardsub/,
  "Visual checkpoint must not show green cleanedReady when this run skipped clean"
);
assert.match(
  visualSource,
  /showAllEvents|EVENTS_PREVIEW|slice\(0,\s*3\)/,
  "Visual events list must default to a short preview"
);
assert.doesNotMatch(
  visualSource,
  /visual_approved[\s\S]*pill good[\s\S]*approved/,
  "Visual rail must not duplicate Visual approved as a meta pill when CTA already shows it"
);
assert.match(
  pageSource,
  /analyzeNoOutput|clean_skipped_no_hardsub|no_hardsub_detected/,
  "Final Review must not claim analyzeSuccess when OCR produced no new cleaned video"
);
assert.ok(en.finalReviewVisual.warnNoHardsub.length > 0);
assert.ok(vi.finalReviewVisual.warnCleanSkipped.length > 0);
assert.ok(en.finalReviewVisual.analyzeNoOutput.length > 0);
assert.ok(vi.finalReviewVisual.priorCleanedKept.length > 0);
assert.ok(en.finalReviewHeader.rerender.length > 0 && en.finalReviewHeader.rerender.length <= 12);
assert.ok(vi.finalReviewHeader.transcriptEditor.length > 0 && vi.finalReviewHeader.transcriptEditor.length <= 12);
assert.ok(en.finalReviewHeader.publishDraft.length <= 10);
assert.ok(vi.finalReviewHeader.reviewBoard.length <= 12);
assert.ok(en.finalReviewVisual.showAllEvents.length > 0);
assert.ok(vi.finalReviewVisual.showAllEvents.length > 0);
assert.ok(en.finalReviewStates.startRender.length > 0);
assert.ok(en.finalReviewTabs.review.length > 0);
assert.ok(en.finalReviewActions.checklistProgress.length > 0);
assert.ok(vi.finalReviewVisual.analyzeOcr.length > 0);
assert.ok(vi.finalReviewStates.startRender.length > 0);
assert.ok(vi.finalReviewTabs.review.length > 0);
assert.ok(vi.finalReviewActions.checklistProgress.length > 0);

console.log("final-review visual checkpoint tests passed");
