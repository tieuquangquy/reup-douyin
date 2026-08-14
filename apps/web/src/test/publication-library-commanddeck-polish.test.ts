/** Focused contract: Publication Library pre-sync command deck polish v1870. */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const webSrc = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const page = readFileSync(resolve(webSrc, "components/operator-routes/PublicationLibraryPage.tsx"), "utf8");
const cssFull = readFileSync(resolve(webSrc, "app/globals.css"), "utf8");
const marker = "/* Publication Library Command Deck Polish v1870";
const start = cssFull.indexOf(marker);
const end = cssFull.indexOf("/* Publication Library Post-sync Receipt Workspace v1900", start);
assert.ok(start >= 0, "v1870 CSS block must exist");
assert.ok(end > start, "v1870 CSS block must end before v1900");
const css = cssFull.slice(start, end);

assert.match(
  page,
  /publication-library-commanddeck is-v1800 is-v1870[\s\S]*commanddeck__outcomes is-v1870/,
  "Pre-sync command deck must opt into the v1870 polish surface",
);
assert.match(
  css,
  /commanddeck\.is-v1870 \{[\s\S]{0,500}?--pl-cd-axis:\s*0\.6875rem[\s\S]{0,200}?--pl-cd-data:\s*0\.875rem[\s\S]{0,200}?--pl-cd-label-quiet:\s*#6b8278[\s\S]{0,120}?--pl-cd-label-strong:\s*#2a4d41/,
  "v1870 must publish one command-deck type scale and quiet/strong label colors",
);
assert.match(
  css,
  /commanddeck\.is-v1870[\s\S]{0,1200}?commanddeck__canvas::before[\s\S]{0,160}?opacity:\s*0/,
  "v1870 canvas must drop the busy grid overlay so the hero reads as one composition",
);
assert.match(
  css,
  /commanddeck\.is-v1870[\s\S]{0,1800}?commanddeck__canvas-head[\s\S]{0,220}?background:\s*(#f4f8f6|var\(--pl-cd-mint\))/,
  "v1870 status head must use a quiet mint strip instead of a competing pill row",
);
assert.match(
  css,
  /outcomes\.is-v1870 li[\s\S]{0,280}?background:\s*transparent[\s\S]{0,160}?border:\s*0/,
  "v1870 outcomes must read as a soft step rail, not three heavy cards",
);

console.log("publication-library-commanddeck-polish: PASS");
