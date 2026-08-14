/**
 * Publish Drafts index — Intelligence worksheet queue triage.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const testDir = dirname(fileURLToPath(import.meta.url));
const webSrc = resolve(testDir, "..");

const page = readFileSync(resolve(webSrc, "components/operator-routes/PublishDraftsIndexPage.tsx"), "utf8");
const css = readFileSync(resolve(webSrc, "app/globals.css"), "utf8");
const en = readFileSync(resolve(webSrc, "lib/i18n/en.json"), "utf8");
const vi = readFileSync(resolve(webSrc, "lib/i18n/vi.json"), "utf8");
const pkg = readFileSync(resolve(webSrc, "../package.json"), "utf8");

assert.match(page, /OperatorStudioShell/, "Publish Drafts must keep OperatorStudioShell");
assert.match(page, /TopbarRefreshButton/, "Publish Drafts must put Refresh in the Topbar");
assert.match(page, /publish-drafts-page is-v1/, "Publish Drafts must use Intelligence worksheet shell");
assert.match(page, /generated_at/, "Publish Drafts must surface queue freshness");
assert.match(page, /publish-drafts-spectrum is-v7/, "Publish Drafts must mark Queue poster spectrum v7");
assert.match(page, /publish-drafts-spectrum__poster/, "Publish Drafts must render poster composition");
assert.match(page, /publish-drafts-spectrum__score/, "Publish Drafts must render proportional score rows");
assert.match(page, /publish-drafts-spectrum__rule/, "Publish Drafts must render dominant accent rule");
assert.match(page, /publish-drafts-spectrum__metrics/, "Publish Drafts must render metric ticker");
assert.match(page, /publish-drafts-panel__links/, "Publish Drafts must host triage links in the queue panel");
assert.match(page, /publish-drafts-ledger/, "Publish Drafts must render split ledger table");
assert.match(page, /publish-drafts-ledger__row/, "Publish Drafts must render ledger rows");
assert.doesNotMatch(page, /publish-drafts-mosaic|DraftTile/, "Publish Drafts must retire mosaic tiles");
assert.doesNotMatch(page, /publish-drafts-tickets|DraftTicket/, "Publish Drafts must retire ticket list");
assert.doesNotMatch(page, /publish-drafts-toolbar/, "Publish Drafts must retire the detached triage toolbar");
assert.doesNotMatch(page, /publish-drafts-row is-head/, "Publish Drafts must retire the 6-column sheet head");
assert.match(page, /publish-drafts-attention/, "Publish Drafts must surface attention");
assert.match(page, /needs_attention/, "Attention must read needs_attention authority");
assert.match(page, /attention\.length > 0|attentionCount > 0/, "Attention strip must only render when items exist");
assert.match(page, /planned_publish_at/, "Metric grid must surface next scheduled time");
assert.match(page, /accounts\.length/, "Metric grid must surface accounts in view");
assert.match(page, /publish-drafts-footnote|indexDesc/, "Drafts must footnote queue reuse honesty");
assert.match(page, /fetchPublishControlQueue/, "Publish Drafts must keep queue authority");
assert.match(page, /unassigned_drafts|assigned_drafts|scheduled_drafts/, "Sheet must flatten queue buckets");
assert.doesNotMatch(page, /\/ops\/publish-health/, "Publish Drafts must not deep-link Ops Publish Health");
assert.doesNotMatch(page, /\/ops\/publish-control/, "Publish Drafts must not deep-link Ops Publish Control");
assert.match(page, /\/publishing\/export-packages|\/publishing\/publish-handoffs/, "Panel must keep Operator workflow triage links");
assert.match(page, /\/publishing\/drafts\/\$\{/, "Rows must deep-link draft detail");
assert.match(page, /useEffect\(\(\) => \{\s*void load\(\);\s*\},\s*\[t\]\)/s, "Load effect must stay on stable t dep");
assert.doesNotMatch(page, /OpsSummaryCards|OpsItemCard|PageShell/, "Must not use retired shells/cards");
assert.doesNotMatch(page, /operator-quick-grid|operator-quick-card/, "Must not use quick-card grid");
assert.doesNotMatch(page, /cookie|secret|token/i, "Must not expose secrets");
assert.doesNotMatch(page, /ops-drafts-kpi|DraftsKpi|has-attention|publish-drafts-spectrum__donut/, "Retired Ops / donut marks must go");

assert.match(css, /\/\* Publishing Drafts Intelligence worksheet v1/, "CSS must define Drafts worksheet v1 block");
assert.match(css, /\.publish-drafts-page\.is-v1/, "CSS must define Drafts page shell");
assert.match(css, /\.publish-drafts-spectrum\.is-v7/, "CSS must define Queue poster spectrum v7");
assert.match(css, /\.publish-drafts-spectrum__poster/, "CSS must define poster composition");
assert.match(css, /\.publish-drafts-spectrum__score/, "CSS must define score rows");
assert.match(css, /\.publish-drafts-spectrum__metrics/, "CSS must define metric ticker");
assert.match(
  css,
  /\.publish-drafts-spectrum\.is-v7 \.publish-drafts-spectrum__stage \{[\s\S]{0,900}?width:\s*100%/,
  "Poster stage must span the content width",
);
assert.match(css, /\.publish-drafts-ledger/, "CSS must define split ledger table");
assert.match(css, /\.publish-drafts-ledger__row/, "CSS must define ledger rows");
assert.match(css, /\.publish-drafts-chip\s*\{[^}]*font-weight:\s*400/, "Drafts chips must not use bold weight");
assert.match(css, /\.publish-drafts-attention/, "CSS must define attention strip");
assert.match(css, /\.publish-drafts-footnote/, "CSS must define footnote");
assert.doesNotMatch(css, /\.publish-drafts-row\.is-head/, "CSS must retire sheet head");
assert.doesNotMatch(css, /\.publish-drafts-mosaic/, "CSS must retire mosaic grid");
assert.doesNotMatch(css, /\.publish-drafts-tickets/, "CSS must retire ticket list");

assert.match(en, /"publishDraftsIndex"/, "en.json must keep publishDraftsIndex");
assert.match(en, /"operatorDraft"/, "en.json must define operatorDraft");
assert.match(vi, /"publishDraftsIndex"/, "vi.json must keep publishDraftsIndex");
assert.match(vi, /"operatorDraft"/, "vi.json must define operatorDraft");
assert.match(pkg, /ops-publish-drafts-ui\.test\.ts/, "package.json must run drafts UI test");

console.log("ops-publish-drafts-ui tests passed");
