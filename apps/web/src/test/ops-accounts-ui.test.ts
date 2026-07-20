/**
 * Ops Accounts — platform account triage (scoped KPI/sheet, compact attention, no legacy health-table).
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const testDir = dirname(fileURLToPath(import.meta.url));
const webSrc = resolve(testDir, "..");

const page = readFileSync(resolve(webSrc, "components/ops-console/OpsAccountsPage.tsx"), "utf8");
const css = readFileSync(resolve(webSrc, "app/globals.css"), "utf8");
const en = readFileSync(resolve(webSrc, "lib/i18n/en.json"), "utf8");
const vi = readFileSync(resolve(webSrc, "lib/i18n/vi.json"), "utf8");
const pkg = readFileSync(resolve(webSrc, "../package.json"), "utf8");

assert.match(page, /ops-accounts-page/, "Accounts page must use scoped ops-accounts-page shell");
assert.match(page, /ops-accounts-kpis/, "Accounts page must render KPI band");
assert.match(page, /ops-accounts-kpi/, "Accounts page must use scoped KPI cards");
assert.match(page, /ops-accounts-freshness|opsAccounts\.loadedAt/, "Accounts page must surface load freshness");
assert.match(page, /fetchAllPlatformAccounts/, "Accounts page must keep platform-accounts authority");
assert.match(page, /fetchPublishControlQueue/, "Accounts page must keep queue health authority for unhealthy KPI");
assert.match(page, /ops-accounts-sheet|ops-accounts-row/, "Accounts page must render accounts sheet");
assert.match(page, /ops-accounts-chip/, "Accounts page must use soft status/hold chips");
assert.match(page, /ops-accounts-attention/, "Accounts page must surface attention for hold/unhealthy");
assert.match(page, /attentionRows\.length > 0/, "Attention side must only render when hot accounts exist");
assert.match(page, /ops-accounts-toolbar|ops-accounts-actions/, "Triage links must sit in the compact toolbar");
assert.match(page, /\/ops\/publish-control/, "Accounts page must deep-link publish control");
assert.match(page, /ops-accounts-footnote|editsInPublishControl/, "Accounts must footnote that edits live in publish-control");
assert.doesNotMatch(page, /health-overview-grid/, "Accounts page must leave shared health-overview-grid");
assert.doesNotMatch(page, /health-table/, "Accounts page must not use health-table");
assert.doesNotMatch(page, /<OpsMetricCard/, "Accounts page must not use shared OpsMetricCard");
assert.doesNotMatch(page, /<OpsPanel/, "Accounts page must not use shared OpsPanel");
assert.doesNotMatch(page, /<StatusBadge/, "Accounts page must not use StatusBadge");
assert.doesNotMatch(page, /updatePlatformAccount/, "Accounts page must stay read-only");

assert.match(css, /\.ops-accounts-page/, "CSS must define Accounts page shell");
assert.match(css, /\.ops-accounts-kpis/, "CSS must define Accounts KPI grid");
assert.match(css, /\.ops-accounts-row|\.ops-accounts-sheet/, "CSS must define accounts sheet");
assert.match(css, /\.ops-accounts-chip\s*\{[^}]*font-weight:\s*400/, "Accounts chips must not use bold weight");
assert.match(css, /\.ops-accounts-attention/, "CSS must define attention list");
assert.match(css, /\.ops-accounts-footnote/, "CSS must define compact footnote");
assert.match(css, /\.ops-accounts-main\.has-attention/, "CSS must support split only when attention is present");

assert.match(en, /"loadedAt"|"attention"|"editsInPublishControl"/, "en.json must define Accounts redesign labels");
assert.match(en, /"yes"|"no"/, "en.json must define hold yes/no");
assert.match(vi, /"loadedAt"|"attention"|"editsInPublishControl"/, "vi.json must define Accounts redesign labels");
assert.match(vi, /"yes"|"no"/, "vi.json must define hold yes/no");

assert.match(pkg, /ops-accounts-ui\.test\.ts/, "package.json must run ops-accounts-ui test");

console.log("ops-accounts-ui tests passed");
