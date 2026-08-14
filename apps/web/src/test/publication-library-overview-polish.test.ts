/** Focused contract: Publication Library populated overview polish v2630. */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const webSrc = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const page = readFileSync(resolve(webSrc, "components/operator-routes/PublicationLibraryPage.tsx"), "utf8");
const cssFull = readFileSync(resolve(webSrc, "app/globals.css"), "utf8");
const marker = "/* Publication Library Overview Polish v2630";
const start = cssFull.indexOf(marker);
const end = cssFull.indexOf("/* Publication Library Slim Command Bar v2400", start);
assert.ok(start >= 0, "v2630 CSS block must exist");
assert.ok(end > start, "v2630 CSS block must end before Slim Command Bar v2400");
const css = cssFull.slice(start, end);

assert.match(
  page,
  /publication-library-briefing is-v2500[\s\S]*is-v2620 is-v2630/,
  "Populated briefing must opt into the v2630 overview polish",
);
assert.match(
  css,
  /briefing\.is-v2630 \{[\s\S]{0,500}?--pl-ov-axis:\s*0\.6875rem[\s\S]{0,200}?--pl-ov-data:\s*0\.875rem[\s\S]{0,200}?--pl-ov-label-quiet:\s*#6b8278[\s\S]{0,120}?--pl-ov-label-strong:\s*#2a4d41/,
  "v2630 must publish one overview type scale and quiet/strong label colors",
);
assert.match(
  css,
  /briefing\.is-v2630[\s\S]{0,2200}?briefing__action[\s\S]{0,280}?background:\s*(#f4f8f6|var\(--pl-ov-mint\))/,
  "v2630 sync action panel must drop the heavy dark slab for a quiet mint surface",
);
assert.match(
  css,
  /briefing\.is-v2630[\s\S]{0,2800}?metric-track[\s\S]{0,200}?background:\s*#(e[0-9a-f]{5}|d[ce][0-9a-f]{4})/i,
  "v2630 zero meter tracks must stay whisper-soft against the briefing",
);
assert.match(
  css,
  /is-v2630[\s\S]{0,1200}?sheet thead th[\s\S]{0,220}?color:\s*var\(--pl-ov-label-quiet\)/,
  "v2630 roster headers must use the quiet label token",
);

console.log("publication-library-overview-polish: PASS");
