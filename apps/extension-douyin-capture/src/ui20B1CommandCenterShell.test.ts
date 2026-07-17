import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const manifestJson = readFileSync(new URL("../public/manifest.json", import.meta.url), "utf8");
const popupHtml = readFileSync(new URL("../public/popup.html", import.meta.url), "utf8");
const popupCss = readFileSync(new URL("../public/popup.css", import.meta.url), "utf8");
const popupSource = readFileSync(new URL("./popup.ts", import.meta.url), "utf8");

const mainHtml = popupHtml.slice(popupHtml.indexOf("<main"), popupHtml.indexOf("</main>") + "</main>".length);

assert.match(manifestJson, /"default_popup"\s*:\s*"popup\.html"/, "manifest must point the extension action popup at popup.html");
assert.match(popupHtml, /21D-0 POPUP ROOT CONFIRMED/, "popup root must carry the Phase 21D-0 root confirmation comment");
assert.match(popupSource, /\/\/ 21D-0 POPUP ROOT CONFIRMED/, "popup.ts must carry the Phase 21D-0 root confirmation comment");
assert.match(popupHtml, /<title>Douyin Profile Scanner<\/title>/, "popup title must remain stable for the browser extension");
assert.match(mainHtml, /id="scannerControlPanelRoot"[^>]*class="[^"]*scanner-shell[^"]*scp-shell/, "main screen must render the compact ScannerControlPanel root");
assert.match(mainHtml, /class="[^"]*scanner-hero[^"]*scp-topbar/, "main screen must render the compact scanner hero");
assert.match(mainHtml, /class="[^"]*scanner-health-inline[^"]*scp-health-row/, "main screen must render inline health chips");
assert.match(mainHtml, /class="[^"]*scanner-main-grid[^"]*scp-main-grid/, "main screen must render the compact main grid");
assert.match(mainHtml, /class="[^"]*scanner-primary-card[^"]*scp-action-block/, "main screen must render the compact primary action card");
assert.match(mainHtml, /class="[^"]*scanner-stats-grid[^"]*scp-counters-block/, "main screen must render the compact counters grid");
assert.match(mainHtml, /class="[^"]*scanner-settings-compact[^"]*scp-settings-bar/, "main screen must render the compact settings bar");
assert.match(mainHtml, /class="[^"]*scanner-bottom-dock[^"]*scp-bottom-bar/, "main screen must render the compact bottom dock");
assert.match(popupHtml, /id="deckPanelResults"[^>]*\bdeck-panel\b/, "Results panel must keep deck-panel overlay class");
assert.match(popupHtml, /id="deckPanelAdvanced"[^>]*\bdeck-panel\b/, "Advanced panel must keep deck-panel overlay class");

assert.match(mainHtml, /id="scannerPrimaryActionButton"/, "main scanner UI must render the primary action button");
assert.match(mainHtml, /id="scannerStatsGrid"/, "main scanner UI must render compact counters grid");
assert.match(mainHtml, /id="scannerOpenCaptureInboxButton"/, "main scanner UI must render Capture Inbox action");
assert.match(mainHtml, /id="scannerOpenAdvancedButton"/, "main scanner UI must render Advanced action");
assert.match(mainHtml, /id="scannerPauseResumeButton"/, "main scanner UI must render Pause/Resume action");
assert.match(mainHtml, /id="scannerResetButton"/, "main scanner UI must render Reset action");

assert.match(popupCss, /\.scanner-shell,\s*\n\.scp-shell\s*\{/, "scanner shell CSS rule must exist");
assert.match(popupCss, /\.scanner-hero,\s*\n\.scp-topbar\s*\{/, "scanner hero CSS rule must exist");
assert.match(popupCss, /\.scanner-health-inline,\s*\n\.scp-health-row\s*\{/, "scanner health CSS rule must exist");
assert.match(popupCss, /\.scanner-main-grid,\s*\n\.scp-main-grid\s*\{/, "scanner main grid CSS rule must exist");
assert.match(popupCss, /\.scanner-primary-card,\s*\n\.scp-action-block\s*\{/, "scanner primary card CSS rule must exist");
assert.match(popupCss, /\.scanner-stats-grid,\s*\n\.scp-counters-block\s*\{/, "scanner counters CSS rule must exist");
assert.match(popupCss, /\.scanner-settings-compact,\s*\n\.scp-settings-bar\s*\{/, "scanner settings CSS rule must exist");
assert.match(popupCss, /\.scanner-bottom-dock,\s*\n\.scp-bottom-bar\s*\{/, "scanner bottom dock CSS rule must exist");
assert.match(popupCss, /\.deck-panel\s*\{/, "deck-panel CSS rule must exist for overlays");
assert.doesNotMatch(popupCss, /\.deck-shell\s*\{/, "old deck-shell CSS rule must be removed");
assert.doesNotMatch(popupCss, /\.scanner-card\s*\{/, "old scanner-card CSS rule must be removed");
assert.doesNotMatch(mainHtml, /scanner-card|deck-card|scanner-health-strip|scanner-stats-strip|scanner-primary-panel|scanner-bottom-actions/, "old main card-stack scanner classes must be removed from main markup");
assert.doesNotMatch(mainHtml, /Douyin Profile Scanner|Profile scan summary|Scan plan summary|Queue Preview|Debug Details|Technical Details|Payload Guard|Flush Batch|Test First|Test Last|Test Random/, "forbidden old main-screen text must be removed from main markup");

assert.match(popupSource, /function ScannerControlPanel\(state: WholeProfileHarvestState\): ScannerControlPanelViewModel \{/, "popup must expose ScannerControlPanel");
assert.match(popupSource, /getScannerControlPanelViewModel\(state\)/, "popup must render scanner main state from ScannerControlPanel view model");
assert.match(popupSource, /function renderDouyinScannerMainScreen\(state: WholeProfileHarvestState\): void \{/, "popup must expose scanner main screen render function");
assert.match(popupSource, /function applyDeckActivePanel\(panel: WholeProfileHarvestUiPrefs\["active_panel"\]\): void \{/, "popup must still expose panel switching function");
assert.match(popupSource, /saveWholeProfileHarvestUiPrefs\(\{ \.\.\.prefs, active_panel: panel \}\)/, "panel switching must persist to local UI prefs");

console.log("UI-20B-1 Command Center shell tests passed");
