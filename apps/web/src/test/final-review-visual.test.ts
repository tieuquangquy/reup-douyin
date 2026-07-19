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
assert.ok(en.finalReviewVisual.approving.length > 0);
assert.ok(vi.finalReviewVisual.approving.length > 0);
assert.match(pageSource, /handleStartFirstRender/, "Empty Final Review must start first render");
assert.match(
  pageSource,
  /async function handleRerender\(\)[\s\S]*?pollAnalyzeJobUntilSettled[\s\S]*?loadData\(\)/,
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
  /fr-topbar__gates[\s\S]*fr-gate[\s\S]*fr-gate/,
  "Header must not show two always-visible readiness gates"
);
assert.match(headerSource, /fr-chip/, "Header must show compact meta chips");
assert.match(cssSource, /aspect-ratio:\s*16\s*\/\s*9/, "Compare panes must use landscape 16:9");
assert.doesNotMatch(cssSource, /aspect-ratio:\s*9\s*\/\s*16/, "Compare panes must not force portrait 9:16");
assert.match(statesSource, /startRender/, "Empty state must expose start render CTA");
assert.match(
  statesSource,
  /export function FinalReviewEmptyState\([\s\S]*?return \(\s*<div className="state-panel final-review-empty"/,
  "Empty state must render a panel div, not nest <main>"
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
