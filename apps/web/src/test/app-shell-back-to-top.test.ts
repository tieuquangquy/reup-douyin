import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const testDir = dirname(fileURLToPath(import.meta.url));
const webRoot = resolve(testDir, "..");
const appShellSource = readFileSync(resolve(webRoot, "components/app-shell/AppShell.tsx"), "utf8");
const backToTopSource = readFileSync(resolve(webRoot, "components/app-shell/BackToTopButton.tsx"), "utf8");
const sidebarSource = readFileSync(resolve(webRoot, "components/app-shell/Sidebar.tsx"), "utf8");
const globalCssSource = readFileSync(resolve(webRoot, "app/globals.css"), "utf8");

assert.match(appShellSource, /<BackToTopButton \/>/, "Authenticated AppShell must mount one shared Back to top control");
assert.match(backToTopSource, /BACK_TO_TOP_THRESHOLD = 600/, "Back to top must wait until the page is meaningfully long");
assert.match(backToTopSource, /window\.addEventListener\("scroll", updateVisibility, \{ passive: true \}\)/, "Back to top must use a passive document scroll listener");
assert.match(backToTopSource, /aria-label="Back to top"/, "Back to top must expose an accessible label");
assert.match(backToTopSource, /window\.matchMedia\("\(prefers-reduced-motion: reduce\)"\)/, "Back to top must respect reduced motion");
assert.match(backToTopSource, /window\.scrollTo\(\{ top: 0, behavior \}\)/, "Back to top must return the document viewport to the top");
assert.match(globalCssSource, /\.app-back-to-top\s*\{[^}]*position: fixed;[^}]*env\(safe-area-inset-bottom/, "Back to top must be fixed and mobile safe-area aware");
assert.match(globalCssSource, /\.app-back-to-top:focus-visible/, "Back to top must provide a visible keyboard focus ring");
assert.match(sidebarSource, /querySelector<HTMLElement>\('\[aria-current="page"\]'\)/, "Sidebar must find the active route item");
assert.match(sidebarSource, /requestAnimationFrame/, "Sidebar must wait for the active route layout before scrolling");
assert.match(
  sidebarSource,
  /scrollIntoView\(\{ behavior: "auto", block: "center", inline: "nearest" \}\)/,
  "Sidebar must reveal the active route without moving keyboard focus"
);

console.log("AppShell Back to top tests passed");
