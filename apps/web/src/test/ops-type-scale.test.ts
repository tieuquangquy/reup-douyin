/**
 * Ops Home + Health — readable type scale + secondary text contrast (A+B).
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const testDir = dirname(fileURLToPath(import.meta.url));
const webSrc = resolve(testDir, "..");
const css = readFileSync(resolve(webSrc, "app/globals.css"), "utf8");
const pkg = readFileSync(resolve(webSrc, "../package.json"), "utf8");

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function cssDecl(selector: string, prop: string): string {
  const selRe = selector
    .split(/\s*,\s*/)
    .map((part) =>
      part
        .trim()
        .split(/\s+/)
        .map(escapeRegExp)
        .join("\\s+"),
    )
    .join("\\s*,\\s*");
  const re = new RegExp(`(?:^|[\\n,])\\s*${selRe}\\s*\\{([^}]*)\\}`, "m");
  const match = css.match(re);
  assert.ok(match, `missing CSS rule for ${selector}`);
  const propMatch = match[1].match(new RegExp(`${escapeRegExp(prop)}\\s*:\\s*([^;]+)`, "i"));
  assert.ok(propMatch, `missing ${prop} on ${selector}`);
  return propMatch[1].trim();
}

function remOf(selector: string): number {
  const value = cssDecl(selector, "font-size");
  const match = value.match(/^([\d.]+)rem$/i);
  assert.ok(match, `${selector} font-size must be rem, got ${value}`);
  return Number(match[1]);
}

function assertRemAtLeast(selector: string, min: number): void {
  const actual = remOf(selector);
  assert.ok(
    actual + 1e-9 >= min,
    `${selector} font-size ${actual}rem must be >= ${min}rem`,
  );
}

function assertColor(selector: string, expected: string): void {
  assert.equal(cssDecl(selector, "color").toLowerCase(), expected.toLowerCase());
}

/* Home — A scale floors */
assertRemAtLeast(".ops-home-freshness", 0.82);
assertRemAtLeast(".ops-home-kpi em", 0.82);
assertRemAtLeast(".ops-home-kpi strong", 1.55);
assertRemAtLeast(".ops-home-kpi span", 0.78);
assertRemAtLeast(".ops-home-panel__head h2", 1.02);
assertRemAtLeast(".ops-home-panel__link", 0.78);
assertRemAtLeast(".ops-home-statstrip em", 0.78);
assertRemAtLeast(".ops-home-statstrip strong", 0.86);
assertRemAtLeast(".ops-home-block h3", 0.82);
assertRemAtLeast(".ops-home-empty", 0.84);
assertRemAtLeast(".ops-home-chip", 0.78);
assertRemAtLeast(".ops-home-jobs code, .ops-home-failures code", 0.78);
assertRemAtLeast(".ops-home-queue-mix__legend", 0.78);
assertRemAtLeast(".ops-home-daybar em", 0.72);
assertRemAtLeast(".ops-home-daybar strong", 0.78);
assertRemAtLeast(".ops-home-attention span", 0.8);
assertRemAtLeast(".ops-home-fetch", 0.8);

/* Home — B contrast */
assertColor(".ops-home-freshness", "#4b5563");
assertColor(".ops-home-kpi em", "#4b5563");
assertColor(".ops-home-kpi span", "#6b7280");
assertColor(".ops-home-block h3", "#4b5563");
assertColor(".ops-home-empty", "#6b7280");
assertColor(".ops-home-chip em", "#4b5563");
assertColor(".ops-home-jobs span, .ops-home-accounts span", "#4b5563");
assertColor(".ops-home-queue-mix__legend", "#4b5563");
assertColor(".ops-home-daybar em", "#6b7280");
assertColor(".ops-home-attention span", "#4b5563");
assertColor(".ops-home-fetch", "#4b5563");

