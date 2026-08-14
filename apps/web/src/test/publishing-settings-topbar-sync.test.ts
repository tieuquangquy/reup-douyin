/** Publishing Settings topbars must match Publication Library header contract. */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const webSrc = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const contentAiPage = readFileSync(resolve(webSrc, "components/operator-routes/ContentIntelligenceSettingsPage.tsx"), "utf8");
const contentAi = readFileSync(resolve(webSrc, "components/operator-routes/ContentAiConfiguration.tsx"), "utf8");
const catalogPage = readFileSync(resolve(webSrc, "components/operator-routes/AffiliateCatalogSettingsPage.tsx"), "utf8");
const catalog = readFileSync(resolve(webSrc, "components/operator-routes/AffiliateCatalogPage.tsx"), "utf8");
const comments = readFileSync(resolve(webSrc, "components/operator-routes/AffiliateCommentTemplatesSettingsPage.tsx"), "utf8");
const navConfig = readFileSync(resolve(webSrc, "lib/navigationConfig.ts"), "utf8");

const contentAiSurface = `${contentAiPage}\n${contentAi}`;
const catalogSurface = `${catalogPage}\n${catalog}`;

assert.match(
  contentAiSurface,
  /title=\{t\("publishingSettings\.contentIntelligence"\)\}/,
  "Content Intelligence topbar title must be the leaf page name, like Publication Library",
);
assert.match(
  contentAiSurface,
  /description=\{t\("publishingSettings\.contentIntelligenceHint"\)\}/,
  "Content Intelligence must use its own topbar description",
);
assert.match(
  catalogSurface,
  /title=\{t\("publishingSettings\.affiliateCatalog"\)\}/,
  "Affiliate Catalog topbar title must be the leaf page name",
);
assert.match(
  catalogSurface,
  /description=\{t\("publishingSettings\.affiliateCatalogHint"\)\}/,
  "Affiliate Catalog must use its own topbar description",
);
assert.match(
  comments,
  /title=\{t\("publishingSettings\.affiliateComments"\)\}/,
  "Affiliate Comments topbar title must be the leaf page name",
);
assert.match(
  comments,
  /description=\{t\("publishingSettings\.affiliateCommentsHint"\)\}/,
  "Affiliate Comments must use its own topbar description",
);

assert.doesNotMatch(
  contentAiSurface + catalogSurface + comments,
  /title=\{t\("publishingSettings\.title"\)\}/,
  "Shared Publishing Settings title must not replace the leaf page title in the topbar",
);

for (const path of [
  "/publishing/settings/content-intelligence",
  "/publishing/settings/affiliate-catalog",
  "/publishing/settings/affiliate-comments",
]) {
  const blockStart = navConfig.indexOf(`patterns: ["${path}"]`);
  assert.ok(blockStart >= 0, `Breadcrumb block for ${path} must exist`);
  const block = navConfig.slice(blockStart, blockStart + 420);
  assert.match(
    block,
    /label: "nav\.sectionPublishing"/,
    `${path} breadcrumbs must use Publishing like Publication Library (Home > Publishing > leaf)`,
  );
  assert.doesNotMatch(
    block,
    /label: "nav\.sectionPublishingSettings"/,
    `${path} must not use Publishing Settings as the middle crumb`,
  );
}

assert.match(contentAiSurface, /TopbarRefreshButton/, "Content Intelligence must expose the default topbar Refresh control");
assert.match(catalogSurface, /TopbarRefreshButton/, "Affiliate Catalog must expose the default topbar Refresh control");
assert.match(comments, /TopbarRefreshButton/, "Affiliate Comments must expose the default topbar Refresh control");
assert.match(contentAi, /actions=\{[\s\S]{0,220}?TopbarRefreshButton[\s\S]{0,220}?load\(true\)/, "Content AI Refresh must call load(true)");
assert.match(catalog, /actions=\{[\s\S]{0,220}?TopbarRefreshButton[\s\S]{0,220}?load\(true\)/, "Catalog Refresh must call load(true)");
assert.match(comments, /actions=\{[\s\S]{0,220}?TopbarRefreshButton[\s\S]{0,220}?load\(\)/, "Comments Refresh must call load()");

console.log("publishing-settings-topbar-sync: PASS");
