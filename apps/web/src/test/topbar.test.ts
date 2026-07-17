import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const testDir = dirname(fileURLToPath(import.meta.url));
const webRoot = resolve(testDir, "..");

const topbarSource = readFileSync(resolve(webRoot, "components/app-shell/Topbar.tsx"), "utf8");
const refreshSource = readFileSync(resolve(webRoot, "components/app-shell/TopbarRefreshButton.tsx"), "utf8");
const globalCssSource = readFileSync(resolve(webRoot, "app/globals.css"), "utf8");
const navConfigSource = readFileSync(resolve(webRoot, "lib/navigationConfig.ts"), "utf8");
const languageSource = readFileSync(resolve(webRoot, "components/app-shell/LanguageSwitcher.tsx"), "utf8");
const opsHomeShell = readFileSync(resolve(webRoot, "app/ops/page.tsx"), "utf8");
const reupQueueSource = readFileSync(resolve(webRoot, "components/reup-queue/ReupQueuePage.tsx"), "utf8");

assert.match(topbarSource, /app-topbar-command-bar/, "Topbar must use a compact command bar layout");
assert.doesNotMatch(topbarSource, /app-topbar-nav-menu/, "Topbar must not duplicate sidebar navigation via Navigate");
assert.doesNotMatch(topbarSource, /topbarQuickActions/, "Topbar must not consume topbar quick-nav actions");
assert.doesNotMatch(topbarSource, /app-topbar-menu-current/, "Account menu must not show a current-workspace row");
assert.doesNotMatch(navConfigSource, /export const topbarQuickActions/, "topbarQuickActions must be removed once Navigate is gone");
assert.match(topbarSource, /app-topbar-account-avatar/, "Account trigger must use a compact avatar control");
assert.match(topbarSource, /app-topbar-account-surface/, "Account menu must show current surface as muted text");
assert.match(topbarSource, /app-topbar-menu-separator/, "Account menu must separate action groups");
assert.match(topbarSource, /app-topbar-menu-logout/, "Logout must use a dedicated quiet style");
assert.match(topbarSource, /WorkspaceSwitchIcon|app-topbar-menu-icon/, "Workspace switch must include a leading icon");
assert.match(topbarSource, /showWorkspaceSwitch/, "Workspace switch visibility must be conditional");
assert.match(
  topbarSource,
  /showWorkspaceSwitch \? \([\s\S]*?href=\{switchHref\}/,
  "Workspace switch must be a single Go-to link inside Account"
);
assert.match(topbarSource, /removeAttribute\([\"']open[\"']\)/, "Account menu must close on outside click");
assert.doesNotMatch(topbarSource, /app-topbar-surface-switch/, "Topbar must not use a primary surface-switch CTA");
assert.doesNotMatch(topbarSource, /nav\.openOpsConsole|nav\.openOperatorStudio/, "Workspace copy must not use Open … CTA labels");

assert.match(topbarSource, /loginPathForSurface/, "Workspace switch must route through auth login portals");
assert.match(topbarSource, /loginPathForSurface\("ops"\)/, "Studio→Ops switch must use Ops login path");
assert.match(topbarSource, /loginPathForSurface\("operator"\)/, "Ops→Studio switch must use Operator login path");
assert.match(topbarSource, /OPS_ADMIN_ROLES|owner.*admin|canOpenOps/, "Ops workspace option must be role-gated");
assert.match(topbarSource, /topbar\.switchToOpsConsole|topbar\.switchToOperatorStudio/, "Workspace menu must use Go to … labels");

assert.match(refreshSource, /app-topbar-btn is-icon/, "Refresh control must be an icon-only topbar button");
assert.match(refreshSource, /aria-label/, "Icon refresh must expose an accessible label");
assert.match(refreshSource, /RefreshIcon|app-topbar-refresh-icon/, "Refresh control must use an SVG icon");

assert.doesNotMatch(languageSource, /🌐/, "Language switcher must not use emoji");
assert.match(languageSource, /language-switcher__icon|svg/, "Language switcher must use an SVG globe icon");

assert.doesNotMatch(opsHomeShell, /href=["']\/ops\/health["']/, "Ops home shell must not duplicate sidebar Health link");
assert.doesNotMatch(opsHomeShell, /href=["']\/ops\/jobs["']/, "Ops home shell must not duplicate sidebar Jobs link");

assert.match(globalCssSource, /\.app-topbar-btn\.is-icon/, "Global CSS must style icon-only topbar buttons");
assert.match(globalCssSource, /\.app-topbar-account-surface/, "Global CSS must style account surface subtitle");
assert.match(globalCssSource, /\.app-topbar-menu-logout/, "Global CSS must style logout quietly");
assert.match(
  globalCssSource,
  /\.app-topbar-btn,[\s\S]*?min-height:\s*32px/,
  "Topbar controls must use a compact 32px control height"
);

assert.doesNotMatch(reupQueueSource, /reup-queue-header-actions[\s\S]*Open Review Board/, "Reup Queue topbar must not duplicate sidebar navigation links");
assert.match(reupQueueSource, /TopbarRefreshButton/, "Reup Queue must use the shared icon refresh control");

console.log("topbar UI tests passed");
