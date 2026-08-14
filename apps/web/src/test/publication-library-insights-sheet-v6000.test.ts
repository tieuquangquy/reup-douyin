/** Insights panel sheet continuity — match Overview workbench band language in Drawer v6000. */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const testDir = dirname(fileURLToPath(import.meta.url));
const webSrc = resolve(testDir, "..");
const page = readFileSync(resolve(webSrc, "components/operator-routes/PublicationLibraryPage.tsx"), "utf8");
const cssAll = readFileSync(resolve(webSrc, "app/globals.css"), "utf8");
const en = readFileSync(resolve(webSrc, "lib/i18n/en.json"), "utf8");
const vi = readFileSync(resolve(webSrc, "lib/i18n/vi.json"), "utf8");
const marker = "/* Workbench Drawer v6000";
const start = cssAll.indexOf(marker);
assert.ok(start >= 0, "Workbench Drawer v6000 CSS block must exist");
const css = cssAll.slice(start, start + 120_000);

assert.match(
  page,
  /inspectorTab === "INSIGHTS"[\s\S]{0,1600}?publication-library-growth[\s\S]{0,9000}?publication-library-velocity-guidance/,
  "Velocity guidance must sit inside the Insights growth section for sheet rhythm",
);

assert.match(
  css,
  /inspector-panel\.is-v6000 > \.publication-library-growth \{[\s\S]{0,280}?display:\s*grid[\s\S]{0,160}?gap:\s*[0-9.]+rem/,
  "Insights growth must use a clear vertical stack on the stage",
);

assert.match(
  css,
  /is-v6000[\s\S]{0,80}?publication-library-growth > header \{[\s\S]{0,220}?justify-content:\s*space-between/,
  "Insights header must keep title and status on one row",
);

assert.match(
  css,
  /is-v6000[\s\S]{0,120}?publication-library-metrics\.is-sheet \{[\s\S]{0,320}?background:\s*#f4f8f6[\s\S]{0,220}?grid-template-columns:\s*repeat\(3/,
  "Insights metrics must read as one quiet band like Overview signals",
);

assert.match(
  css,
  /is-v6000[\s\S]{0,120}?publication-library-metrics\.is-sheet > div \{[\s\S]{0,200}?background:\s*transparent[\s\S]{0,120}?border:\s*0/,
  "Insight metric cells must stay flush inside the band without nested wells",
);

assert.doesNotMatch(
  css,
  /is-v6000[\s\S]{0,120}?publication-library-metrics\.is-sheet > div \{[^}]*linear-gradient/,
  "Insight metric cells must not paint nested gradient wells",
);

assert.match(
  css,
  /is-v6000[\s\S]{0,280}?publication-library-velocity-guidance \{[\s\S]{0,360}?background:\s*transparent[\s\S]{0,280}?border-top:\s*1px solid\s*#cfdfd6|is-v6000[\s\S]{0,280}?publication-library-velocity-guidance \{[\s\S]{0,360}?border-top:\s*1px solid\s*#cfdfd6[\s\S]{0,280}?background:\s*transparent/,
  "Velocity guidance must be a quiet divider note, not a floating amber card",
);

assert.doesNotMatch(
  css,
  /is-v6000[\s\S]{0,200}?publication-library-velocity-guidance \{[^}]*#fff8e9/,
  "Velocity guidance must not keep the legacy amber boxed fill on v6000",
);

assert.match(
  css,
  /is-v6000[\s\S]{0,160}?publication-library-insights-actions[\s\S]{0,280}?async-button/,
  "Check readiness CTA must be styled in the Insights actions row",
);

assert.match(
  page,
  /!preflight\?\.ready_for_live_job[\s\S]{0,280}?publication-library-insights-actions[\s\S]{0,400}?checkInsights/,
  "Check readiness must hide once Insights readiness already passed",
);

assert.match(
  page,
  /publicationLibrary\.trendLabel\.\$\{growth\?\.trend_label \?\? "NO_DATA"\}/,
  "Insights status pill must use trendLabel i18n instead of raw NO_DATA",
);

assert.match(
  page,
  /className="publication-library-insights-gate is-ready"/,
  "Passed readiness must render as one insights-gate is-ready surface",
);

assert.doesNotMatch(
  page,
  /ready_for_live_job \? \([\s\S]{0,200}?preflight-result is-ready/,
  "Passed readiness must not nest a separate preflight-result card above authorize",
);

assert.match(
  css,
  /insights-gate\.is-ready \{[\s\S]{0,320}?background:\s*#f4f8f6[\s\S]{0,200}?border:\s*1px solid\s*#d9e7df/,
  "Ready gate must be one quiet mint band",
);

assert.match(
  css,
  /insights-gate\.is-ready[\s\S]{0,200}?publication-library-authorize \{[\s\S]{0,200}?background:\s*transparent[\s\S]{0,120}?border:\s*0/,
  "Authorize row must stay flush inside the ready gate without a nested mint card",
);

assert.match(
  css,
  /metrics\.is-sheet > div > b\.is-empty \{[\s\S]{0,120}?color:\s*#9aafa5/,
  "Idle metric dashes must read muted instead of ink-black",
);

assert.match(en, /"trendLabel"[\s\S]{0,120}"NO_DATA":\s*"No data"/, "English trendLabel must include No data");
assert.match(vi, /"trendLabel"[\s\S]{0,120}"NO_DATA":/, "Vietnamese trendLabel must include NO_DATA");

console.log("publication-library-insights-sheet-v6000: PASS");
