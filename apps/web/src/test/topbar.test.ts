import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const testDir = dirname(fileURLToPath(import.meta.url));
const webRoot = resolve(testDir, "..");

const topbarSource = readFileSync(resolve(webRoot, "components/app-shell/Topbar.tsx"), "utf8");
const refreshSource = readFileSync(resolve(webRoot, "components/app-shell/TopbarRefreshButton.tsx"), "utf8");
const labeledButtonSource = readFileSync(resolve(webRoot, "components/app-shell/TopbarLabeledButton.tsx"), "utf8");
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
assert.doesNotMatch(topbarSource, /app-topbar-surface-mark|TopbarSurfaceIcon/, "Topbar must not reserve a decorative icon beside the page title");
assert.match(topbarSource, /app-topbar-title-row[\s\S]*StatusBadge/, "Page title and workspace status must share one clear hierarchy");
assert.match(topbarSource, /app-topbar-menu-separator/, "Account menu must separate action groups");
assert.match(topbarSource, /app-topbar-menu-logout/, "Logout must use a dedicated quiet style");
assert.match(topbarSource, /WorkspaceSwitchIcon|app-topbar-menu-icon/, "Workspace switch must include a leading icon");
assert.match(topbarSource, /app-topbar-account-avatar is-panel/, "Account menu must open with a strong identity block");
assert.match(topbarSource, /app-topbar-account-watermark/, "Account identity hero must include a decorative monogram watermark");
assert.match(topbarSource, /app-topbar-account-commands/, "Workspace and locale controls must share one command surface");
assert.match(topbarSource, /accountDisplayName[\s\S]*app-topbar-account-email/, "Identity hero must prefer display name and preserve email as a secondary identifier");
assert.match(topbarSource, /primaryAccountRole[\s\S]*app-topbar-account-role/, "Identity hero must derive a truthful role badge from auth roles");
assert.match(topbarSource, /workspaceSlug[\s\S]*app-topbar-account-workspace/, "Identity hero must expose the active workspace slug");
assert.match(topbarSource, /workspaceCount > 1/, "Workspace count must stay conditional when only one membership exists");
assert.match(topbarSource, /MenuArrowIcon/, "Workspace switch must include a trailing direction cue");
assert.doesNotMatch(topbarSource, /PreferencesIcon/, "Preferences must not duplicate the globe icon already embedded in the language control");
assert.match(topbarSource, /LogoutIcon[\s\S]*topbar\.logout/, "Logout action must include a semantic icon");
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

assert.match(refreshSource, /TopbarLabeledButton/, "Refresh control must use shared icon+text topbar button");
assert.match(labeledButtonSource, /app-topbar-btn__label/, "Labeled topbar button must render visible text label");
assert.match(topbarSource, /app-topbar-account-trigger-label/, "Account trigger must show icon + text label");
assert.match(refreshSource, /RefreshIcon|app-topbar-refresh-icon/, "Refresh control must use an SVG icon");

assert.doesNotMatch(languageSource, /🌐|GlobeIcon|language-switcher__select/, "Compact language switcher must not keep the old globe or select UI");
assert.match(languageSource, /COMPACT_LOCALES[\s\S]*"vi", "en"/, "Compact language switcher must expose VI and EN in that order");
assert.match(languageSource, /aria-pressed=\{locale === value\}/, "Compact language switcher must expose its selected locale accessibly");
assert.match(languageSource, /value\.toUpperCase\(\)/, "Compact language labels must render as VI and EN");

assert.doesNotMatch(opsHomeShell, /href=["']\/ops\/health["']/, "Ops home shell must not duplicate sidebar Health link");
assert.doesNotMatch(opsHomeShell, /href=["']\/ops\/jobs["']/, "Ops home shell must not duplicate sidebar Jobs link");

assert.match(globalCssSource, /\.app-topbar-btn\.is-labeled/, "Global CSS must style labeled icon+text topbar buttons");
assert.match(globalCssSource, /\.app-topbar-btn__icon-wrap/, "Global CSS must style topbar icon wraps");
assert.match(globalCssSource, /\.app-topbar-account-surface/, "Global CSS must style account surface subtitle");
assert.match(globalCssSource, /\.app-topbar-menu-logout/, "Global CSS must style logout quietly");
assert.match(globalCssSource, /App shell V14[\s\S]*\.app-topbar-context/, "Global CSS must style the context header hierarchy");
assert.match(globalCssSource, /\.app-topbar-command-bar\s*\{[\s\S]*border-radius:\s*13px/, "Topbar actions must live in a compact command dock");
assert.match(globalCssSource, /\.app-topbar-menu-panel\.app-topbar-account-panel[\s\S]*border-radius:\s*15px/, "Account dropdown must use elevated card chrome");
assert.match(globalCssSource, /\.app-topbar-account-header\s*\{[\s\S]*grid-template-columns:\s*40px/, "Account dropdown must use an avatar-led identity header");
assert.match(globalCssSource, /\.app-topbar-account-panel \.app-topbar-menu-logout[\s\S]*grid-template-columns:/, "Logout row must align its icon and label");
assert.match(globalCssSource, /App shell V15[\s\S]*\.app-topbar-account-watermark/, "Account dropdown must use the Identity Passport concept");
assert.match(globalCssSource, /\.app-topbar-account-panel \.app-topbar-account-header[\s\S]*linear-gradient\(135deg, #173f35/, "Identity Passport must use a distinctive dark identity hero");
assert.match(globalCssSource, /\.app-topbar-account-commands \.app-topbar-account-language[\s\S]*grid-template-columns:\s*auto auto/, "Locale control must use the compact inline command-strip layout");
assert.match(globalCssSource, /\.language-switcher\.is-segmented[\s\S]*grid-template-columns:\s*repeat\(2, 40px\)/, "VI and EN must render as a two-segment switch");
assert.match(globalCssSource, /\.app-topbar-account-workspace[\s\S]*grid-column:\s*1 \/ -1/, "Workspace context must form a full-width passport strip");
assert.match(globalCssSource, /\.app-topbar-account-role\.is-owner[\s\S]*\.app-topbar-account-role\.is-admin/, "Privileged roles must have distinct truthful badge treatments");
assert.match(
  globalCssSource,
  /\.app-topbar-btn,[\s\S]*?min-height:\s*32px/,
  "Topbar controls must use a compact 32px control height"
);

assert.doesNotMatch(reupQueueSource, /reup-queue-header-actions[\s\S]*Open Review Board/, "Reup Queue topbar must not duplicate sidebar navigation links");
assert.match(reupQueueSource, /TopbarRefreshButton/, "Reup Queue must use the shared icon refresh control");

console.log("topbar UI tests passed");
