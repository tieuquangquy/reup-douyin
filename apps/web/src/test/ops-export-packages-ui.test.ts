/**
 * Export Packages index — Dispatch bay triage.
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
assert.match(page, /export-packages-page is-v4/, "Export Packages must use Dispatch bay shell v4");
assert.match(page, /export-packages-bay/, "Export Packages must render dispatch bay");
assert.match(page, /export-packages-bay__body/, "Export Packages must render bay body");
assert.doesNotMatch(page, /export-packages-page is-v3/, "Export Packages must retire v3 side-by-side bay");
assert.match(page, /export-packages-mix__donut/, "Export Packages must render donut plot");
assert.match(page, /export-packages-mix__legend/, "Export Packages must render mix legend");
assert.match(page, /export-packages-mix__signals/, "Export Packages must render mix signals panel");
assert.match(page, /publish_handoff_ids/, "Export Packages signals must use handoff ids authority");
assert.match(page, /opsExportPackages\.avgItemsPacked/, "Export Packages signals must include avg items metric");
assert.match(page, /handoffCount === 1 \? t\("opsExportPackages\.handoff"\)/, "Export Packages slip chips must pluralize handoff count");
assert.doesNotMatch(page, /key:\s*"ready"[\s\S]{0,220}?filter:\s*"READY_FOR_HANDOFF"/, "Export Packages signals must not echo Ready legend");
assert.doesNotMatch(en, /"readyForHandoffDetail":\s*"READY_FOR_HANDOFF/, "Export Packages copy must not leak READY_FOR_HANDOFF enum");
assert.match(en, /"avgItemsPacked"/, "en.json must define avg items signal");
assert.match(vi, /"avgItemsPacked"/, "vi.json must define avg items signal");
assert.match(page, /conic-gradient/, "Export Packages donut must use conic-gradient");
assert.match(page, /packageStageClass/, "Export Packages must share stage tokens across chart and slips");
assert.doesNotMatch(page, /export-packages-mix__meters|export-packages-mix__track/, "Export Packages must retire pipeline meters");
assert.doesNotMatch(page, /export-packages-command/, "Export Packages must fold command into bay rail");
assert.match(page, /export-packages-manifest/, "Export Packages must render manifesto list");
assert.match(page, /export-packages-manifest__slip/, "Export Packages must render manifesto slips");
assert.match(page, /export-packages-rail__link|export-packages-dock__link/, "Export Packages must host triage links on the bay");
assert.doesNotMatch(page, /export-packages-stages/, "Export Packages must retire chip stage strip");
assert.doesNotMatch(page, /tone-\$\{statusTone\(item\.status\)\}/, "Export Packages must not paint status chips via global statusTone");
assert.doesNotMatch(page, /export-packages-spectrum|export-packages-ledger|publish-drafts-spectrum/, "Export Packages must retire Drafts clone chrome");
assert.doesNotMatch(page, /ops-export-page|ops-export-kpis|ExportKpi/, "Export Packages must retire Ops KPI chrome");
assert.doesNotMatch(page, /ops-export-toolbar/, "Export Packages must retire the detached triage toolbar");
assert.doesNotMatch(page, /ops-export-row is-head/, "Export Packages must retire the 6-column sheet head");
assert.match(page, /export-packages-attention/, "Export Packages must surface attention");
assert.match(page, /FAILED_NEEDS_ATTENTION/, "Attention must derive from FAILED_NEEDS_ATTENTION");
assert.match(page, /needsAttention\.length > 0/, "Attention banner must only render when items exist");
assert.match(page, /export-packages-footnote|noAutoPublish/, "Export Packages must footnote honesty");
assert.match(page, /fetchExportPackages/, "Export Packages must keep list authority");
assert.match(page, /\/selection\/reup-queue/, "Bay must link Reup Queue");
assert.match(page, /\/publishing\/publish-handoffs/, "Bay must link Publish Handoffs");
assert.match(page, /\/publishing\/export-packages\/\$\{/, "Slips must deep-link package detail");
assert.match(page, /useEffect\(\(\) => \{\s*void load\(\);\s*\},\s*\[t\]\)/s, "Load effect must stay on stable t dep");
assert.doesNotMatch(page, /OpsSummaryCards|OpsItemCard|PageShell/, "Must not use retired shells/cards");
assert.doesNotMatch(page, /operator-quick-grid|operator-quick-card/, "Must not use quick-card grid");
assert.doesNotMatch(page, /cookie|secret|token/i, "Must not expose secrets");

assert.match(css, /\/\* Export Packages Dispatch bay v4/, "CSS must define Export Packages Dispatch bay v4 block");
assert.match(css, /\.export-packages-page\.is-v4/, "CSS must define Export Packages page shell v4");
assert.match(css, /\.export-packages-bay/, "CSS must define dispatch bay");
assert.match(css, /\.export-packages-bay__body/, "CSS must define bay body");
assert.match(css, /bay__body[^{]*\{[^}]*grid-template-columns:\s*minmax\(0,\s*1fr\)/, "CSS must stack bay body in one column");
assert.doesNotMatch(css, /\.export-packages-page\.is-v3/, "CSS must retire v3 page shell");
assert.match(css, /\.export-packages-mix__donut/, "CSS must define donut");
assert.match(css, /\.export-packages-mix__legend/, "CSS must define mix legend");
assert.match(css, /\.export-packages-mix__signals/, "CSS must define mix signals panel");
assert.match(css, /--ep-stage-ready:\s*#2f8f6f/, "CSS must define Ready stage token");
assert.match(css, /--ep-stage-handed:\s*#4f6fbf/, "CSS must define Handoff stage token");
assert.match(css, /\.export-packages-chip\.is-ready/, "CSS must paint Ready chips from stage token");
assert.match(css, /\.export-packages-chip\.is-handed/, "CSS must paint Handoff chips from stage token");
assert.match(css, /\.export-packages-manifest__slip/, "CSS must define manifesto slips");
assert.doesNotMatch(css, /\.export-packages-stages/, "CSS must retire chip stage strip");
assert.doesNotMatch(css, /\.export-packages-mix__meters/, "CSS must retire pipeline meters");
assert.doesNotMatch(css, /\.export-packages-page\.is-v2/, "CSS must retire v2 page shell");
assert.match(css, /\.export-packages-chip\s*\{[^}]*font-weight:\s*400/, "Export chips must not use bold weight");
assert.match(css, /\.export-packages-attention/, "CSS must define attention banner");
assert.match(css, /\.export-packages-footnote/, "CSS must define footnote");
assert.doesNotMatch(css, /\.export-packages-spectrum\.is-v7/, "CSS must retire spectrum poster");
assert.doesNotMatch(css, /\.export-packages-ledger/, "CSS must retire ledger table");

assert.match(en, /"opsExportPackages"/, "en.json must define opsExportPackages");
assert.match(vi, /"opsExportPackages"/, "vi.json must define opsExportPackages");
assert.match(pkg, /ops-export-packages-ui\.test\.ts/, "package.json must run export packages UI test");
assert.match(pkg, /export-packages-index-polish\.test\.ts/, "package.json must run export packages polish test");

console.log("ops-export-packages-ui tests passed");
