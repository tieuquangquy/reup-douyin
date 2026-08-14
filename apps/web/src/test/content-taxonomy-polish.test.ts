/** Topic Taxonomy Intelligence polish: v21 logical form layout groups. */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const webSrc = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const manager = readFileSync(resolve(webSrc, "components/operator-routes/ContentTaxonomyManager.tsx"), "utf8");
const cssFull = readFileSync(resolve(webSrc, "app/globals.css"), "utf8");
const v21Start = cssFull.indexOf("/* Content Taxonomy Form Layout v21");
assert.ok(v21Start >= 0, "v21 form layout polish CSS block must exist");
const v21 = cssFull.slice(v21Start, v21Start + 5000);

assert.match(manager, /is-v20 is-v21|is-v21/, "Taxonomy page must opt into v21");
assert.match(manager, /content-taxonomy-fields is-v19 is-v21|fields[\s\S]{0,40}?is-v21/, "Editor fields must opt into v21 layout");
assert.match(manager, /content-taxonomy-create[\s\S]{0,80}?is-v21/, "Create form must opt into v21 layout");
assert.match(v21, /repeat\(12,\s*minmax\(0,\s*1fr\)\)/, "v21 uses a 12-column form grid");
assert.match(v21, /is-name[\s\S]{0,120}?grid-column:\s*1\s*\/\s*6/, "Name occupies the primary identity band");
assert.match(v21, /is-keywords[\s\S]{0,120}?grid-column:\s*1\s*\/\s*8/, "Keywords span the wider content band");
assert.match(v21, /is-description[\s\S]{0,120}?grid-column:\s*8\s*\/\s*13/, "Description sits beside keywords");
assert.match(v21, /is-code[\s\S]{0,120}?grid-column:\s*1\s*\/\s*4/, "Create code stays in a compact leading column");

console.log("content-taxonomy-polish: PASS");
