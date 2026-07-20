/**
 * Ops Assets — reuse triage (current/historical by type, compact right column, no charts).
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const testDir = dirname(fileURLToPath(import.meta.url));
const webSrc = resolve(testDir, "..");

const page = readFileSync(resolve(webSrc, "components/ops-console/OpsAssetsPage.tsx"), "utf8");
const css = readFileSync(resolve(webSrc, "app/globals.css"), "utf8");
const en = readFileSync(resolve(webSrc, "lib/i18n/en.json"), "utf8");
const vi = readFileSync(resolve(webSrc, "lib/i18n/vi.json"), "utf8");
const pkg = readFileSync(resolve(webSrc, "../package.json"), "utf8");

assert.match(page, /ops-assets-page/, "Assets page must use scoped ops-assets-page shell");
assert.match(page, /ops-assets-kpis/, "Assets page must render KPI band");
assert.match(page, /ops-assets-kpi/, "Assets page must use scoped KPI cards");
assert.match(page, /generated_at/, "Assets page must surface metrics freshness");
assert.match(page, /ops-assets-freshness|opsAssets\.metricsGenerated/, "Assets page must render freshness strip");
assert.match(page, /asset_reuse_by_type/, "Assets page must read asset_reuse_by_type authority");
assert.match(page, /fetchOperationalMetrics/, "Assets page must keep metrics authority");
assert.match(page, /ops-assets-by-type|opsAssets\.byType/, "Assets page must render by-type panel");
assert.match(page, /opsAssets\.staleShare|staleShare/, "Assets page must show stale pressure as text");
assert.match(page, /ops-assets-signal/, "Assets page must render scoped signal chips");
assert.match(page, /ops-assets-signal tone-\$\{row\.needsCurrent \? "warn" : "good"\}/, "Signal chips must toggle warn/good by needsCurrent");
assert.doesNotMatch(page, /ops-assets-meter|ShareMeter|flexGrow/, "Assets page must not use meter / chart bars");
assert.match(page, /ops-assets-attention|opsAssets\.needsCurrent|current_count === 0/, "Assets page must surface types needing current");
assert.match(page, /needsCurrentRows\.length > 0/, "Attention side must only render when types need current");
assert.doesNotMatch(page, /opsAssets\.limits|attentionClear|ops-assets-limits/, "Dedicated Limits / empty-attention copy must be removed from page");
assert.match(page, /ops-assets-footnote|fileScanDeferred/, "Limits honesty must become a compact footnote");
assert.match(page, /ops-assets-toolbar|ops-assets-actions/, "Triage links must sit in the compact toolbar");
assert.match(page, /\/ops\/health/, "Assets page must deep-link system health");
assert.match(page, /\/ops\/tools/, "Assets page must deep-link tools / doctor");
assert.doesNotMatch(page, /ops-assets-pager|ASSETS_PAGE_SIZE/, "Assets by-type sheet must not use the mistaken pager");
assert.doesNotMatch(page, /health-overview-grid/, "Assets page must leave shared health-overview-grid");
assert.doesNotMatch(page, /<OpsMetricCard/, "Assets page must not use shared OpsMetricCard");
assert.doesNotMatch(page, /<OpsPanel/, "Assets page must not use shared OpsPanel");
assert.doesNotMatch(page, /opsAssets\.notScanned|missingOrCorrupt/, "Assets page must not show fake Not scanned KPI");

assert.match(css, /\.ops-assets-page/, "CSS must define Assets page shell");
assert.match(css, /\.ops-assets-kpis/, "CSS must define Assets KPI grid");
assert.match(css, /\.ops-assets-by-type|\.ops-assets-row/, "CSS must define by-type sheet");
assert.doesNotMatch(css, /\.ops-assets-meter/, "CSS must not define share meters");
assert.match(css, /\.ops-assets-signal/, "CSS must define Assets signal chips");
assert.match(css, /\.ops-assets-signal\.tone-warn|\.ops-assets-signal\.tone-good/, "CSS must define signal chip tones");
assert.match(css, /\.ops-assets-signal\s*\{[^}]*font-weight:\s*400/, "Signal chips must not use bold weight");
assert.match(css, /\.ops-assets-row\.is-head\s*>\s*span:nth-child\(n\s*\+\s*2\)/, "Numeric / signal headers must right-align with values");
assert.match(css, /\.ops-assets-attention/, "CSS must define attention list");
assert.match(css, /\.ops-assets-footnote/, "CSS must define compact footnote");
assert.match(css, /\.ops-assets-main\.has-attention/, "CSS must support split only when attention is present");
assert.doesNotMatch(css, /\.ops-assets-pager/, "CSS must not define assets pager");

assert.match(en, /"byType"|"needsCurrent"/, "en.json must define byType / needsCurrent");
assert.match(en, /"metricsGenerated"|"staleShare"/, "en.json must define freshness / stale labels");
assert.match(en, /"fileScanDeferred"/, "en.json must define deferred limits copy");
assert.match(vi, /"byType"|"needsCurrent"/, "vi.json must define byType / needsCurrent");
assert.match(vi, /"metricsGenerated"|"staleShare"/, "vi.json must define freshness / stale labels");
assert.match(vi, /"fileScanDeferred"/, "vi.json must define deferred limits copy");

assert.match(pkg, /ops-assets-ui\.test\.ts/, "package.json must run ops-assets-ui test");

console.log("ops-assets-ui tests passed");