/* Health — A scale floors (dense path included) */
assertRemAtLeast(".ops-health-freshness", 0.84);
assertRemAtLeast(".ops-health-freshness.is-inline", 0.82);
assertRemAtLeast(".ops-health-actions a", 0.78);
assertRemAtLeast(".ops-health-card__label", 0.82);
assertRemAtLeast(".ops-health-page.is-dense .ops-health-card__value", 1.18);
assertRemAtLeast(".ops-health-card__detail", 0.78);
assertRemAtLeast(".ops-health-card__badge", 0.74);
assertRemAtLeast(".ops-health-page.is-dense .ops-health-card__badge", 0.7);
assertRemAtLeast(".ops-health-panel__link", 0.78);
assertRemAtLeast(".ops-health-page.is-dense .ops-health-panel__head h2", 0.98);
assertRemAtLeast(".ops-health-stat em", 0.78);
assertRemAtLeast(".ops-health-stat strong", 0.86);
assertRemAtLeast(".ops-health-block h3", 0.82);
assertRemAtLeast(".ops-health-meta", 0.8);
assertRemAtLeast(".ops-health-queue-mix__legend", 0.78);
assertRemAtLeast(".ops-health-daybar em", 0.72);
assertRemAtLeast(".ops-health-daybar strong", 0.78);
assertRemAtLeast(".ops-health-asset code, .ops-health-account code", 0.78);
assertRemAtLeast(".ops-health-matrix", 0.78);
assertRemAtLeast(".ops-health-matrix thead th", 0.7);
assertRemAtLeast(".ops-health-chip", 0.78);

/* Health — B contrast */
assertColor(".ops-health-freshness", "#4b5563");
assertColor(".ops-health-card__label", "#4b5563");
assertColor(".ops-health-card__detail", "#6b7280");
assertColor(".ops-health-block h3", "#4b5563");
assertColor(".ops-health-meta", "#6b7280");
assertColor(".ops-health-stat em", "#4b5563");
assertColor(".ops-health-queue-mix__legend", "#4b5563");
assertColor(".ops-health-daybar em", "#6b7280");
assertColor(".ops-health-asset span, .ops-health-account span", "#4b5563");
assertColor(".ops-health-matrix thead th", "#4b5563");

/* V11 — the selectors used by the live Home V6–V9 and Health V4–V10 layouts. */
const v11Marker = "/* Ops typography V11";
const v11Start = css.indexOf(v11Marker);
assert.ok(v11Start >= 0, "CSS must define the live Ops typography V11 layer");
const v11 = css.slice(v11Start);

function assertV11TokenUse(selector: string, token: string): void {
  const selectorStart = v11.indexOf(selector);
  assert.ok(selectorStart >= 0, `V11 must cover ${selector}`);
  const blockEnd = v11.indexOf("}", selectorStart);
  assert.ok(blockEnd > selectorStart, `V11 rule for ${selector} must close`);
  const rule = v11.slice(selectorStart, blockEnd + 1);
  assert.match(rule, new RegExp(`font-size\\s*:\\s*var\\(--${escapeRegExp(token)}\\)`), `${selector} must use --${token}`);
}

const semanticTokens = [...v11.matchAll(/--ops-type-[\w-]+:\s*([\d.]+)rem/g)].map((match) => Number(match[1]));
assert.ok(semanticTokens.length >= 8, "V11 must define the complete semantic type scale");
assert.ok(semanticTokens.every((value) => value >= 0.6875), "No Ops typography token may fall below 11px at a 16px root");

assertV11TokenUse(".ops-home-v6 .ops-home-v6-panel__head h2", "ops-type-panel-title");
assertV11TokenUse(".ops-home-v6 .ops-home-v6-incident__copy strong", "ops-type-body");
assertV11TokenUse(".ops-home-v6 .ops-home-v6-axis", "ops-type-axis");
assertV11TokenUse(".ops-home-v6 .ops-home-v9-risk__evidence small", "ops-type-meta");
assertV11TokenUse(".ops-health-page .ops-health-v2-command p", "ops-type-body");
assertV11TokenUse(".ops-health-page .ops-health-v4-flow-node__copy > strong", "ops-type-data");
assertV11TokenUse(".ops-health-page .ops-health-v7-ledger__copy > strong", "ops-type-body");
assertV11TokenUse(".ops-health-page .ops-health-v8-zone > header h3", "ops-type-body");
assertV11TokenUse(".ops-health-page .ops-health-v10-columns__plot > aside", "ops-type-axis");
assertV11TokenUse(".ops-health-page .ops-health-v10-columns__head nav span", "ops-type-meta");

assert.match(pkg, /ops-type-scale\.test\.ts/, "package.json must run ops-type-scale test");

console.log("ops-type-scale tests passed");
