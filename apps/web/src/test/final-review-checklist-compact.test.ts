import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const testDir = dirname(fileURLToPath(import.meta.url));
const checklistSource = readFileSync(
  resolve(testDir, "../components/final-review/FinalReviewChecklist.tsx"),
  "utf8"
);
const cssSource = readFileSync(resolve(testDir, "../app/globals.css"), "utf8");
const en = JSON.parse(readFileSync(resolve(testDir, "../lib/i18n/en.json"), "utf8")) as {
  finalReviewChecklist: { title: string; markAll: string; clearAll: string; items: Record<string, string> };
};
const vi = JSON.parse(readFileSync(resolve(testDir, "../lib/i18n/vi.json"), "utf8")) as {
  finalReviewChecklist: { title: string; markAll: string; clearAll: string; items: Record<string, string> };
};

assert.match(checklistSource, /fr-check/, "Checklist must use compact fr-check layout");
assert.match(checklistSource, /onSetAll|markAll/, "Checklist must offer mark-all for fast QA");
assert.doesNotMatch(
  checklistSource,
  /checklist-row[\s\S]*<small>/,
  "Compact checklist must not always show long hint text under every row"
);
assert.match(checklistSource, /title=\{/, "Hints stay available via title tooltip");
assert.match(cssSource, /\.fr-check/, "Compact checklist styles must exist");

assert.ok(en.finalReviewChecklist.markAll.length > 0);
assert.ok(vi.finalReviewChecklist.markAll.length > 0);
assert.ok(en.finalReviewChecklist.items.narration_clear.length <= 28, "EN labels should stay short");
assert.ok(vi.finalReviewChecklist.items.narration_clear.length <= 24, "VI labels should stay short");

console.log("final-review checklist compact tests passed");
