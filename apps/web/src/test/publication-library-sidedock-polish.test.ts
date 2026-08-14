/** Publication Library sidedock v1810: spark AI CTA, polished nav tiles, no fake "AI" badge. */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const webSrc = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const page = readFileSync(resolve(webSrc, "components/operator-routes/PublicationLibraryPage.tsx"), "utf8");
const cssFull = readFileSync(resolve(webSrc, "app/globals.css"), "utf8");

const v1810Start = cssFull.indexOf("/* Publication Library Sidedock v1810");
assert.ok(v1810Start >= 0, "v1810 sidedock polish CSS block must exist");
const v1810 = cssFull.slice(v1810Start, v1810Start + 8000);

assert.match(page, /publication-library-sidedock is-v330[\s\S]{0,120}?is-v1810/, "Sidedock must opt into v1810");
assert.match(
  page,
  /publication-library-sidedock__ai[\s\S]{0,180}?PublicationLibraryIcon kind="spark"/,
  "Configure Topic AI must use the spark glyph instead of settings-only chrome",
);
assert.match(page, /configureAi/, "AI settings shortcut copy must remain");

assert.match(v1810, /\.publication-library-sidedock\.is-v1810/, "v1810 CSS must scope to sidedock mark");
assert.match(v1810, /sidedock__ai[\s\S]{0,400}?publication-library-icon[\s\S]{0,120}?display:\s*(?:flex|inline-flex|block)/, "v1810 must show the real AI icon");
assert.match(v1810, /sidedock__ai::before[\s\S]{0,120}?display:\s*none|content:\s*none/, "v1810 must remove the fake AI text badge");
assert.doesNotMatch(v1810, /content:\s*"AI"/, "v1810 must not reintroduce content:\"AI\"");
assert.match(v1810, /sidedock__views button\.is-active/, "v1810 must restyle active nav tiles");

console.log("publication-library-sidedock-polish: PASS");
