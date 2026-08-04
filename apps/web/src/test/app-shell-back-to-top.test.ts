import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const testDir = dirname(fileURLToPath(import.meta.url));
const webRoot = resolve(testDir, "..");
const appShellSource = readFileSync(resolve(webRoot, "components/app-shell/AppShell.tsx"), "utf8");
const backToTopSource = readFileSync(resolve(webRoot, "components/app-shell/BackToTopButton.tsx"), "utf8");
const sidebarSource = readFileSync(resolve(webRoot, "components/app-shell/Sidebar.tsx"), "utf8");
const navSectionSource = readFileSync(resolve(webRoot, "components/app-shell/NavSection.tsx"), "utf8");
const navConfigSource = readFileSync(resolve(webRoot, "lib/navigationConfig.ts"), "utf8");
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
assert.match(sidebarSource, /app-sidebar is-\$\{surface\}/, "Sidebar must expose its Operator or Ops visual surface");
assert.match(sidebarSource, /app-sidebar__footer[\s\S]*common\.localWorkspace/, "Desktop navigation must finish with truthful local workspace context");
assert.match(navConfigSource, /export type NavIconName/, "Navigation icons must use a typed shared vocabulary");
assert.match(navSectionSource, /NavItemIcon[\s\S]*item\.icon/, "Every navigation row must render its configured semantic icon");
assert.match(navSectionSource, /app-nav-item__indicator/, "Navigation rows must use a compact directional active cue");
assert.match(navSectionSource, /aria-hidden="true" className=\{`app-nav-item__icon/, "Decorative navigation icons must stay hidden from assistive technology");
assert.match(globalCssSource, /App shell V16[\s\S]*\.app-sidebar\.is-operator/, "Operator Studio must use the light workflow navigation surface");
assert.match(globalCssSource, /\.app-sidebar\.is-ops[\s\S]*linear-gradient\(180deg, #122d26/, "Ops Console must use the dark control-room navigation surface");
assert.match(globalCssSource, /\.app-nav-item\s*\{[\s\S]*grid-template-columns:\s*34px minmax\(0, 1fr\) auto/, "Navigation rows must align icon, copy and status consistently");
assert.match(globalCssSource, /\.app-sidebar nav\s*\{[\s\S]*overflow-y:\s*auto/, "Desktop navigation must scroll independently so its footer cannot overlap the final item");
assert.match(globalCssSource, /@media \(max-width:\s*980px\)[\s\S]*\.app-sidebar nav[\s\S]*overflow-x:\s*auto/, "Responsive navigation must become a horizontally scannable ribbon");
assert.match(globalCssSource, /@media \(max-width:\s*980px\)[\s\S]*\.app-sidebar nav[\s\S]*overflow-y:\s*hidden/, "Responsive ribbon must suppress the desktop vertical scrollbar");

console.log("AppShell Back to top tests passed");
