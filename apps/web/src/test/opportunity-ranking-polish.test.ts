/** Opportunity Ranking Intelligence polish: spectrum + toolbar + dense table + detail drawer. */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const webSrc = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const queue = readFileSync(resolve(webSrc, "components/operator-routes/AffiliateOpportunityRanking.tsx"), "utf8");
const cssFull = readFileSync(resolve(webSrc, "app/globals.css"), "utf8");
const en = readFileSync(resolve(webSrc, "lib/i18n/en.json"), "utf8");
const vi = readFileSync(resolve(webSrc, "lib/i18n/vi.json"), "utf8");

const v1Start = cssFull.indexOf("/* Opportunity Ranking Intelligence v1");
assert.ok(v1Start >= 0, "v1 opportunity ranking polish CSS block must exist");
const v1 = cssFull.slice(v1Start, v1Start + 45000);

assert.match(queue, /opportunity-ranking-page is-v1/, "Opportunity page must opt into Intelligence v1 shell");
assert.match(queue, /opportunity-ranking-spectrum/, "Opportunity page must show a recommendation-mix spectrum");
assert.match(queue, /opportunity-ranking-spectrum__donut/, "Spectrum must include a donut status mix");
assert.match(queue, /opportunity-ranking-spectrum__plot|opportunity-ranking-spectrum__bars/, "Spectrum must include filterable attention bars");
assert.match(queue, /filter:\s*"PRIORITY"/, "Queue signals must include Priority as a filterable recommendation");
assert.match(queue, /filter:\s*"DO_NOT_PLACE"/, "Queue signals must include Do not place as a filterable recommendation");
assert.doesNotMatch(queue, /opportunity-ranking-kpis/, "v1 must drop the five flat KPI cards");
assert.match(queue, /opportunity-ranking-toolbar is-v1/, "v1 must use the compact command toolbar");
assert.match(queue, /OpportunityToolbarGlyph|opportunity-ranking-toolbar__glyph/, "Toolbar actions must use compact glyphs");
assert.match(queue, /noAutoPlacement|separateScores|noCombinedScore/, "Opportunity must keep no-auto-placement / separate-score safety copy");
assert.match(queue, /opportunity-ranking-table is-v1|opportunity-ranking-table-wrap is-v1/, "v1 must mark the dense results table");
assert.match(queue, /WorkItemDetailsDrawer/, "v1 must open detail in WorkItemDetailsDrawer");
assert.doesNotMatch(queue, /opportunity-ranking-detail-row/, "v1 must remove the inline table detail row");
assert.match(queue, /is-clickable/, "Scored rows must be marked clickable for drawer open");
assert.match(queue, /stopPropagation/, "Action controls must stopPropagation so row click does not double-toggle");
assert.match(queue, /AffiliateCommentPlacementPanel/, "Drawer must still host affiliate comment placement");
assert.match(queue, /affiliateComment\.prepare/, "Priority opportunities must still expose prepare copy");
assert.match(queue, /opportunity-ranking-empty|emptyHint/, "Empty opportunity queue must have a dedicated empty state");
assert.match(queue, /IntelligenceSpectrumSkeleton|IntelligenceTableSkeleton/, "Cold load must use Intelligence skeletons");

assert.match(v1, /--pl-iq-mint|--pl-iq-label-quiet|--pl-iq-label-strong/, "v1 CSS must use Intelligence tokens");
assert.match(v1, /opportunity-ranking-spectrum__donut/, "v1 CSS must style the spectrum donut");
assert.match(v1, /opportunity-ranking-toolbar/, "v1 CSS must style the toolbar");
assert.match(v1, /work-item-details-drawer|opportunity-ranking-detail/, "v1 CSS must style drawer-hosted detail");

assert.match(en, /"spectrumStatusMix":/, "en.json must include opportunityRanking.spectrumStatusMix");
assert.match(vi, /"spectrumStatusMix":/, "vi.json must include opportunityRanking.spectrumStatusMix");
assert.match(en, /"emptyHint":/, "en.json must include opportunityRanking.emptyHint");
assert.match(vi, /"emptyHint":/, "vi.json must include opportunityRanking.emptyHint");
assert.match(en, /"noAutoPlacement":/, "en.json must include opportunityRanking.noAutoPlacement");
assert.match(vi, /"noAutoPlacement":/, "vi.json must include opportunityRanking.noAutoPlacement");

console.log("opportunity-ranking-polish: PASS");
