import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const testDir = dirname(fileURLToPath(import.meta.url));
const cardSource = readFileSync(resolve(testDir, "../components/risk/RiskSummaryCard.tsx"), "utf8");
const cssSource = readFileSync(resolve(testDir, "../app/globals.css"), "utf8");
const en = JSON.parse(readFileSync(resolve(testDir, "../lib/i18n/en.json"), "utf8")) as {
  riskSummary: Record<string, string>;
};
const vi = JSON.parse(readFileSync(resolve(testDir, "../lib/i18n/vi.json"), "utf8")) as {
  riskSummary: Record<string, string>;
};

assert.match(cardSource, /fr-risk/, "Risk card must use compact fr-risk layout");
assert.match(cardSource, /fr-risk__row/, "Flags must render as compact rows");
assert.match(cardSource, /title=\{/, "Flag details stay available via title tooltip");
assert.doesNotMatch(
  cardSource,
  /flag\.description[\s\S]*?<p>|flag\.evidence_summary[\s\S]*?<small>/,
  "Compact risk must not always show long description/evidence under every flag"
);
assert.match(cardSource, /fr-risk__decisions/, "Operator decisions must stay in a compact row");
assert.match(cssSource, /\.fr-risk/, "Compact risk styles must exist");

assert.ok(en.riskSummary.hintShort.length > 0);
assert.ok(vi.riskSummary.hintShort.length > 0);
assert.ok(en.riskSummary.acceptWithWarning.length <= 18, "EN accept label should stay short");
assert.ok(vi.riskSummary.acceptWithWarning.length <= 16, "VI accept label should stay short");

console.log("final-review risk compact tests passed");
