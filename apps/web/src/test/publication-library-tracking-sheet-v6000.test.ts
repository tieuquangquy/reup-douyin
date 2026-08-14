/** Tracking panel sheet continuity — match Overview/Insights workbench language in Drawer v6000. */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const testDir = dirname(fileURLToPath(import.meta.url));
const webSrc = resolve(testDir, "..");
const page = readFileSync(resolve(webSrc, "components/operator-routes/PublicationLibraryPage.tsx"), "utf8");
const cssAll = readFileSync(resolve(webSrc, "app/globals.css"), "utf8");

const marker = "/* Workbench Drawer v6000";
const start = cssAll.indexOf(marker);
assert.ok(start >= 0, "Workbench Drawer v6000 CSS block must exist");
const css = cssAll.slice(start, start + 160_000);

assert.match(
  page,
  /inspectorTab === "TRACKING"[\s\S]{0,800}?publication-library-tracking[\s\S]{0,2500}?tracking-setup/,
  "Tracking setup markup must remain under the Tracking panel",
);

assert.match(
  css,
  /inspector-panel\.is-v6000 > \.publication-library-tracking \{[\s\S]{0,280}?display:\s*grid[\s\S]{0,160}?gap:\s*[0-9.]+rem/,
  "Tracking panel must use a clear vertical stack on the stage",
);

assert.match(
  css,
  /is-v6000[\s\S]{0,80}?publication-library-tracking > header \{[\s\S]{0,220}?justify-content:\s*space-between/,
  "Tracking header must keep title block and status on one row",
);

assert.match(
  css,
  /is-v6000[\s\S]{0,120}?publication-library-tracking > header > span \{[\s\S]{0,280}?border-radius:\s*999px/,
  "Tracking status must use the Insights-style pill",
);

assert.match(
  css,
  /is-v6000[\s\S]{0,160}?publication-library-tracking-setup \{[\s\S]{0,320}?background:\s*#f4f8f6[\s\S]{0,200}?border:\s*1px solid\s*#d9e7df/,
  "Tracking setup must read as one quiet mint band",
);

assert.match(
  css,
  /is-v6000[\s\S]{0,200}?tracking-setup[\s\S]{0,120}?tracking-consent \{[\s\S]{0,200}?background:\s*transparent[\s\S]{0,120}?border:\s*0/,
  "Consent must stay flush inside the setup band without a nested card",
);

assert.match(
  css,
  /is-v6000[\s\S]{0,200}?tracking-enable \{[\s\S]{0,200}?border-top:\s*1px solid\s*#d9e7df/,
  "Window + Enable row must separate with a quiet divider inside the band",
);

assert.match(
  css,
  /is-v6000[\s\S]{0,160}?tracking-window \{[\s\S]{0,280}?border:\s*1px solid\s*#c9dbd1[\s\S]{0,200}?border-radius:\s*0\.75rem/,
  "Tracking window select must match draft-picker trigger language",
);

assert.match(
  css,
  /is-v6000[\s\S]{0,160}?tracking-facts\.is-sheet \{[\s\S]{0,320}?background:\s*#f4f8f6[\s\S]{0,220}?grid-template-columns:\s*repeat\(3/,
  "Active tracking facts must read as one signals-style band",
);

assert.match(
  css,
  /is-v6000[\s\S]{0,160}?tracking-facts\.is-sheet > div \{[\s\S]{0,200}?background:\s*transparent[\s\S]{0,120}?border:\s*0/,
  "Tracking fact cells must stay flush inside the band",
);

assert.doesNotMatch(
  css,
  /is-v6000[\s\S]{0,200}?tracking-setup \{[^}]*#fff8e9/,
  "Tracking setup must not use legacy amber fill",
);

console.log("publication-library-tracking-sheet-v6000: PASS");
