/**
 * Export Packages index — Dispatch bay polish contract.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const testDir = dirname(fileURLToPath(import.meta.url));
const webSrc = resolve(testDir, "..");

const page = readFileSync(resolve(webSrc, "components/operator-routes/ExportPackagesIndexPage.tsx"), "utf8");
const cssFull = readFileSync(resolve(webSrc, "app/globals.css"), "utf8");
const en = readFileSync(resolve(webSrc, "lib/i18n/en.json"), "utf8");
const vi = readFileSync(resolve(webSrc, "lib/i18n/vi.json"), "utf8");

assert.match(page, /export-packages-page is-v4/, "Export Packages must use Dispatch bay shell v4");
assert.match(page, /export-packages-bay/, "Export Packages must wrap content in a dispatch bay");
assert.match(page, /export-packages-rail/, "Export Packages must render a top rail");
assert.match(page, /export-packages-rail__copy/, "Bay rail must keep a compact copy block");
assert.match(page, /opsExportPackages\.packageRecords/, "Rail must keep Package records title");
assert.match(page, /opsExportPackages\.loadedAt/, "Rail meta must use Loaded label instead of raw count");
assert.doesNotMatch(page, /rail__copy[\s\S]{0,420}?packageRecordsDetail/, "Rail must drop static durable-containers detail");
assert.doesNotMatch(page, /rail__copy[\s\S]{0,420}?status === "success" \? total/, "Rail must not repeat package total beside the donut");
assert.match(page, /export-packages-bay__body/, "Bay must expose a stacked body");
assert.match(page, /export-packages-mix/, "Export Packages must render a dispatch mix chart");
assert.match(page, /export-packages-mix__donut/, "Mix chart must expose a donut plot");
assert.match(page, /export-packages-mix__donut-core/, "Donut must expose a total core");
assert.match(page, /export-packages-mix__legend/, "Mix chart must expose a clickable legend");
assert.match(page, /export-packages-mix__signals/, "Mix band must expose a right-side signals panel");
assert.match(page, /export-packages-mix__signal/, "Signals panel must render individual signal tiles");
assert.match(page, /publish_handoff_ids/, "Linked handoffs signal must derive from publish_handoff_ids");
assert.match(page, /item_count/, "Items packed signal must derive from item_count");
assert.match(page, /opsExportPackages\.avgItemsPacked/, "Signals must expose avg items per package");
assert.match(page, /opsExportPackages\.draftPackagesDetail|filter:\s*"DRAFT"/, "Signals must surface Draft as a dispatch metric");
assert.match(page, /handoffCount === 1 \? t\("opsExportPackages\.handoff"\)/, "Slip handoff chip must pluralize via singular handoff key");
assert.doesNotMatch(
  page,
  /key:\s*"ready"[\s\S]{0,220}?filter:\s*"READY_FOR_HANDOFF"/,
  "Signals must not echo Ready-for-handoff legend counts",
);
assert.doesNotMatch(
  page,
  /key:\s*"attention"[\s\S]{0,280}?filter:\s*"FAILED_NEEDS_ATTENTION"/,
  "Signals must not echo Needs-attention legend counts",
);
assert.doesNotMatch(en, /"readyForHandoffDetail":\s*"READY_FOR_HANDOFF/, "en readyForHandoffDetail must not leak status enum");
assert.doesNotMatch(vi, /"readyForHandoffDetail":\s*"package READY_FOR_HANDOFF"/, "vi readyForHandoffDetail must not leak status enum");
assert.match(en, /"avgItemsPacked"/, "en.json must define avgItemsPacked");
assert.match(vi, /"avgItemsPacked"/, "vi.json must define avgItemsPacked");
assert.match(en, /"draftPackagesDetail"/, "en.json must define draftPackagesDetail");
assert.match(vi, /"draftPackagesDetail"/, "vi.json must define draftPackagesDetail");
assert.match(en, /"handoff":\s*"Handoff"/, "en.json must define singular handoff for slip chips");
assert.match(vi, /"handoff":/, "vi.json must define singular handoff for slip chips");
assert.match(page, /conic-gradient/, "Donut must paint slices with conic-gradient");
assert.match(page, /is-current/, "Active stage filter must highlight on the mix chart");
assert.doesNotMatch(page, /export-packages-mix__meters|export-packages-mix__track/, "Pipeline meters must stay retired");
assert.doesNotMatch(page, /export-packages-mix__bar/, "Stacked overview bar must stay retired");
assert.doesNotMatch(page, /export-packages-command/, "Standalone command header must fold into the bay rail");
assert.doesNotMatch(page, /export-packages-page is-v3/, "Retired v3 side-by-side bay must go");
assert.match(page, /export-packages-dock/, "Packages must render inside a dispatch dock panel");
assert.doesNotMatch(page, /export-packages-dock__head/, "Dock must not repeat Packages count label above the manifesto");
assert.match(page, /export-packages-rail__links/, "Triage links must live on the bay rail");
assert.match(page, /className="export-packages-rail__link"/, "Triage links must render as styled rail link buttons");
assert.match(page, /export-packages-rail__link-icon/, "Triage link buttons must include icons");
assert.match(page, /export-packages-manifest/, "Packages must render as a manifesto list");
assert.match(page, /export-packages-manifest__slip/, "Each package must render as a manifesto slip");
assert.match(
  page,
  /<Link[\s\S]{0,240}?className=\{`export-packages-manifest__slip|className="export-packages-manifest__slip/,
  "Manifest slips must be whole-row links into package detail",
);
assert.match(page, /export-packages-attention/, "Needs-attention must remain available as a quiet banner");
assert.match(page, /IntelligenceTableSkeleton/, "Cold load must skeleton the dense manifesto");
assert.match(page, /export-packages-bay[\s\S]*status=\{status\}|status=\{status\}[\s\S]*export-packages-bay/s, "Loading and error states must render inside the bay frame");
assert.match(page, /status === "loading"|status=\{status\}/, "Page must drive AsyncContentBoundary from bay status");
assert.doesNotMatch(page, /export-packages-stages/, "Chip-style stage strip must stay retired");
assert.doesNotMatch(page, /export-packages-spectrum|IntelligenceSpectrumSkeleton|publish-drafts-spectrum/, "Dispatch bay must not clone Drafts spectrum poster");
assert.doesNotMatch(page, /export-packages-ledger/, "Dispatch bay must retire Drafts-style ledger");
assert.doesNotMatch(page, /ops-export-page|ops-export-kpis|ExportKpi/, "Worksheet must retire Ops KPI chrome");
assert.doesNotMatch(page, /ops-export-sheet|ops-export-row is-head/, "Worksheet must retire sparse 6-column sheet");
assert.doesNotMatch(page, /ops-export-toolbar/, "Triage links must fold into the bay rail");
assert.match(page, /\/selection\/reup-queue/, "Reup Queue triage link must remain");
assert.match(page, /\/publishing\/publish-handoffs/, "Publish Handoffs triage link must remain");
assert.match(page, /fetchExportPackages/, "Export Packages must keep list authority");
assert.match(page, /stageFilter|setStageFilter/, "Mix chart must drive client-side filtering");
assert.match(page, /function packageStageClass/, "Stage class helper must own chart+slip+chip tokens");
assert.match(page, /export-packages-chip \$\{stage|className=\{`export-packages-chip \$\{/, "Status chips must use package stage classes");
assert.doesNotMatch(page, /tone-\$\{statusTone\(item\.status\)\}/, "Status chips must not use global statusTone on this page");
assert.match(en, /"filterAll"/, "en.json must define filterAll for donut core / legend");
assert.match(vi, /"filterAll"/, "vi.json must define filterAll for donut core / legend");

const cssStart = cssFull.indexOf("/* Export Packages Dispatch bay v4");
assert.ok(cssStart >= 0, "v4 Export Packages Dispatch bay CSS block must exist");
const css = cssFull.slice(cssStart, cssStart + 52000);
assert.match(css, /--pl-iq-mint:\s*#f4f8f6/, "Export bay must use Intelligence mint");
assert.match(css, /--ep-stage-ready:\s*#2f8f6f/, "Ready stage token must be shared");
assert.match(css, /--ep-stage-handed:\s*#4f6fbf/, "Handoff stage token must be shared");
assert.match(css, /export-packages-bay/, "Bay shell styles must exist");
assert.match(css, /export-packages-rail/, "Rail styles must exist");
assert.match(css, /export-packages-bay__body/, "Bay body styles must exist");
assert.match(css, /bay__body[^{]*\{[^}]*grid-template-columns:\s*minmax\(0,\s*1fr\)/, "Bay body must stack in one column");
assert.doesNotMatch(css, /bay__body[^{]*\{[^}]*0\.92fr/, "Bay body must not keep the tall side chart column");
assert.match(css, /export-packages-rail__link \{/, "Triage rail link button styles must exist");
assert.match(css, /export-packages-mix__donut/, "Donut styles must exist");
assert.match(css, /export-packages-mix__legend/, "Legend styles must exist");
assert.match(css, /export-packages-mix__signals/, "Signals panel styles must exist");
assert.match(css, /export-packages-mix__signal/, "Signal tile styles must exist");
assert.match(css, /export-packages-mix__board/, "Mix band must host chart and signals in one board");
assert.doesNotMatch(css, /export-packages-mix__meters/, "Retired meter styles must go");
assert.doesNotMatch(css, /export-packages-page\.is-v3/, "Retired v3 page shell must go from the bay block");
assert.match(css, /export-packages-manifest__slip/, "Manifest slip styles must exist");
assert.match(css, /export-packages-chip\.is-ready/, "Ready status chips must share Ready stage color");
assert.match(css, /export-packages-chip\.is-handed/, "Handoff status chips must share Handoff stage color");
assert.match(css, /slip\.is-handed[^{]*\{[^}]*--ep-slip-edge:\s*var\(--ep-stage-handed\)/, "Slip edge for Handoff must use handed token");
assert.match(css, /border-style:\s*dashed|dashed/, "Manifest slips must carry shipping-slip dashed chrome");
assert.doesNotMatch(css, /export-packages-stages/, "Retired chip stage strip styles must go");
assert.doesNotMatch(css, /export-packages-spectrum\.is-v7/, "Retired spectrum poster styles must go");
assert.doesNotMatch(css, /export-packages-ledger/, "Retired ledger styles must go");
assert.doesNotMatch(css, /ops-export-kpis/, "Retired Ops KPI styles must not live in the bay block");

console.log("export-packages-index-polish: PASS");
