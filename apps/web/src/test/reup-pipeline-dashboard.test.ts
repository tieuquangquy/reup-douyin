import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const testDir = dirname(fileURLToPath(import.meta.url));
const webSrcDir = resolve(testDir, "..");
const pageSource = readFileSync(resolve(webSrcDir, "components/operator-routes/PipelineDashboardPage.tsx"), "utf8");
const routeSource = readFileSync(resolve(webSrcDir, "app/ops/pipeline/page.tsx"), "utf8");
const apiSource = readFileSync(resolve(webSrcDir, "lib/api.ts"), "utf8");
const operationsTypesSource = readFileSync(resolve(webSrcDir, "types/operations.ts"), "utf8");
const navSource = readFileSync(resolve(webSrcDir, "lib/navigationConfig.ts"), "utf8");
const globalCssSource = readFileSync(resolve(webSrcDir, "app/globals.css"), "utf8");

const requiredStageLabels = ["Capture", "Review", "Reup Queue", "Export Package", "Publish Handoff", "Publish progress"];
const requiredLinks = [
  "/ops/extensions/douyin/capture-inbox",
  "/selection/review-board",
  "/selection/reup-queue",
  "/publishing/export-packages",
  "/publishing/publish-handoffs",
  "/publishing/drafts",
  "/ops/publish-health",
  "/ops/publish-attempts",
  "/ops/reconciliation"
];
const requiredPrimitives = [
  "OperatorStudioShell",
  "OpsWorkflowContext",
  "OpsNextActionBanner",
  "OpsSummaryCards",
  "OpsDetailPanel",
  "OpsDetailSection",
  "OpsItemCard",
  "OpsStatePanel",
  "OpsMetadataList",
  "OpsActionRow"
];

assert.match(routeSource, /PipelineDashboardPage/, "The /ops/pipeline route must render PipelineDashboardPage");
assert.match(apiSource, /fetchPipelineDashboard/, "API client must expose fetchPipelineDashboard");
assert.match(apiSource, /\/pipeline-dashboard/, "API client must call the operator-accessible aggregation endpoint");
assert.doesNotMatch(apiSource, /\/ops\/pipeline-dashboard/, "Pipeline dashboard API must not stay under Ops-only /ops prefix");
assert.match(operationsTypesSource, /PipelineDashboardResponse/, "Operations types must include the pipeline dashboard response contract");
assert.match(operationsTypesSource, /PipelineStageKey/, "Operations types must define typed pipeline stage keys");
assert.match(navSource, /\/ops\/pipeline/, "Navigation config must expose the pipeline dashboard route");
assert.match(navSource, /nav\.pipelineDashboard/, "Navigation config must include a stable pipeline dashboard label key");

for (const primitive of requiredPrimitives) {
  assert.match(pageSource, new RegExp(primitive), `Pipeline Dashboard must reuse ${primitive}`);
}

for (const label of requiredStageLabels) {
  assert.match(pageSource, new RegExp(label), `Pipeline Dashboard must show the ${label} stage`);
}

for (const href of requiredLinks) {
  assert.match(pageSource, new RegExp(href.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")), `Pipeline Dashboard must link to ${href}`);
}

assert.match(pageSource, /Attention and blockers/, "Pipeline Dashboard must include an attention/blocker panel");
assert.match(pageSource, /Recent activity/, "Pipeline Dashboard must include recent activity");
assert.match(pageSource, /Quick actions and drill-downs/, "Pipeline Dashboard must include quick actions and drill-down links");
assert.match(pageSource, /PipelineStepMarker/, "Pipeline Dashboard must include stage-by-stage visual markers");
assert.doesNotMatch(pageSource, /cookie|secret|token/i, "Pipeline Dashboard UI must not expose secrets, cookies, or tokens");

assert.match(pageSource, /pipeline-dashboard/, "Pipeline Dashboard must use a scoped layout wrapper class");
assert.match(pageSource, /pipeline-stage-strip/, "Pipeline Dashboard must render stages in a compact stage strip");
assert.match(pageSource, /pipeline-split-panels/, "Pipeline Dashboard must place attention and activity in a split layout");
assert.match(pageSource, /pipeline-quick-link-grid/, "Pipeline Dashboard must use a compact quick-link grid");
assert.match(pageSource, /pipeline-list-row/, "Attention and activity must use compact list-row styling");
assert.doesNotMatch(pageSource, /PageShell/, "Pipeline Dashboard must not nest PageShell under OperatorStudioShell");
assert.match(pageSource, /TopbarRefreshButton/, "Pipeline Dashboard must put Refresh in the Topbar");
assert.match(globalCssSource, /\.pipeline-dashboard\s*\{/, "globals.css must define scoped .pipeline-dashboard styles");
assert.match(globalCssSource, /\.pipeline-stage-strip\s*\{/, "globals.css must style the stage strip");
assert.match(globalCssSource, /\.pipeline-quick-link-grid\s*\{/, "globals.css must style compact quick links");

console.log("reup pipeline dashboard source tests passed");
