/** Intelligence data tabs: cold skeleton vs soft refresh (no fake KPI zeros). */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const webSrc = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const classification = readFileSync(resolve(webSrc, "components/operator-routes/ContentClassificationQueue.tsx"), "utf8");
const taxonomy = readFileSync(resolve(webSrc, "components/operator-routes/ContentTaxonomyManager.tsx"), "utf8");
const matching = readFileSync(resolve(webSrc, "components/operator-routes/AffiliateProductMatchingQueue.tsx"), "utf8");
const opportunity = readFileSync(resolve(webSrc, "components/operator-routes/AffiliateOpportunityRanking.tsx"), "utf8");
const cssFull = readFileSync(resolve(webSrc, "app/globals.css"), "utf8");
const cssStart = cssFull.indexOf("/* Intelligence Data Loading Skeleton");
assert.ok(cssStart >= 0, "shared Intelligence loading skeleton CSS block must exist");
const css = cssFull.slice(cssStart, cssStart + 5000);

for (const [name, source] of [
  ["classification", classification],
  ["taxonomy", taxonomy],
  ["matching", matching],
  ["opportunity", opportunity],
] as const) {
  assert.match(source, /hasLoadedOnce/, `${name} must track first successful payload`);
  assert.match(source, /coldLoading/, `${name} must distinguish cold load from soft refresh`);
  assert.match(
    source,
    /pl-iq-data-skeleton|is-skeleton|Intelligence(?:Table|Tree|Spectrum|Kpi)Skeleton/,
    `${name} must render a cold-load skeleton`,
  );
}

assert.match(classification, /coldLoading[\s\S]{0,120}?classification-queue-spectrum/, "Classification must not show live spectrum during cold load");
assert.match(matching, /coldLoading[\s\S]{0,120}?affiliate-matching-spectrum/, "Matching must not show live spectrum during cold load");
assert.match(opportunity, /coldLoading[\s\S]{0,200}?opportunity-ranking-spectrum/, "Opportunity must not show live spectrum during cold load");

assert.doesNotMatch(
  classification,
  /loading && queue\.items\.length === 0 \?[\s\S]{0,80}?<p className="muted"/,
  "Classification cold load must not be a bare muted paragraph",
);
assert.doesNotMatch(
  matching,
  /loading && queue\.items\.length === 0 \?[\s\S]{0,80}?<p className="muted"/,
  "Matching cold load must not be a bare muted paragraph",
);
assert.doesNotMatch(
  taxonomy,
  /loading && topics\.length === 0 \?[\s\S]{0,80}?<p className="muted"/,
  "Taxonomy cold load must not be a bare muted paragraph",
);
assert.doesNotMatch(
  opportunity,
  /loading && queue\.items\.length === 0 \?[\s\S]{0,80}?<p className="muted"/,
  "Opportunity cold load must not be a bare muted paragraph",
);

assert.match(css, /pl-iq-data-skeleton/, "CSS must style pl-iq-data-skeleton");
assert.match(css, /@keyframes pl-iq-skeleton-pulse|--pl-iq-mint/, "Skeleton must use Intelligence pulse tokens");

console.log("intelligence-data-loading-polish: PASS");
