/**
 * Ops Publish Health — analytics dashboard (scoped UI, single shell, feedback mutate).
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const testDir = dirname(fileURLToPath(import.meta.url));
const webSrc = resolve(testDir, "..");

const page = readFileSync(resolve(webSrc, "components/publish-health/PublishHealthDashboardPage.tsx"), "utf8");
const route = readFileSync(resolve(webSrc, "app/ops/publish-health/page.tsx"), "utf8");
const css = readFileSync(resolve(webSrc, "app/globals.css"), "utf8");
const en = readFileSync(resolve(webSrc, "lib/i18n/en.json"), "utf8");
const vi = readFileSync(resolve(webSrc, "lib/i18n/vi.json"), "utf8");
const pkg = readFileSync(resolve(webSrc, "../package.json"), "utf8");
const noDup = readFileSync(resolve(webSrc, "test/no-duplicate-header.test.ts"), "utf8");

assert.match(page, /OpsConsoleShell/, "Publish Health must own OpsConsoleShell");
assert.match(page, /TopbarRefreshButton/, "Publish Health must put Refresh in the Topbar");
assert.doesNotMatch(page, /health-header/, "Publish Health must not render a nested page header");
assert.doesNotMatch(route, /OpsConsoleShell/, "Route publish-health must not double-wrap OpsConsoleShell");
assert.match(page, /ops-ph-page/, "Publish Health must use scoped ops-ph-page shell");
assert.match(page, /ops-ph-kpis/, "Publish Health must render KPI band");
assert.match(page, /ops-ph-kpi/, "Publish Health must use scoped KPI cards");
assert.match(page, /ops-ph-freshness|generated_at/, "Publish Health must surface snapshot freshness");
assert.match(page, /fetchPublishHealthDashboard/, "Publish Health must keep dashboard authority");
assert.match(page, /submitOperatorFeedback/, "Publish Health must keep feedback mutate");
assert.match(page, /windowValue|AnalyticsWindow/, "Publish Health must keep window filter");
assert.match(page, /ops-ph-toolbar/, "Publish Health must render toolbar");
assert.match(page, /\/ops\/reconciliation/, "Publish Health must deep-link reconciliation");
assert.match(page, /\/ops\/accounts/, "Publish Health must deep-link accounts");
assert.match(page, /ops-ph-sheet|ops-ph-account/, "Publish Health must render account health sheet");
assert.match(page, /ops-ph-queue|action_queue/, "Publish Health must surface operator queue");
assert.match(page, /ops-ph-feedback|feedback-form|handleFeedbackSubmit/, "Publish Health must keep feedback form");
assert.match(page, /pipeline_feedback|ops-ph-pipeline/, "Publish Health must keep pipeline hints");
assert.doesNotMatch(page, /health-overview-grid/, "Publish Health must leave shared health-overview-grid");
assert.doesNotMatch(page, /health-table/, "Publish Health must not use health-table");
assert.doesNotMatch(page, /<OpsMetricCard/, "Publish Health must not use shared OpsMetricCard");
assert.doesNotMatch(page, /<OpsPanel/, "Publish Health must not use shared OpsPanel");

assert.match(css, /\.ops-ph-page/, "CSS must define Publish Health page shell");
assert.match(css, /\.ops-ph-kpis/, "CSS must define Publish Health KPI grid");
assert.match(css, /\.ops-ph-sheet|\.ops-ph-row/, "CSS must define Publish Health sheets");
assert.match(css, /\.ops-ph-feedback/, "CSS must define feedback form styles");

assert.match(en, /"pageTitle"|"successRate"|"saveFeedback"|"selectPublication"/, "en.json must define Publish Health labels");
assert.match(vi, /"pageTitle"|"successRate"|"saveFeedback"|"selectPublication"/, "vi.json must define Publish Health labels");

assert.match(pkg, /ops-publish-health-ui\.test\.ts/, "package.json must run ops-publish-health-ui test");
assert.match(noDup, /PublishHealthDashboardPage|publish-health/, "no-duplicate-header must cover Publish Health shell ownership");

console.log("ops-publish-health-ui tests passed");
