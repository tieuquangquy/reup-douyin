/** Classify result sheet — match Insights/Tracking band language in Drawer v6000. */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const testDir = dirname(fileURLToPath(import.meta.url));
const webSrc = resolve(testDir, "..");
const page = readFileSync(resolve(webSrc, "components/operator-routes/PublicationClassificationPanel.tsx"), "utf8");
const cssAll = readFileSync(resolve(webSrc, "app/globals.css"), "utf8");

const marker = "/* Workbench Drawer v6000";
const start = cssAll.indexOf(marker);
assert.ok(start >= 0, "Workbench Drawer v6000 CSS block must exist");
const css = cssAll.slice(start, start + 180_000);

assert.match(
  page,
  /function shortVersionLabel\([\s\S]{0,280}?split\(":"\)/,
  "Classifier/taxonomy version labels must shorten at the colon so prompt hashes do not crowd the result band",
);

assert.match(
  css,
  /is-v6000[\s\S]{0,160}?publication-classification-result\.is-sheet \{[\s\S]{0,320}?background:\s*#f4f8f6[\s\S]{0,220}?grid-template-columns:\s*repeat\(3/,
  "Classify result must read as one quiet mint band like Insights metrics",
);

assert.match(
  css,
  /is-v6000[\s\S]{0,160}?publication-classification-result\.is-sheet > div \{[\s\S]{0,200}?background:\s*transparent[\s\S]{0,120}?border:\s*0/,
  "Result cells must stay flush inside the band without nested wells",
);

assert.doesNotMatch(
  css,
  /is-v6000[\s\S]{0,160}?publication-classification-result\.is-sheet > div \{[^}]*linear-gradient/,
  "Result cells must not paint nested gradient wells",
);

assert.match(
  css,
  /is-v6000[\s\S]{0,160}?publication-classification-insight \{[\s\S]{0,320}?background:\s*#f4f8f6[\s\S]{0,200}?border:\s*1px solid\s*#d9e7df/,
  "Insight/runtime/why must sit in one mint band",
);

assert.match(
  css,
  /is-v6000[\s\S]{0,200}?publication-classification-runtime \{[\s\S]{0,200}?background:\s*transparent[\s\S]{0,120}?border:\s*0/,
  "Runtime row must stay flush inside the insight band",
);

assert.match(
  css,
  /is-v6000[\s\S]{0,200}?publication-classification-rationale \{[\s\S]{0,280}?background:\s*transparent[\s\S]{0,200}?border-top:\s*1px solid\s*#d9e7df/,
  "Why this result must be a divider note, not a nested blue card",
);

assert.doesNotMatch(
  css,
  /is-v6000[\s\S]{0,200}?publication-classification-rationale \{[^}]*#f5f8ff/,
  "Rationale must not keep the legacy blue boxed fill on v6000",
);

assert.match(
  css,
  /is-v6000[\s\S]{0,160}?publication-classification-evidence \{[\s\S]{0,280}?background:\s*#f4f8f6/,
  "Evidence must use the same quiet mint band",
);

assert.match(
  css,
  /is-v6000[\s\S]{0,200}?publication-classification-evidence article \{[\s\S]{0,200}?background:\s*transparent[\s\S]{0,120}?border:\s*0/,
  "Evidence articles must stay flush without nested grey cards",
);

assert.match(
  css,
  /is-v6000[\s\S]{0,200}?publication-classification-actions \{[\s\S]{0,200}?border-top:\s*1px solid\s*#cfdfd6/,
  "Classify actions must sit on a quiet divider like Tracking footer",
);

assert.match(
  css,
  /is-v6000[\s\S]{0,220}?publication-classification-actions[\s\S]{0,280}?async-button\.primary \{[\s\S]{0,200}?background:\s*#12352c/,
  "Approve must read as the primary workbench CTA",
);

console.log("publication-library-classify-result-v6000: PASS");
