import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const testDir = dirname(fileURLToPath(import.meta.url));
const layoutSource = readFileSync(resolve(testDir, "../app/layout.tsx"), "utf8");

// Browser extensions (e.g. Cốc Cốc `-cz-shortcut-listen`) mutate <html>/<body>
// before hydrate; Next requires suppressHydrationWarning on those tags.
assert.match(
  layoutSource,
  /<html\b[^>]*\bsuppressHydrationWarning\b/,
  "root <html> must suppressHydrationWarning for extension DOM injects"
);
assert.match(
  layoutSource,
  /<body\b[^>]*\bsuppressHydrationWarning\b/,
  "root <body> must suppressHydrationWarning for extension DOM injects"
);

console.log("root-layout-hydration tests passed");
