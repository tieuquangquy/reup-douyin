import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const testDir = dirname(fileURLToPath(import.meta.url));
const visualSource = readFileSync(
  resolve(testDir, "../components/final-review/FinalReviewVisualCheckpoint.tsx"),
  "utf8"
);
const cssSource = readFileSync(resolve(testDir, "../app/globals.css"), "utf8");
const en = JSON.parse(readFileSync(resolve(testDir, "../lib/i18n/en.json"), "utf8")) as {
  finalReviewVisual: Record<string, string>;
};

assert.match(visualSource, /final-visual-checkpoint__reanalyze-guard/, "Reanalyze block must keep the guard details shell");
assert.match(visualSource, /final-visual-checkpoint__reanalyze-body/, "Reanalyze warning + CTA must sit in a dedicated body");
assert.match(visualSource, /final-visual-checkpoint__reanalyze-warn/, "Warning copy must use a dedicated warn class");
assert.match(visualSource, /final-visual-checkpoint__reanalyze-cta/, "Re-analyze must use a dedicated quiet CTA class");
assert.match(visualSource, /window\.confirm\(t\("finalReviewVisual\.reanalyzeConfirm"\)\)/, "Destructive reanalyze must keep confirm");
assert.match(cssSource, /\.final-visual-checkpoint__reanalyze-guard\b/, "Reanalyze guard must be styled");
assert.match(cssSource, /\.final-visual-checkpoint__reanalyze-guard\s*>\s*summary::-webkit-details-marker|\.final-visual-checkpoint__reanalyze-guard summary::-webkit-details-marker/, "Default details marker must be replaced");
assert.match(cssSource, /\.final-visual-checkpoint__reanalyze-cta\b/, "Reanalyze CTA styles must exist");
assert.match(en.finalReviewVisual.reanalyzeAdvanced, /Advanced/i, "Advanced summary label must stay operator-readable");
assert.ok(en.finalReviewVisual.reanalyzeAdvanced.length <= 28, "Advanced summary must stay compact");

console.log("final-review reanalyze polish tests passed");
