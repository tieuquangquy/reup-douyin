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
  "OpsConsoleShell",
  "PageShell",
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
assert.match(apiSource, /\/ops\/pipeline-dashboard/, "API client must call the aggregation endpoint");
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

console.log("reup pipeline dashboard source tests passed");
