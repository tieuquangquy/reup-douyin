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
assert.match(
  boundarySource,
  /AsyncSkeletonVariant = "gallery" \| "list" \| "detail" \| "form" \| "table" \| "dashboard"/,
  "Shared skeletons must cover Ops table and dashboard shapes"
);
assert.match(boundarySource, /role="status"/, "Loading and refresh feedback must be announced accessibly");
assert.match(boundarySource, /PageLoadError/, "Error branch must default to the shared PageLoadError card");
assert.match(boundarySource, /async-skeleton__status/, "Initial loading must show a compact visible status chip");
assert.match(boundarySource, /async-skeleton__spinner/, "Loading status chip must include a spinner icon");
assert.match(boundarySource, /async-skeleton__label/, "Loading status chip must show regular-weight label text");
assert.match(boundarySource, /is-table|variant === "table"/, "Table skeleton variant must be implemented");
assert.match(boundarySource, /is-dashboard|variant === "dashboard"/, "Dashboard skeleton variant must be implemented");
assert.doesNotMatch(boundarySource, /sr-only/, "Loading label must not rely on missing sr-only utility");
assert.match(globalCssSource, /\.async-skeleton\.is-gallery/, "Gallery skeleton variant must have a shared layout");
assert.match(globalCssSource, /\.async-skeleton\.is-table/, "Table skeleton variant must have a shared layout");
assert.match(globalCssSource, /\.async-skeleton\.is-dashboard/, "Dashboard skeleton variant must have a shared layout");
assert.match(globalCssSource, /\.async-skeleton__status/, "CSS must style the compact loading status chip");
assert.match(
  globalCssSource,
  /\.app-content\s*>\s*\.async-skeleton(?:,\s*\.app-content\s*>\s*\.async-content-state)?\s*\{[^}]*padding:\s*1rem var\(--app-content-inset-x\) 1\.35rem/,
  "Page-level AsyncSkeleton must use the same content inset as Ops pages so it does not stick to header/nav"
);
assert.match(
  globalCssSource,
  /\.app-content\s*>\s*\.async-content-state/,
  "Page-level async error/empty states must share the same content inset"
);
assert.match(globalCssSource, /@media \(prefers-reduced-motion: reduce\)[\s\S]*\.async-skeleton__block/, "Skeleton shimmer must respect reduced motion");
assert.match(globalCssSource, /@media \(prefers-reduced-motion: reduce\)[\s\S]*\.async-skeleton__spinner/, "Loading spinner must respect reduced motion");

console.log("async content boundary tests passed");
