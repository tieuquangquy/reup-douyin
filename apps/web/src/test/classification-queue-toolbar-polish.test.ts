/** Classification Queue filter toolbar: icon actions + editorial polish. */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const webSrc = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const queue = readFileSync(resolve(webSrc, "components/operator-routes/ContentClassificationQueue.tsx"), "utf8");
const cssFull = readFileSync(resolve(webSrc, "app/globals.css"), "utf8");
const marker = "/* Classification Queue Toolbar Polish v19";
const start = cssFull.indexOf(marker);
assert.ok(start >= 0, "v19 classification toolbar polish block must exist");
const css = cssFull.slice(start, start + 3500);

assert.match(
  queue,
  /classification-queue-toolbar is-v19/,
  "Toolbar must opt into v19 editorial polish",
);
assert.match(
  queue,
  /className="classification-queue-toolbar__icon-btn is-apply"[\s\S]*?type="submit"/,
  "Apply must be an icon submit control",
);
assert.match(
  queue,
  /aria-label=\{t\("classificationQueue\.apply"\)\}/,
  "Apply must expose an accessible label",
);
assert.match(
  queue,
  /className="classification-queue-toolbar__icon-btn is-refresh"[\s\S]*?aria-label=\{t\("common\.refresh"\)\}|aria-label=\{t\("common\.refresh"\)\}[\s\S]*?className="classification-queue-toolbar__icon-btn is-refresh"/,
  "Refresh must be an accessible icon control",
);
assert.match(
  queue,
  /leadingIcon=\{<ClassificationToolbarGlyph kind="(?:search|refresh)" \/>\}/,
  "Icon actions must use ClassificationToolbarGlyph leading icons",
);
assert.doesNotMatch(
  queue,
  /AsyncButton pending=\{loading\} type="submit">\{t\("classificationQueue\.apply"\)\}<\/AsyncButton>/,
  "Apply must not render as a text-only AsyncButton",
);
assert.doesNotMatch(
  queue,
  /onClick=\{\(\) => void load\(true\)\}>\{t\("common\.refresh"\)\}<\/AsyncButton>/,
  "Refresh must not render as a text-only AsyncButton",
);
assert.match(
  css,
  /toolbar\.is-v19[\s\S]{0,280}?background:\s*(#fff|#ffffff|white)/,
  "v19 toolbar must sit on a white editorial surface",
);
assert.match(
  css,
  /icon-btn[\s\S]{0,500}?width:\s*2\.35rem/,
  "v19 icon actions must be compact square controls",
);
assert.match(
  css,
  /icon-btn[\s\S]{0,280}?\.async-button__label[\s\S]{0,160}?clip:|icon-btn[\s\S]{0,280}?visually-hidden/,
  "v19 must visually hide AsyncButton text labels on icon actions",
);
assert.doesNotMatch(
  queue,
  /classification-queue-toolbar is-v19[\s\S]*?<span>\{t\("classificationQueue\.(page|status|search)"\)\}<\/span>/,
  "Toolbar must not show Page / Status / Search field labels above controls",
);
assert.match(
  queue,
  /<select[\s\S]{0,120}?aria-label=\{t\("classificationQueue\.page"\)\}|aria-label=\{t\("classificationQueue\.page"\)\}[\s\S]{0,80}?onChange=\{\(event\) => setAccountFilter/,
  "Page select must keep an accessible name without a visible label",
);
assert.match(
  queue,
  /aria-label=\{t\("classificationQueue\.status"\)\}/,
  "Status select must keep an accessible name without a visible label",
);
assert.match(
  queue,
  /aria-label=\{t\("classificationQueue\.search"\)\}/,
  "Search input must keep an accessible name without a visible label",
);
assert.match(
  queue,
  /classification-queue-low-confidence[\s\S]*?onlyLowConfidence/,
  "Low-confidence checkbox must keep its visible text",
);

console.log("classification-queue-toolbar-polish: PASS");
