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
};
const vi = JSON.parse(readFileSync(resolve(testDir, "../lib/i18n/vi.json"), "utf8")) as {
  finalReviewVisual: Record<string, string>;
  finalReviewStates: Record<string, string>;
  finalReviewTabs: Record<string, string>;
  finalReviewActions: Record<string, string>;
};

assert.match(apiSource, /export async function createOcrJob/, "API must expose createOcrJob");
assert.match(apiSource, /export async function fetchOcrSummary/, "API must expose fetchOcrSummary");
assert.match(apiSource, /export async function approveOcrVisual/, "API must expose approveOcrVisual");
assert.match(pageSource, /FinalReviewVisualCheckpoint/, "Final Review must mount visual checkpoint");
assert.match(pageSource, /maxAttempts:\s*900/, "OCR poll must allow ~30 minutes on CPU Paddle");
assert.match(apiSource, /sample_fps:\s*1\.0/, "OCR create should default to 1 fps for hard-sub pilot");
assert.match(pageSource, /handleAnalyzeOcr/, "Final Review must run OCR analyze");
assert.match(pageSource, /handleStartFirstRender/, "Empty Final Review must start first render");
assert.match(
  pageSource,
  /async function handleRerender\(\)[\s\S]*?pollAnalyzeJobUntilSettled[\s\S]*?loadData\(\)/,
  "Rerender must poll job and reload latest render so Warnings panel is not stale"
);
assert.match(pageSource, /fr-rail/, "Final Review must use tabbed rail");
assert.match(pageSource, /railTab/, "Final Review must keep rail tab state");
assert.match(pageSource, /fr-workspace/, "Final Review must use cinema workspace layout");
assert.match(actionsSource, /fr-decision-bar/, "Decision actions must render sticky decision bar");
assert.doesNotMatch(
  headerSource,
  /onApprove|onPublishReady|approveExport|markPublishReady/,
  "Header must not duplicate Approve / Publish-ready CTAs"
);
assert.match(headerSource, /fr-topbar__gates|fr-gate/, "Header must show export readiness gates");
assert.match(headerSource, /fr-chip/, "Header must show compact meta chips");
assert.match(headerSource, /fr-topbar__tools/, "Header tools must sit in a dedicated strip");
assert.match(cssSource, /aspect-ratio:\s*16\s*\/\s*9/, "Compare panes must use landscape 16:9");
assert.doesNotMatch(cssSource, /aspect-ratio:\s*9\s*\/\s*16/, "Compare panes must not force portrait 9:16");
assert.match(statesSource, /startRender/, "Empty state must expose start render CTA");
assert.match(
  statesSource,
  /export function FinalReviewEmptyState\([\s\S]*?return \(\s*<div className="state-panel final-review-empty"/,
  "Empty state must render a panel div, not nest <main>"
);
assert.match(visualSource, /warnNoHardsub|warnCleanSkipped/, "Visual checkpoint must label no-hardsub warnings");
assert.ok(en.finalReviewVisual.warnNoHardsub.length > 0);
assert.ok(vi.finalReviewVisual.warnCleanSkipped.length > 0);
assert.ok(en.finalReviewStates.startRender.length > 0);
assert.ok(en.finalReviewTabs.review.length > 0);
assert.ok(en.finalReviewActions.checklistProgress.length > 0);
assert.ok(vi.finalReviewVisual.analyzeOcr.length > 0);
assert.ok(vi.finalReviewStates.startRender.length > 0);
assert.ok(vi.finalReviewTabs.review.length > 0);
assert.ok(vi.finalReviewActions.checklistProgress.length > 0);

console.log("final-review visual checkpoint tests passed");
