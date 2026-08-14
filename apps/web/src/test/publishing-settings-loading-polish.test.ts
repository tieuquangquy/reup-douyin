/** Publishing Settings cold-load: Content Intelligence / Catalog / Comments share Intelligence skeletons. */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const webSrc = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const skeleton = readFileSync(resolve(webSrc, "components/operator-routes/IntelligenceDataSkeleton.tsx"), "utf8");
const contentAi = readFileSync(resolve(webSrc, "components/operator-routes/ContentAiConfiguration.tsx"), "utf8");
const catalog = readFileSync(resolve(webSrc, "components/operator-routes/AffiliateCatalogPage.tsx"), "utf8");
const comments = readFileSync(resolve(webSrc, "components/operator-routes/AffiliateCommentTemplatesSettingsPage.tsx"), "utf8");
const cssFull = readFileSync(resolve(webSrc, "app/globals.css"), "utf8");

assert.match(skeleton, /export function IntelligenceSettingsStageSkeleton/, "Content Intelligence cold-load needs a stage skeleton");
assert.match(skeleton, /export function IntelligenceCatalogWorksheetSkeleton/, "Affiliate Catalog cold-load needs toolbar + table worksheet skeleton");
assert.match(skeleton, /export function IntelligenceSplitEditorSkeleton/, "Affiliate Comments cold-load needs list + editor split skeleton");
assert.match(skeleton, /pl-iq-data-skeleton is-stage/, "Stage skeleton must use the shared Intelligence skeleton mark");
assert.match(skeleton, /pl-iq-data-skeleton is-catalog-worksheet/, "Catalog worksheet skeleton must use the shared Intelligence skeleton mark");
assert.match(skeleton, /pl-iq-data-skeleton is-split/, "Split skeleton must use the shared Intelligence skeleton mark");

assert.match(contentAi, /IntelligenceSettingsStageSkeleton/, "Content AI cold-load must render the stage skeleton, not muted copy alone");
assert.doesNotMatch(
  contentAi,
  /if \(!config \|\| !draft\) \{[\s\S]{0,220}?<p className="muted"/,
  "Content AI must not fall back to a bare muted loading paragraph",
);

assert.match(catalog, /IntelligenceCatalogWorksheetSkeleton/, "Catalog cold-load must render the worksheet skeleton");
assert.match(catalog, /coldLoading && !showForm \?[\s\S]{0,220}?IntelligenceCatalogWorksheetSkeleton/, "Catalog worksheet skeleton must gate on coldLoading");

assert.match(comments, /IntelligenceSplitEditorSkeleton/, "Comments cold-load must render the split editor skeleton");
assert.doesNotMatch(
  comments,
  /loading \? <p className="muted">\{t\("affiliateComment\.loading"\)\}<\/p>/,
  "Comments must not keep the muted loading paragraph as the cold-load UI",
);

const cssStart = cssFull.indexOf("/* Intelligence Data Loading Skeleton");
assert.ok(cssStart >= 0, "Shared Intelligence skeleton CSS block must exist");
const css = cssFull.slice(cssStart, cssStart + 9000);
assert.match(css, /\.pl-iq-data-skeleton\.is-stage/, "Stage skeleton CSS must exist");
assert.match(css, /\.pl-iq-data-skeleton\.is-catalog-worksheet/, "Catalog worksheet skeleton CSS must exist");
assert.match(css, /\.pl-iq-data-skeleton\.is-split/, "Split skeleton CSS must exist");

console.log("publishing-settings-loading-polish: PASS");
