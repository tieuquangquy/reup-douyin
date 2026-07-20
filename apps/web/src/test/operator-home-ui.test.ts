/**
 * Operator Studio home — triage layout + P0–P2 enrichment contract.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const testDir = dirname(fileURLToPath(import.meta.url));
const webSrc = resolve(testDir, "..");

const page = readFileSync(resolve(webSrc, "components/operator-home/OperatorHomePage.tsx"), "utf8");
const freshnessStrip = readFileSync(resolve(webSrc, "components/operator-home/FreshnessStrip.tsx"), "utf8");
const nextWorkPanel = readFileSync(resolve(webSrc, "components/operator-home/NextWorkPanel.tsx"), "utf8");
const overview = readFileSync(resolve(webSrc, "components/operator-home/OverviewCards.tsx"), "utf8");
const continuePanel = readFileSync(resolve(webSrc, "components/operator-home/ContinuePanel.tsx"), "utf8");
const actionPanel = readFileSync(resolve(webSrc, "components/operator-home/ActionQueuePanel.tsx"), "utf8");
const activityPanel = readFileSync(resolve(webSrc, "components/operator-home/RecentActivityPanel.tsx"), "utf8");
const quickLaunch = readFileSync(resolve(webSrc, "components/operator-home/QuickLaunchGrid.tsx"), "utf8");
const state = readFileSync(resolve(webSrc, "lib/operatorHomeState.ts"), "utf8");
const css = readFileSync(resolve(webSrc, "app/globals.css"), "utf8");
const en = readFileSync(resolve(webSrc, "lib/i18n/en.json"), "utf8");
const vi = readFileSync(resolve(webSrc, "lib/i18n/vi.json"), "utf8");
const pkg = readFileSync(resolve(webSrc, "../package.json"), "utf8");

assert.match(page, /operator-home/, "Home must use operator-home shell");
assert.match(page, /OverviewCards/, "Home must render overview KPIs");
assert.match(page, /ContinuePanel/, "Home must render Continue panel");
assert.match(page, /ActionQueuePanel/, "Home must render Action queue");
assert.match(page, /QuickLaunchGrid/, "Home must render Quick launch");
assert.match(page, /RecentActivityPanel/, "Home must render Recent activity");
assert.match(page, /FreshnessStrip/, "Home must render FreshnessStrip");
assert.match(page, /NextWorkPanel/, "Home must render NextWorkPanel");

const continueIdx = page.indexOf("<ContinuePanel");
const actionIdx = page.indexOf("<ActionQueuePanel");
const nextIdx = page.indexOf("<NextWorkPanel");
assert.ok(continueIdx >= 0 && actionIdx >= 0, "Continue and Action panels must be present");
assert.ok(continueIdx < actionIdx, "Continue must appear before Action queue in DOM order");
assert.ok(nextIdx >= 0 && nextIdx < continueIdx, "Next work must appear before Continue");

assert.match(overview, /operator-home-kpis/, "Overview must use compact KPI strip class");
assert.doesNotMatch(overview, /StatusBadge/, "Overview KPIs must not use StatusBadge");
assert.doesNotMatch(overview, /operator-metric-card/, "Overview must leave tall metric cards");

assert.match(continuePanel, /operator-home-continue/, "Continue must use scoped sheet class");
assert.match(continuePanel, /operator-home-row|operator-home-continue__item/, "Continue must use sheet row markup");
assert.doesNotMatch(continuePanel, /StatusBadge/, "Continue rows must not use StatusBadge");

assert.match(actionPanel, /operator-home-actions/, "Action queue must use scoped sheet class");
assert.match(actionPanel, /operator-home-row|operator-home-actions__item/, "Action queue must use sheet row markup");
assert.match(actionPanel, /operator-home-num|operator-home-count/, "Action queue must show compact count pill");

assert.match(activityPanel, /operator-home-activity/, "Activity must use scoped sheet class");
assert.match(activityPanel, /operator-home-activity__trail/, "Activity must cluster timestamp + open action");
assert.match(activityPanel, /formatCompact|· /, "Activity must use compact time format");
assert.doesNotMatch(activityPanel, /StatusBadge/, "Activity rows must not use StatusBadge");

assert.match(quickLaunch, /operator-home-launch/, "Quick launch must use scoped launch class");
assert.doesNotMatch(quickLaunch, /operator-quick-grid/, "Quick launch must leave heavy 2-col card grid");
assert.doesNotMatch(quickLaunch, /operator-quick-card/, "Quick launch must leave heavy quick cards");

/* P0–P2 enrichment */
assert.match(page, /fetchPipelineDashboard/, "Home must fetch pipeline dashboard authority");
assert.match(page, /fetchDouyinExtensionStatus/, "Home must fetch Douyin extension status");
assert.match(freshnessStrip, /operator-home-freshness/, "Home must render freshness / pipeline status strip");
assert.match(freshnessStrip, /operator-home-freshness__inline/, "Freshness must use compact inline meta");
assert.match(freshnessStrip, /operator-home-freshness__action/, "Freshness actions must use prominent pill buttons");
assert.doesNotMatch(freshnessStrip, /operator-home-signal/, "Freshness must not use mini signal cards");
assert.match(nextWorkPanel, /operator-home-next/, "Home must render next-work triage");
assert.match(state, /buildNextWork|pickNextWork/, "State must build next-work from pipeline attention");
assert.match(state, /capture|reup_queue|export_package|publish_handoff/, "Metrics must cover capture/reup/export-handoff stages");
assert.match(state, /blocked_by_risk|blockers/, "Metrics must surface risk blockers");
assert.match(state, /succeeded_attempts|publishSuccess|publish_success/, "State must surface publish success window count");
assert.match(state, /opsConsoleBoundary|isOpsConsoleHref/, "Home state must classify Ops Console hrefs via boundary");
assert.doesNotMatch(state, /key: \"ops\"[\s\S]*href: \"\/ops\"/, "Quick launch must not include Ops Console entry");
assert.doesNotMatch(state, /href: blockedByRisk[^;]*\/ops\/risk|href: \"\/ops\/risk\"|href: \"\/ops\/jobs\"|href: \"\/ops\/health\"|href: \"\/ops\/reconciliation\"|href: \"\/ops\/publish-health\"/, "Home builders must not assign Ops Console monitor hrefs");
assert.match(page, /optimizationHint \?|optimizationHint &&/, "Optimization panel must only render when hint exists");

assert.match(css, /\.operator-home-kpis/, "CSS must define compact KPI strip");
assert.match(css, /\.operator-home-continue/, "CSS must define Continue sheet");
assert.match(css, /\.operator-home-actions/, "CSS must define Action sheet");
assert.match(css, /\.operator-home-activity/, "CSS must define Activity sheet");
assert.match(css, /\.operator-home-launch/, "CSS must define Quick launch chips");
assert.match(css, /\.operator-home-freshness/, "CSS must define freshness strip");
assert.match(css, /\.operator-home-freshness__inline/, "CSS must define compact inline freshness meta");
assert.match(css, /\.operator-home-freshness__action/, "CSS must define freshness action pills");
assert.doesNotMatch(css, /\.operator-home-signal\s*\{/, "CSS must drop heavy freshness signal cards");
assert.match(css, /\.operator-home-next/, "CSS must define next-work list");
assert.match(
  css,
  /\.operator-home-activity__item\s*\{[^}]*border-bottom|\.operator-home-row\s*\{[^}]*border-bottom/,
  "Sheet rows must use divider borders"
);

assert.match(en, /"nextWork"|"freshness"|"captureWaiting"|"reupQueue"|"exportHandoff"|"blockers"|"publishSuccess"|"extension"/, "en.json must define P0–P2 home labels");
assert.match(vi, /"nextWork"|"freshness"|"captureWaiting"|"reupQueue"|"exportHandoff"|"blockers"|"publishSuccess"|"extension"/, "vi.json must define P0–P2 home labels");

assert.match(pkg, /operator-home-ui\.test\.ts/, "package.json must run operator-home-ui test");

console.log("operator-home-ui tests passed");
