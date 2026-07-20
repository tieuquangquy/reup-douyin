/**
 * Ops Publish Control — assignment + hold plane (scoped UI, single shell, mutates preserved).
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const testDir = dirname(fileURLToPath(import.meta.url));
const webSrc = resolve(testDir, "..");

const page = readFileSync(resolve(webSrc, "components/publish-control/PublishControlPlanePage.tsx"), "utf8");
const route = readFileSync(resolve(webSrc, "app/ops/publish-control/page.tsx"), "utf8");
const css = readFileSync(resolve(webSrc, "app/globals.css"), "utf8");
const en = readFileSync(resolve(webSrc, "lib/i18n/en.json"), "utf8");
const vi = readFileSync(resolve(webSrc, "lib/i18n/vi.json"), "utf8");
const pkg = readFileSync(resolve(webSrc, "../package.json"), "utf8");
const noDup = readFileSync(resolve(webSrc, "test/no-duplicate-header.test.ts"), "utf8");

assert.match(page, /OpsConsoleShell/, "Publish Control must own OpsConsoleShell");
assert.match(page, /TopbarRefreshButton/, "Publish Control must put Refresh in the Topbar");
assert.doesNotMatch(page, /control-header/, "Publish Control must not render nested control-header");
assert.doesNotMatch(route, /OpsConsoleShell/, "Route publish-control must not double-wrap OpsConsoleShell");
assert.match(page, /ops-control-page/, "Publish Control must use scoped ops-control-page shell");
assert.match(page, /ops-control-kpis/, "Publish Control must render KPI band");
assert.match(page, /ops-control-kpi/, "Publish Control must use scoped KPI cards");
assert.match(page, /ops-control-freshness|generated_at/, "Publish Control must surface queue freshness");
assert.match(page, /fetchPublishControlQueue/, "Publish Control must keep queue authority");
assert.match(page, /fetchRoutingRules/, "Publish Control must keep routing-rules authority");
assert.match(page, /assignPublishDraft/, "Publish Control must keep assign mutate");
assert.match(page, /unassignPublishDraft/, "Publish Control must keep unassign mutate");
assert.match(page, /bulkAssignPublishDrafts/, "Publish Control must keep bulk assign mutate");
assert.match(page, /updatePlatformAccount/, "Publish Control must keep hold mutate");
assert.match(page, /ops-control-toolbar|ops-control-actions/, "Triage links must sit in toolbar");
assert.match(page, /\/ops\/accounts/, "Publish Control must deep-link accounts");
assert.match(page, /\/ops\/routing-rules/, "Publish Control must deep-link routing rules");
assert.match(page, /ops-control-accounts|ops-control-account/, "Publish Control must render accounts sheet");
assert.match(page, /ops-control-queue|ops-control-draft/, "Publish Control must render draft routing sheet");
assert.match(page, /ops-control-bulk/, "Publish Control must keep bulk assign bar");
assert.match(page, /ops-control-attention|needs_attention/, "Publish Control must surface attention");
assert.match(page, /ops-control-footnote|assignmentAuthorityFootnote/, "Publish Control must footnote authority");
assert.doesNotMatch(page, /health-table/, "Publish Control must not use health-table");
assert.doesNotMatch(page, /control-overview-grid/, "Publish Control must leave legacy control-overview-grid");
assert.doesNotMatch(page, /account-card/, "Publish Control must not use account-card grid");

assert.match(css, /\.ops-control-page/, "CSS must define Publish Control page shell");
assert.match(css, /\.ops-control-kpis/, "CSS must define Publish Control KPI grid");
assert.match(css, /\.ops-control-chip\s*\{[^}]*font-weight:\s*400/, "Control chips must not use bold weight");
assert.match(css, /\.ops-control-main\.has-attention/, "CSS must support split when attention is present");

assert.match(en, /"metricsGenerated"|"assignmentAuthorityFootnote"|"triage"|"status"/, "en.json must define Control redesign labels");
assert.match(vi, /"metricsGenerated"|"assignmentAuthorityFootnote"|"triage"|"status"/, "vi.json must define Control redesign labels");
assert.match(pkg, /ops-publish-control-ui\.test\.ts/, "package.json must run ops-publish-control-ui test");
assert.match(noDup, /PublishControlPlanePage|publish-control/, "no-duplicate-header must cover Publish Control shell ownership");

console.log("ops-publish-control-ui tests passed");
