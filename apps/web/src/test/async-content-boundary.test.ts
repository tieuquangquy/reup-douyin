import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const testDir = dirname(fileURLToPath(import.meta.url));
const webRoot = resolve(testDir, "..");
const boundarySource = readFileSync(resolve(webRoot, "components/shared/AsyncContentBoundary.tsx"), "utf8");
const globalCssSource = readFileSync(resolve(webRoot, "app/globals.css"), "utf8");

assert.match(boundarySource, /status === "loading"/, "Boundary must distinguish initial loading");
assert.match(boundarySource, /status === "error"/, "Boundary must expose a dedicated error branch");
assert.match(boundarySource, /status === "empty"/, "Boundary must avoid flashing success content for empty data");
assert.match(boundarySource, /aria-busy=\{refreshing \|\| undefined\}/, "Background refresh must keep stale content mounted");
assert.match(boundarySource, /variant: "gallery" \| "list" \| "detail" \| "form"/, "Shared skeletons must cover standard page shapes");
assert.match(boundarySource, /role="status"/, "Loading and refresh feedback must be announced accessibly");
assert.match(globalCssSource, /\.async-skeleton\.is-gallery/, "Gallery skeleton variant must have a shared layout");
assert.match(globalCssSource, /@media \(prefers-reduced-motion: reduce\)[\s\S]*\.async-skeleton__block/, "Skeleton shimmer must respect reduced motion");

console.log("async content boundary tests passed");
