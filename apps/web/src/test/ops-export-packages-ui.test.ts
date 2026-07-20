/**
 * Export Packages index — triage sheet (Assets/Risk/Pipeline contract).
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const testDir = dirname(fileURLToPath(import.meta.url));
const webSrc = resolve(testDir, "..");

const page = readFileSync(resolve(webSrc, "components/operator-routes/ExportPackagesIndexPage.tsx"), "utf8");
const css = readFileSync(resolve(webSrc, "app/globals.css"), "utf8");
const en = readFileSync(resolve(webSrc, "lib/i18n/en.json"), "utf8");
const vi = readFileSync(resolve(webSrc, "lib/i18n/vi.json"), "utf8");
const pkg = readFileSync(resolve(webSrc, "../package.json"), "utf8");

assert.match(page, /OperatorStudioShell/, "Export Packages must keep OperatorStudioShell");
assert.match(page, /TopbarRefreshButton/, "Export Packages must put Refresh in the Topbar");
assert.match(page, /ops-export-page/, "Export Packages must use scoped ops-export-page shell");
assert.match(page, /ops-export-freshness|loadedAt/, "Export Packages must surface freshness");
assert.match(page, /ops-export-kpis/, "Export Packages must render scoped KPI band");
assert.match(page, /ops-export-kpi/, "Export Packages must use scoped KPI cards");
assert.match(page, /ops-export-toolbar|ops-export-actions/, "Export Packages must render triage toolbar");
assert.match(page, /ops-export-sheet|ops-export-row/, "Export Packages must render list sheet");
assert.match(page, /ops-export-attention/, "Export Packages must surface attention");
assert.match(page, /FAILED_NEEDS_ATTENTION/, "Attention must derive from FAILED_NEEDS_ATTENTION");
assert.match(page, /attention\.length > 0|needsAttention\.length > 0/, "Attention side must only render when items exist");
assert.match(page, /ops-export-footnote|readOnlyFootnote|noAutoPublish/, "Export Packages must footnote honesty");
assert.match(page, /fetchExportPackages/, "Export Packages must keep list authority");
assert.match(page, /\/selection\/reup-queue/, "Toolbar must link Reup Queue");
assert.match(page, /\/publishing\/publish-handoffs/, "Toolbar must link Publish Handoffs");
assert.match(page, /\/publishing\/export-packages\/\$\{/, "Rows must deep-link package detail");
assert.doesNotMatch(page, /OpsSummaryCards/, "Must not use OpsSummaryCards");
assert.doesNotMatch(page, /OpsItemCard/, "Must not use OpsItemCard");
assert.doesNotMatch(page, /OpsStatePanel/, "Must not use OpsStatePanel");
assert.doesNotMatch(page, /operator-quick-grid/, "Must not use operator-quick-grid");
assert.doesNotMatch(page, /PageShell/, "Must not nest PageShell");
assert.doesNotMatch(page, /cookie|secret|token/i, "Must not expose secrets");

assert.match(css, /\.ops-export-page/, "CSS must define Export page shell");
assert.match(css, /\.ops-export-kpis/, "CSS must define Export KPI grid");
assert.match(css, /\.ops-export-chip\s*\{[^}]*font-weight:\s*400/, "Export chips must not use bold weight");
assert.match(css, /\.ops-export-main\.has-attention/, "CSS must support split when attention is present");
assert.match(css, /\.ops-export-footnote/, "CSS must define footnote");

assert.match(en, /"opsExportPackages"/, "en.json must define opsExportPackages");
assert.match(vi, /"opsExportPackages"/, "vi.json must define opsExportPackages");
assert.match(pkg, /ops-export-packages-ui\.test\.ts/, "package.json must run export packages UI test");

console.log("ops-export-packages-ui tests passed");
