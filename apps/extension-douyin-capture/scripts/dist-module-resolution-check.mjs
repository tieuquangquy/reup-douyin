import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";

const root = process.cwd();
const dist = join(root, "dist");
const entrypoints = ["popup.js", "popupActions.js", "contentScript.js", "background.js"];
const relativeImportPattern = /(?:import|export)\s+(?:[^"']*?\s+from\s+)?["'](\.\.?\/[^"']+)["']/g;

for (const entrypoint of entrypoints) {
  const entrypointPath = join(dist, entrypoint);
  assert.equal(existsSync(entrypointPath), true, `${entrypoint} must be emitted into dist`);
  const content = readFileSync(entrypointPath, "utf-8");
  const imports = [...content.matchAll(relativeImportPattern)].map((match) => match[1]).filter(Boolean);

  for (const specifier of imports) {
    assert.equal(specifier.endsWith(".js"), true, `${entrypoint} imports ${specifier}, but browser ESM requires a .js extension`);
    const resolved = join(dist, specifier);
    assert.equal(existsSync(resolved), true, `${entrypoint} imports missing emitted module ${specifier}`);
  }
}

const popupHtml = readFileSync(join(dist, "popup.html"), "utf-8");
assert.match(popupHtml, /<script\s+type="module"\s+src="popup\.js"><\/script>/, "popup.html must load popup.js as a browser ESM module");

console.log("extension dist module resolution tests passed");
