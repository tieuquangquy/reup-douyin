/** Operator sidebar hover must not slide a white card off the mint rail. */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const cssFull = readFileSync(resolve(dirname(fileURLToPath(import.meta.url)), "../app/globals.css"), "utf8");
const v16Start = cssFull.indexOf("/* App shell V16");
assert.ok(v16Start >= 0, "App shell V16 CSS block must exist");
const v16 = cssFull.slice(v16Start, v16Start + 9000);

assert.doesNotMatch(
  v16,
  /\.app-nav-item:hover \{\s*transform:\s*translateX/,
  "Hover must not translate the nav row (that exposes a mint/white gutter)",
);
assert.doesNotMatch(
  v16,
  /is-operator \.app-nav-item:hover \{[\s\S]{0,140}?rgba\(255,\s*255,\s*255/,
  "Operator hover must not paint a floating white card on the mint rail",
);
assert.doesNotMatch(
  v16,
  /is-operator \.app-nav-item.active \{[\s\S]{0,140}?background:\s*#fff/,
  "Operator active row must not sit as a white inset card",
);
assert.match(
  v16,
  /is-operator[\s\S]{0,500}?padding-left:\s*0|is-operator \.app-nav-item \{[\s\S]{0,220}?margin-inline:\s*-12px/,
  "Operator nav fill must reach the rail edges instead of leaving a 12px gutter",
);
assert.match(
  v16,
  /is-operator \.app-nav-item:hover \{[\s\S]{0,160}?background:\s*(?:#e|#f[0-7]|var\(--pl-iq-mint\))/,
  "Operator hover must use a mint wash, not white paper",
);

console.log("app-shell-nav-hover: PASS");
