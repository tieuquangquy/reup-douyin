/**
 * Publish Drafts index — queue triage sheet (Assets/Risk/Pipeline contract).
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
assert.match(page, /ops-drafts-page/, "Publish Drafts must use scoped ops-drafts-page shell");
assert.match(page, /ops-drafts-freshness|generated_at/, "Publish Drafts must surface queue freshness");
assert.match(page, /ops-drafts-kpis/, "Publish Drafts must render scoped KPI band");
assert.match(page, /ops-drafts-kpi/, "Publish Drafts must use scoped KPI cards");
assert.match(page, /ops-drafts-toolbar|ops-drafts-actions/, "Publish Drafts must render triage toolbar");
assert.match(page, /ops-drafts-sheet|ops-drafts-row/, "Publish Drafts must render list sheet");
assert.match(page, /ops-drafts-attention/, "Publish Drafts must surface attention");
assert.match(page, /needs_attention/, "Attention must read needs_attention authority");
assert.match(page, /needs_attention\.length > 0|attention\.length > 0/, "Attention side must only render when items exist");
assert.match(page, /ops-drafts-footnote|indexDesc|queueFootnote/, "Drafts must footnote queue reuse honesty");
assert.match(page, /fetchPublishControlQueue/, "Publish Drafts must keep queue authority");
assert.match(page, /unassigned_drafts|assigned_drafts|scheduled_drafts/, "Sheet must flatten queue buckets");
assert.doesNotMatch(page, /\/ops\/publish-health/, "Publish Drafts must not deep-link Ops Publish Health");
assert.doesNotMatch(page, /\/ops\/publish-control/, "Publish Drafts must not deep-link Ops Publish Control");
assert.match(page, /\/publishing\/export-packages|\/publishing\/publish-handoffs/, "Toolbar must keep Operator workflow triage links");
assert.match(page, /\/publishing\/drafts\/\$\{/, "Rows must deep-link draft detail");
assert.match(page, /useEffect\(\(\) => \{\s*void load\(\);\s*\},\s*\[t\]\)/s, "Load effect must stay on stable t dep");
assert.doesNotMatch(page, /OpsSummaryCards/, "Must not use OpsSummaryCards");
assert.doesNotMatch(page, /OpsItemCard/, "Must not use OpsItemCard");
assert.doesNotMatch(page, /operator-quick-grid|operator-quick-card/, "Must not use quick-card grid");
assert.doesNotMatch(page, /PageShell/, "Must not nest PageShell");
assert.doesNotMatch(page, /cookie|secret|token/i, "Must not expose secrets");

assert.match(css, /\.ops-drafts-page/, "CSS must define Drafts page shell");
assert.match(css, /\.ops-drafts-kpis/, "CSS must define Drafts KPI grid");
assert.match(css, /\.ops-drafts-chip\s*\{[^}]*font-weight:\s*400/, "Drafts chips must not use bold weight");
assert.match(css, /\.ops-drafts-main\.has-attention/, "CSS must support split when attention is present");
assert.match(css, /\.ops-drafts-footnote/, "CSS must define footnote");

assert.match(en, /"publishDraftsIndex"/, "en.json must keep publishDraftsIndex");
assert.match(en, /"operatorDraft"/, "en.json must define operatorDraft");
assert.match(vi, /"publishDraftsIndex"/, "vi.json must keep publishDraftsIndex");
assert.match(vi, /"operatorDraft"/, "vi.json must define operatorDraft");
assert.match(pkg, /ops-publish-drafts-ui\.test\.ts/, "package.json must run drafts UI test");

console.log("ops-publish-drafts-ui tests passed");
