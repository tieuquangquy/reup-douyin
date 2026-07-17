import { existsSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import assert from "node:assert/strict";

const root = dirname(fileURLToPath(import.meta.url));
const entrypoints = ["popup.js", "popupActions.js", "contentScript.js", "background.js"];
const relativeImportPattern = /(?:import|export)\s+(?:[^"']*?\s+from\s+)?["'](\.\.?\/[^"']+)["']/g;

for (const entrypoint of entrypoints) {
  const entrypointPath = join(root, entrypoint);
  assert.equal(existsSync(entrypointPath), true, `${entrypoint} must be emitted into dist`);
  const content = readFileSync(entrypointPath, "utf-8");
  const imports = [...content.matchAll(relativeImportPattern)].map((match) => match[1]).filter((specifier): specifier is string => Boolean(specifier));

  for (const specifier of imports) {
    assert.equal(specifier.endsWith(".js"), true, `${entrypoint} imports ${specifier}, but browser ESM requires a .js extension`);
    const resolved = join(root, specifier);
    assert.equal(existsSync(resolved), true, `${entrypoint} imports missing emitted module ${specifier}`);
  }
}

const popupHtml = readFileSync(join(root, "popup.html"), "utf-8");
assert.match(popupHtml, /<script\s+type="module"\s+src="popup\.js"><\/script>/, "popup.html must load popup.js as a browser ESM module");

console.log("extension dist module resolution tests passed");
