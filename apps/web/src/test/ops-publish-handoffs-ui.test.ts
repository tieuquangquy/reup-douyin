/**
 * Publish Handoffs index — triage sheet (Assets/Risk/Pipeline contract).
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const testDir = dirname(fileURLToPath(import.meta.url));
const webSrc = resolve(testDir, "..");

const page = readFileSync(resolve(webSrc, "components/operator-routes/PublishHandoffsIndexPage.tsx"), "utf8");
const css = readFileSync(resolve(webSrc, "app/globals.css"), "utf8");
const en = readFileSync(resolve(webSrc, "lib/i18n/en.json"), "utf8");
const vi = readFileSync(resolve(webSrc, "lib/i18n/vi.json"), "utf8");
const pkg = readFileSync(resolve(webSrc, "../package.json"), "utf8");

assert.match(page, /OperatorStudioShell/, "Publish Handoffs must keep OperatorStudioShell");
assert.match(page, /TopbarRefreshButton/, "Publish Handoffs must put Refresh in the Topbar");
assert.match(page, /ops-handoffs-page/, "Publish Handoffs must use scoped ops-handoffs-page shell");
assert.match(page, /ops-handoffs-freshness|loadedAt/, "Publish Handoffs must surface freshness");
assert.match(page, /ops-handoffs-kpis/, "Publish Handoffs must render scoped KPI band");
assert.match(page, /ops-handoffs-kpi/, "Publish Handoffs must use scoped KPI cards");
assert.match(page, /ops-handoffs-toolbar|ops-handoffs-actions/, "Publish Handoffs must render triage toolbar");
assert.match(page, /ops-handoffs-sheet|ops-handoffs-row/, "Publish Handoffs must render list sheet");
assert.match(page, /ops-handoffs-attention/, "Publish Handoffs must surface attention");
assert.match(page, /FAILED_NEEDS_ATTENTION/, "Attention must derive from FAILED_NEEDS_ATTENTION");
assert.match(page, /attention\.length > 0|needsAttention\.length > 0/, "Attention side must only render when items exist");
assert.match(page, /ops-handoffs-footnote|noPlatformApi|readOnlyFootnote/, "Handoffs must footnote no platform API");
assert.match(page, /fetchPublishHandoffs/, "Publish Handoffs must keep list authority");
assert.match(page, /READY_FOR_OPERATOR|ACCEPTED/, "Ready KPI must count READY_FOR_OPERATOR / ACCEPTED");
assert.match(page, /\/publishing\/export-packages/, "Toolbar or rows must link Export Packages");
assert.match(page, /\/selection\/reup-queue/, "Toolbar must link Reup Queue");
assert.match(page, /\/publishing\/publish-handoffs\/\$\{/, "Rows must deep-link handoff detail");
assert.doesNotMatch(page, /OpsSummaryCards/, "Must not use OpsSummaryCards");
assert.doesNotMatch(page, /OpsItemCard/, "Must not use OpsItemCard");
assert.doesNotMatch(page, /OpsStatePanel/, "Must not use OpsStatePanel");
assert.doesNotMatch(page, /Publish automation/, "Must not fake Publish automation KPI");
assert.doesNotMatch(page, /operator-quick-grid/, "Must not use operator-quick-grid");
assert.doesNotMatch(page, /PageShell/, "Must not nest PageShell");
assert.doesNotMatch(page, /cookie|secret|token/i, "Must not expose secrets");

assert.match(css, /\.ops-handoffs-page/, "CSS must define Handoffs page shell");
assert.match(css, /\.ops-handoffs-kpis/, "CSS must define Handoffs KPI grid");
assert.match(css, /\.ops-handoffs-chip\s*\{[^}]*font-weight:\s*400/, "Handoffs chips must not use bold weight");
assert.match(css, /\.ops-handoffs-main\.has-attention/, "CSS must support split when attention is present");
assert.match(css, /\.ops-handoffs-footnote/, "CSS must define footnote");

assert.match(en, /"opsPublishHandoffs"/, "en.json must define opsPublishHandoffs");
assert.match(vi, /"opsPublishHandoffs"/, "vi.json must define opsPublishHandoffs");
assert.match(pkg, /ops-publish-handoffs-ui\.test\.ts/, "package.json must run handoffs UI test");

console.log("ops-publish-handoffs-ui tests passed");
