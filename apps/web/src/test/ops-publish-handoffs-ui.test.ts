/**
 * Publish Handoffs index — Dispatch bay twin of Export Packages (handoff stages / signals / slips).
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const testDir = dirname(fileURLToPath(import.meta.url));
const webSrc = resolve(testDir, "..");

const page = readFileSync(resolve(webSrc, "components/operator-routes/PublishHandoffsIndexPage.tsx"), "utf8");
const cssFull = readFileSync(resolve(webSrc, "app/globals.css"), "utf8");
const en = readFileSync(resolve(webSrc, "lib/i18n/en.json"), "utf8");
const vi = readFileSync(resolve(webSrc, "lib/i18n/vi.json"), "utf8");
const pkg = readFileSync(resolve(webSrc, "../package.json"), "utf8");

assert.match(page, /OperatorStudioShell/, "Publish Handoffs must keep OperatorStudioShell");
assert.match(page, /TopbarRefreshButton/, "Publish Handoffs must put Refresh in the Topbar");
assert.match(page, /publish-handoffs-page is-bay/, "Publish Handoffs must use Dispatch bay shell");
assert.match(page, /publish-handoffs-bay/, "Publish Handoffs must render dispatch bay");
assert.match(page, /publish-handoffs-bay__body/, "Publish Handoffs must render bay body");
assert.match(page, /publish-handoffs-mix__donut/, "Publish Handoffs must render mix donut");
assert.match(page, /publish-handoffs-mix__legend/, "Publish Handoffs must render mix legend");
assert.match(page, /publish-handoffs-mix__signals/, "Publish Handoffs must render mix signals");
assert.match(page, /conic-gradient/, "Publish Handoffs donut must use conic-gradient");
assert.match(page, /handoffStageClass/, "Publish Handoffs must share stage tokens across chart and slips");
assert.match(page, /publish-handoffs-manifest/, "Publish Handoffs must render manifesto list");
assert.match(page, /publish-handoffs-manifest__slip/, "Publish Handoffs must render manifesto slips");
assert.match(page, /publish-handoffs-rail__link/, "Publish Handoffs must host triage links on the bay rail");
assert.match(page, /publish-handoffs-attention/, "Publish Handoffs must surface attention banner");
assert.match(page, /FAILED_NEEDS_ATTENTION/, "Attention must derive from FAILED_NEEDS_ATTENTION");
assert.match(page, /needsAttention\.length > 0/, "Attention banner must only render when items exist");
assert.match(page, /publish-handoffs-footnote|noPlatformApi/, "Publish Handoffs must footnote honesty");
assert.match(page, /fetchPublishHandoffs/, "Publish Handoffs must keep list authority");
assert.match(page, /\/publishing\/export-packages/, "Bay must link Export Packages");
assert.match(page, /\/selection\/reup-queue/, "Bay must link Reup Queue");
assert.match(page, /\/publishing\/publish-handoffs\/\$\{/, "Slips must deep-link handoff detail");
assert.match(page, /READY_FOR_OPERATOR/, "Ready stage must include READY_FOR_OPERATOR");
assert.match(page, /ACCEPTED/, "Accepted stage must be part of the mix");
assert.match(page, /humanizeStatus/, "Status chips must use humanizeStatus");
assert.match(page, /IntelligenceTableSkeleton/, "Cold load must skeleton the dock");
assert.doesNotMatch(page, /publish-handoffs-page is-desk/, "Operator Desk shell must be retired");
assert.doesNotMatch(page, /publish-handoffs-dial/, "Handoff Dial must be retired");
assert.doesNotMatch(page, /publish-handoffs-ticket/, "Paper tickets must be retired for manifesto slips");
assert.doesNotMatch(page, /publish-handoffs-brief[^a-z]|publish-handoffs-dossier|publish-handoffs-filing|publish-handoffs-trays|publish-handoffs-stamps|publish-handoffs-pulse|publish-handoffs-orbit|publish-handoffs-river/, "Retired metaphors must stay retired");
assert.doesNotMatch(page, /export-packages-mix|export-packages-bay|export-packages-manifest/, "Must not reuse Export Packages class names");
assert.doesNotMatch(page, /ops-handoffs-page|ops-handoffs-kpis|HandoffKpi/, "Legacy Ops KPI chrome must stay retired");
assert.doesNotMatch(page, /OpsSummaryCards|OpsItemCard|PageShell/, "Must not use legacy Ops list chrome");
assert.doesNotMatch(page, /cookie|secret|token/i, "Must not expose secrets");
assert.doesNotMatch(en, /"readyDetail":\s*"READY_FOR_OPERATOR/, "en readyDetail must not leak status enum");
assert.doesNotMatch(vi, /"readyDetail":\s*"READY_FOR_OPERATOR/, "vi readyDetail must not leak status enum");
assert.match(en, /"handoffRecords"/, "en.json must define handoff records rail label");
assert.match(vi, /"handoffRecords"/, "vi.json must define handoff records rail label");
assert.match(en, /"spectrumSignals"/, "en.json must define signals label");
assert.match(vi, /"spectrumSignals"/, "vi.json must define signals label");

const cssStart = cssFull.indexOf("/* Publish Handoffs Dispatch bay");
assert.ok(cssStart >= 0, "Publish Handoffs Dispatch bay CSS block must exist");
const css = cssFull.slice(cssStart, cssStart + 45000);
assert.match(css, /\.publish-handoffs-page\.is-bay/, "CSS must define Publish Handoffs bay page shell");
assert.match(css, /\.publish-handoffs-bay/, "CSS must define dispatch bay");
assert.match(css, /bay__body[^{]*\{[^}]*grid-template-columns:\s*minmax\(0,\s*1fr\)/, "CSS must stack bay body in one column");
assert.match(css, /\.publish-handoffs-mix__donut/, "CSS must define donut");
assert.match(css, /\.publish-handoffs-mix__legend/, "CSS must define mix legend");
assert.match(css, /\.publish-handoffs-mix__signals/, "CSS must define mix signals");
assert.match(css, /\.publish-handoffs-manifest__slip/, "CSS must define manifesto slips");
assert.match(css, /\.publish-handoffs-attention/, "CSS must define attention banner");
assert.match(css, /\.publish-handoffs-footnote/, "CSS must define footnote");
assert.match(css, /--ph-stage-ready:/, "CSS must define Ready stage token");
assert.match(css, /--ph-stage-accepted:/, "CSS must define Accepted stage token");
assert.doesNotMatch(css.slice(0, 8000), /publish-handoffs-dial__/, "Live bay CSS head must not keep Dial cluster rules");

assert.match(pkg, /ops-publish-handoffs-ui\.test\.ts/, "package.json must run handoffs UI test");

console.log("ops-publish-handoffs-ui tests passed");
