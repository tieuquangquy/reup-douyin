/** Focused contract: Publication Library Intelligence polish + spectrum + v26 editorial sheet. */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const webSrc = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const page = readFileSync(resolve(webSrc, "components/operator-routes/PublicationLibraryPage.tsx"), "utf8");
const queue = readFileSync(resolve(webSrc, "components/operator-routes/ContentClassificationQueue.tsx"), "utf8");
const cssFull = readFileSync(resolve(webSrc, "app/globals.css"), "utf8");
const marker = "/* Publication Library Intelligence Workspace v10";
const start = cssFull.indexOf(marker);
const endMarker = "/* Publication Library v21";
const end = cssFull.indexOf(endMarker, start);
assert.ok(start >= 0, "v10 Intelligence CSS block must exist");
assert.ok(end > start, "v10 Intelligence CSS block must end before Library v21");
const css = cssFull.slice(start, end);
const v26Start = css.indexOf("Publication Library Intelligence Polish v26");
assert.ok(v26Start >= 0, "v26 editorial workspace sheet polish block must exist");
const v26 = css.slice(v26Start);

assert.match(
  page,
  /publication-library-intelligence is-v10[\s\S]*is-v25 is-v26/,
  "Intelligence must opt into v26 editorial sheet",
);
assert.match(
  page,
  /publication-library-intelligence__kicker[\s\S]*publicationLibrary\.intelligenceTab/,
  "v26 must restore a quiet Intelligence meta kicker",
);
assert.doesNotMatch(
  page,
  /publication-library-intelligence__eyebrow/,
  "Redundant Intelligence Tools eyebrow must stay removed",
);
assert.match(
  page,
  /intelligenceLane === "CLASSIFICATION"[\s\S]*classificationTab[\s\S]*TAXONOMY[\s\S]*taxonomyTab[\s\S]*PRODUCT_MATCHING[\s\S]*productMatchingTab[\s\S]*opportunityRankingTab|classificationTab[\s\S]*taxonomyTab[\s\S]*productMatchingTab[\s\S]*opportunityRankingTab/,
  "H2 must resolve from the active intelligence lane",
);
assert.match(
  page,
  /publication-library-intelligence__head[\s\S]*intelligence-nav is-v10[\s\S]*is-v26[\s\S]*<\/header>/,
  "Lane nav must stay inside the editorial sheet header",
);
assert.match(
  queue,
  /classification-queue-spectrum__donut/,
  "Spectrum must keep a donut chart element",
);
assert.match(
  queue,
  /barScale\s*=\s*Math\.max\(\s*kpis\.total_publications/,
  "Attention bars must scale against total publications",
);
assert.doesNotMatch(
  queue,
  /classification-queue-kpis/,
  "Five flat KPI cards must stay replaced by the spectrum chart",
);
assert.match(
  css,
  /intelligence\.is-v10 \{[\s\S]{0,500}?--pl-iq-label-quiet:\s*#6b8278[\s\S]{0,120}?--pl-iq-label-strong:\s*#2a4d41/,
  "v10 must publish quiet/strong label colors",
);
assert.match(
  v26,
  /intelligence__head[\s\S]{0,320}?background:\s*(#fff|#ffffff|white)/,
  "v26 must use one white editorial sheet for the whole header",
);
assert.match(
  v26,
  /intelligence__head[\s\S]{0,360}?box-shadow:\s*0/,
  "v26 sheet must have a light elevation shadow",
);
assert.match(
  v26,
  /intelligence-nav\.is-v26[\s\S]{0,360}?background:\s*transparent/,
  "v26 nav must stay transparent inside the same white sheet (no second rail)",
);
assert.doesNotMatch(
  v26,
  /intelligence-nav\.is-v26[\s\S]{0,360}?background:\s*(#e8f0ec|#f4f8f6)/,
  "v26 must not reintroduce a mint/nav band fill",
);
assert.match(
  v26,
  /intelligence__settings[\s\S]{0,320}?border:\s*1px solid/,
  "v26 Configure must be a soft outline button",
);
assert.match(
  v26,
  /button\.is-active[\s\S]{0,280}?background:\s*(rgba\(|#f4f8f6|var\(--pl-iq-mint)|is-active[\s\S]{0,280}?border-bottom-color:\s*var\(--pl-iq-steady/,
  "v26 active lane must keep underline and a soft mint wash",
);
assert.match(
  v26,
  /intelligence__kicker|__kicker[\s\S]{0,200}?letter-spacing/,
  "v26 must style the Intelligence meta kicker",
);

console.log("publication-library-intelligence-polish: PASS");
