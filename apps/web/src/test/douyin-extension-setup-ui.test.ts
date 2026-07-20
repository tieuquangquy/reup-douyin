/**
 * Douyin Extension Setup — Ops-triage install + verify (no intake two-column soup).
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const testDir = dirname(fileURLToPath(import.meta.url));
const webSrc = resolve(testDir, "..");

const page = readFileSync(resolve(webSrc, "components/douyin-extension-setup/DouyinExtensionSetupPage.tsx"), "utf8");
const css = readFileSync(resolve(webSrc, "app/globals.css"), "utf8");
const en = readFileSync(resolve(webSrc, "lib/i18n/en.json"), "utf8");
const vi = readFileSync(resolve(webSrc, "lib/i18n/vi.json"), "utf8");
const pkg = readFileSync(resolve(webSrc, "../package.json"), "utf8");

assert.match(page, /OperatorStudioShell/, "Setup must keep OperatorStudioShell");
assert.match(page, /TopbarRefreshButton/, "Setup must put Check/Refresh in the Topbar");
assert.match(page, /ext-setup-page/, "Setup must use scoped ext-setup-page shell");
assert.match(page, /ext-setup-freshness/, "Setup must render freshness strip");
assert.match(page, /ext-setup-kpis/, "Setup must render KPI band");
assert.match(page, /ext-setup-kpi/, "Setup must use scoped KPI cards");
assert.match(page, /resolveDouyinExtensionDownloadState/, "Setup must keep download state authority");
assert.match(page, /EXTENSION_BUILD_COMMAND|EXTENSION_DIST_PATH/, "Setup must surface build/dist install facts");
assert.match(page, /ext-setup-toolbar|ext-setup-actions/, "Setup must render triage toolbar");
assert.match(page, /ext-setup-steps|ext-setup-install/, "Setup must render install steps sheet");
assert.match(page, /ext-setup-diagnostics/, "Setup must render compact diagnostics");
assert.match(page, /ext-setup-footnote|manualInstall/, "Setup must footnote manual-install honesty");
assert.match(page, /useT\(/, "Setup must use i18n");
assert.match(page, /chrome:\/\/extensions|chrome_extensions_url/, "Setup must keep Chrome extensions shortcut");
assert.match(page, /edge:\/\/extensions|edge_extensions_url/, "Setup must keep Edge extensions shortcut");
assert.match(page, /ext-setup-shortcut__icon|ShortcutOpenIcon|ShortcutCopyIcon/, "Shortcut Open/Copy must render icon glyphs");
assert.match(page, /aria-label=\{openLabel\}|aria-label=\{copyLabel\}/, "Shortcut icon actions must keep accessible labels");
assert.doesNotMatch(page, /ext-setup-shortcut[\s\S]*>\{openLabel\}</, "Shortcut Open must not show text label inside the control");
assert.doesNotMatch(page, /intake-layout/, "Setup must leave legacy intake-layout");
assert.doesNotMatch(page, /intake-side/, "Setup must not keep intake side status column");
assert.doesNotMatch(page, /PageShell/, "Setup must not nest PageShell under OperatorStudioShell");
assert.doesNotMatch(page, /operator-panel/, "Setup must not use legacy operator-panel soup");

assert.match(css, /\.ext-setup-page/, "CSS must define Extension Setup page shell");
assert.match(css, /\.ext-setup-kpis/, "CSS must define Extension Setup KPI grid");
assert.match(css, /\.ext-setup-chip\s*\{[^}]*font-weight:\s*400/, "Setup chips must not use bold weight");
assert.match(css, /\.ext-setup-footnote/, "CSS must define Setup footnote");
assert.match(css, /\.ext-setup-diagnostics/, "CSS must define diagnostics grid");

assert.match(en, /"extensionSetup"/, "en.json must define extensionSetup namespace");
assert.match(en, /"installSteps"|"diagnostics"|"connected"/, "en.json must define setup triage labels");
assert.match(vi, /"extensionSetup"/, "vi.json must define extensionSetup namespace");
assert.match(vi, /"installSteps"|"diagnostics"|"connected"/, "vi.json must define setup triage labels");
assert.match(pkg, /douyin-extension-setup-ui\.test\.ts/, "package.json must run extension setup UI test");

console.log("douyin-extension-setup-ui tests passed");
