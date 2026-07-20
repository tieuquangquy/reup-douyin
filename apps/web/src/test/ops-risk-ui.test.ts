/**
 * Ops Risk — triage visibility (filters, sorted sheet, attention; no mutate / no charts).
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const testDir = dirname(fileURLToPath(import.meta.url));
const webSrc = resolve(testDir, "..");

const page = readFileSync(resolve(webSrc, "components/ops-console/OpsRiskPage.tsx"), "utf8");
const css = readFileSync(resolve(webSrc, "app/globals.css"), "utf8");
const en = readFileSync(resolve(webSrc, "lib/i18n/en.json"), "utf8");
const vi = readFileSync(resolve(webSrc, "lib/i18n/vi.json"), "utf8");
const pkg = readFileSync(resolve(webSrc, "../package.json"), "utf8");

assert.match(page, /ops-risk-page/, "Risk page must use scoped ops-risk-page shell");
assert.match(page, /ops-risk-kpis/, "Risk page must render KPI band");
assert.match(page, /ops-risk-kpi/, "Risk page must use scoped KPI cards");
assert.match(page, /ops-risk-freshness|opsRisk\.loadedAt|loadedAt/, "Risk page must surface load freshness");
assert.match(page, /fetchRiskFlags/, "Risk page must keep risk-flags authority");
assert.match(page, /"REJECTED"|REJECTED/, "Risk page must also load REJECTED flags");
assert.match(page, /ops-risk-filters|statusFilter|filterStatus/, "Risk page must offer status filters");
assert.match(page, /useState<StatusFilter>\("OPEN"\)|useState\("OPEN"\)/, "Risk filter must default to Open");
assert.match(page, /ops-risk-flags|ops-risk-row|opsRisk\.flags/, "Risk page must render flags sheet");
assert.match(page, /ops-risk-chip|ops-risk-signal/, "Risk page must use soft severity/status chips");
assert.match(page, /ops-risk-attention|opsRisk\.attention/, "Risk page must surface blocking/critical attention");
assert.match(page, /attentionFlags\.length > 0/, "Attention side must only render when hot flags exist");
assert.doesNotMatch(page, /opsRisk\.limits|attentionClear/, "Dedicated Limits / empty-attention copy must be removed from page");
assert.match(page, /\/source-videos\/.*final-review|final-review/, "Risk page must deep-link Final Review");
assert.match(page, /source_video_id/, "Risk deep-link must use source_video_id");
assert.match(page, /\/ops\/health/, "Risk page must deep-link system health");
assert.match(page, /href=\"\/ops\"|href=\{\`\/ops\`\}|href="\/ops"/, "Risk page must deep-link ops home");
assert.match(page, /ops-risk-toolbar|ops-risk-actions/, "Triage links must sit in the compact toolbar");
assert.doesNotMatch(page, /health-overview-grid/, "Risk page must leave shared health-overview-grid");
assert.doesNotMatch(page, /<OpsMetricCard/, "Risk page must not use shared OpsMetricCard");
assert.doesNotMatch(page, /<OpsPanel/, "Risk page must not use shared OpsPanel");
assert.doesNotMatch(page, /ops-risk-meter|ShareMeter|flexGrow/, "Risk page must not use meter / chart bars");
assert.doesNotMatch(page, /updateRiskFlagStatus|onFlagAction/, "Risk page must not mutate flags in this pass");

assert.match(css, /\.ops-risk-page/, "CSS must define Risk page shell");
assert.match(css, /\.ops-risk-kpis/, "CSS must define Risk KPI grid");
assert.match(css, /\.ops-risk-filters/, "CSS must define Risk filter pills");
assert.match(css, /\.ops-risk-row|\.ops-risk-flags/, "CSS must define flags sheet");
assert.match(css, /\.ops-risk-chip|\.ops-risk-signal/, "CSS must define soft chips");
assert.match(css, /\.ops-risk-row__badges/, "Severity/status chips must sit in a spaced badge cluster");
assert.match(css, /\.ops-risk-row__badges[\s\S]*?gap:\s*0\.[3-5]/, "Badge cluster must keep a slim gap");
assert.match(css, /\.ops-risk-chip\s*\{[^}]*min-height:\s*1\.[2-4]/, "Risk chips must stay compact in height");
assert.doesNotMatch(css, /\.ops-risk-chip\s*\{[^}]*min-width:/, "Risk chips must not force a wide button min-width");
assert.match(page, /ops-risk-row__badges/, "Page must wrap severity/status in badge cluster");
assert.match(page, /riskChipTone/, "Risk chips must map HIGH severity to a non-muted tone");
assert.match(css, /\.ops-risk-attention/, "CSS must define attention list");
assert.match(css, /\.ops-risk-footnote/, "CSS must define compact footnote");
assert.match(css, /\.ops-risk-main\.is-split|\.ops-risk-main\.has-attention/, "CSS must support split only when attention is present");
assert.doesNotMatch(css, /\.ops-risk-meter/, "CSS must not define risk meters");

assert.match(en, /"loadedAt"|"attention"/, "en.json must define loadedAt / attention");
assert.match(en, /"filterAll"|"flags"/, "en.json must define filter / flags labels");
assert.match(en, /"decisionAtFinalReview"/, "en.json must define decisionAtFinalReview footnote");
assert.match(en, /"openFinalReview"/, "en.json must define Final Review link label");
assert.match(vi, /"loadedAt"|"attention"/, "vi.json must define loadedAt / attention");
assert.match(vi, /"filterAll"|"flags"/, "vi.json must define filter / flags labels");
assert.match(vi, /"decisionAtFinalReview"/, "vi.json must define decisionAtFinalReview footnote");
assert.match(vi, /"openFinalReview"/, "vi.json must define Final Review link label");

assert.match(page, /ops-risk-pager/, "Risk flags sheet must paginate");
assert.match(page, /RISK_PAGE_SIZE|pageSize\s*=\s*20|const pageSize = 20/, "Risk pagination must use a fixed page size");
assert.match(page, /setPage\(1\)|setPageIndex\(0\)/, "Changing status filter must reset to first page");
assert.match(page, /\.slice\(/, "Paginated rows must slice the filtered flag list");
assert.match(en, /"pagePrev"|"pageNext"|"pageRange"/, "en.json must define pager labels");
assert.match(vi, /"pagePrev"|"pageNext"|"pageRange"/, "vi.json must define pager labels");
assert.match(css, /\.ops-risk-pager/, "CSS must define risk pager");

assert.match(pkg, /ops-risk-ui\.test\.ts/, "package.json must run ops-risk-ui test");

console.log("ops-risk-ui tests passed");
