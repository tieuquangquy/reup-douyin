/** Classify empty state — match Tracking/Insights band language in Drawer v6000. */
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
  /publication-classification-empty[\s\S]{0,400}?contentClassification\.run/,
  "Classify empty state must keep Run classification CTA",
);

assert.match(
  css,
  /inspector-panel\.is-v6000 > \.publication-classification \{[\s\S]{0,280}?display:\s*grid[\s\S]{0,160}?gap:\s*[0-9.]+rem/,
  "Classify panel must use a clear vertical stack on the stage",
);

assert.match(
  css,
  /is-v6000[\s\S]{0,120}?publication-classification > header \{[\s\S]{0,220}?justify-content:\s*space-between/,
  "Classify header must keep title block on one row",
);

assert.match(
  css,
  /is-v6000[\s\S]{0,160}?publication-classification-empty \{[\s\S]{0,320}?background:\s*#f4f8f6[\s\S]{0,200}?border:\s*1px solid\s*#d9e7df/,
  "Classify empty must read as one quiet mint band",
);

assert.doesNotMatch(
  css,
  /is-v6000[\s\S]{0,200}?publication-classification-empty \{[^}]*dashed/,
  "Classify empty must not keep the legacy dashed card border",
);

assert.match(
  css,
  /is-v6000[\s\S]{0,200}?publication-classification-empty[\s\S]{0,200}?async-button\.primary \{[\s\S]{0,420}?min-height:\s*2\.5rem/,
  "Run classification must use the workbench primary CTA size",
);

assert.match(
  css,
  /is-v6000[\s\S]{0,200}?publication-classification-empty[\s\S]{0,200}?async-button\.primary \{[\s\S]{0,420}?white-space:\s*nowrap/,
  "Run classification label must stay on one line",
);

console.log("publication-library-classify-empty-v6000: PASS");
