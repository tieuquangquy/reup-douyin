import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const popupHtml = readFileSync(new URL("../public/popup.html", import.meta.url), "utf8");
const popupCss = readFileSync(new URL("../public/popup.css", import.meta.url), "utf8");
const popupSource = readFileSync(new URL("./popup.ts", import.meta.url), "utf8");

const resultsPanelStart = popupHtml.indexOf('id="deckPanelResults"');
const advancedPanelStart = popupHtml.indexOf('id="deckPanelAdvanced"');
const mainHtml = popupHtml.slice(popupHtml.indexOf("<main"), popupHtml.indexOf("</main>") + "</main>".length);
const resultsPanelHtml = popupHtml.slice(resultsPanelStart, advancedPanelStart);
const advancedPanelHtml = popupHtml.slice(advancedPanelStart);

assert.notEqual(resultsPanelStart, -1, "Results deck panel must exist");
assert.notEqual(advancedPanelStart, -1, "Advanced deck panel must exist");

assert.match(popupHtml, /id="deckPanelResults"/, "deck must render Results panel");
assert.match(popupHtml, /id="deckPanelAdvanced"/, "deck must render Advanced panel");
assert.match(popupHtml, /id="deckPanelResults"[\s\S]*hidden/, "Results panel must start hidden");
assert.match(popupHtml, /id="deckPanelAdvanced"[\s\S]*hidden/, "Advanced panel must start hidden");

assert.match(mainHtml, /id="scannerControlPanelRoot"[^>]*class="[^"]*scanner-shell[^"]*scp-shell/, "main shell must use scanner shell class");
assert.match(mainHtml, /class="[^"]*scanner-hero[^"]*scp-topbar/, "main shell must render compact scanner hero");
assert.match(mainHtml, /class="[^"]*scanner-hero-top[^"]*scp-hero-top/, "main shell must render premium hero top row");
assert.match(mainHtml, /<header class="[^"]*scanner-hero[^"]*scp-topbar[^"]*">[\s\S]*<section class="[^"]*scanner-health-inline[^"]*scp-health-row[^"]*"[\s\S]*<\/header>/, "health row must render inline inside the hero");
assert.match(mainHtml, /class="[^"]*scanner-health-inline[^"]*scp-health-row/, "main shell must render compact health row");
assert.match(mainHtml, /class="[^"]*scanner-main-grid[^"]*scp-main-grid/, "main shell must render compact main grid");
assert.match(mainHtml, /class="[^"]*scanner-primary-card[^"]*scp-action-block/, "main shell must render compact primary action block");
assert.match(mainHtml, /class="[^"]*scanner-stats-grid[^"]*scp-counters-block/, "main shell must render compact counters block");
assert.match(mainHtml, /class="[^"]*scanner-settings-compact[^"]*scp-settings-bar/, "main shell must render compact settings section");
assert.match(mainHtml, /class="[^"]*scanner-alert[^"]*scp-alert/, "main shell must render inline alert banner");
assert.match(mainHtml, /class="[^"]*scanner-bottom-dock[^"]*scp-bottom-bar/, "main shell must render compact bottom actions");

assert.match(mainHtml, /id="scannerChipTab"/, "status row must contain profile chip");
assert.match(mainHtml, /id="scannerChipApi"/, "status row must contain API chip");
assert.match(mainHtml, /id="scannerChipCalibration"/, "status row must contain Calibration chip");
assert.match(mainHtml, /id="scannerChipSafety"/, "status row must contain Safety chip");

assert.match(mainHtml, /id="scannerPrimaryActionButton"/, "main screen must contain primary button");
assert.match(mainHtml, /id="scannerPrimaryActionTitle"/, "main screen must contain action title");
assert.match(mainHtml, /id="scannerPrimaryActionReason"/, "main screen must contain action helper copy");

assert.match(popupSource, /const wholeProfileHarvestModeSelect = document\.querySelector<HTMLSelectElement>\("#wholeProfileHarvestMode"\);/, "compact settings logic must keep mode select wiring");
assert.match(popupSource, /const wholeProfileHarvestBatchSelect = document\.querySelector<HTMLSelectElement>\("#wholeProfileHarvestBatch"\);/, "compact settings logic must keep batch select wiring");
assert.match(popupSource, /const wholeProfileHarvestSpeedSelect = document\.querySelector<HTMLSelectElement>\("#wholeProfileHarvestSpeed"\);/, "compact settings logic must keep speed select wiring");

assert.match(mainHtml, /id="scannerStatsGrid"/, "compact counters block must contain metric grid");
assert.match(mainHtml, /id="wholeProfileHarvestMode"/, "compact settings must contain Mode select");
assert.match(mainHtml, /id="wholeProfileHarvestBatch"/, "compact settings must contain Batch select");
assert.match(mainHtml, /id="wholeProfileHarvestSpeed"/, "compact settings must contain Speed select");

assert.match(mainHtml, /id="scannerOpenCaptureInboxButton"/, "bottom actions must contain Capture Inbox button");
assert.match(mainHtml, /id="scannerOpenAdvancedButton"/, "compact settings must contain Advanced button");
assert.match(mainHtml, /id="scannerResetButton"/, "bottom actions must contain Reset button");
assert.doesNotMatch(mainHtml, /id="scannerProfileMetrics"/, "legacy profile summary metric list must be removed");
assert.doesNotMatch(mainHtml, /id="scannerPlanMetrics"/, "legacy plan summary metric list must be removed");
assert.doesNotMatch(mainHtml, /scanner-header|scanner-chip-row|scanner-card|scanner-footer|scanner-health-strip|scanner-stats-strip|scanner-primary-panel|scanner-bottom-actions/, "legacy scanner card-stack classes must be removed from main");
assert.doesNotMatch(mainHtml, /Douyin Profile Scanner|Profile scan summary|Scan plan summary|Queue Preview|Debug Details|Technical Details|Payload Guard|Flush Batch|Test First|Test Last|Test Random/, "forbidden old main-screen text must be removed");

assert.doesNotMatch(popupHtml, /id="wholeProfileTabRun"/, "old top tab bar Run tab must be removed");
assert.doesNotMatch(popupHtml, /id="wholeProfileTabResults"/, "old top tab bar Results tab must be removed");
assert.doesNotMatch(popupHtml, /id="wholeProfileTabAdvanced"/, "old top tab bar Advanced tab must be removed");
assert.doesNotMatch(popupHtml, /id="wholeProfileTabPanelRun"/, "old Run tab panel must be removed");
assert.doesNotMatch(popupHtml, /class="[^"]*tabbar[^"]*"/, "old tabbar class must be removed from markup");

assert.match(resultsPanelHtml, /Results Dashboard<\/h2>/, "Results panel must expose a Results Dashboard heading");
assert.match(resultsPanelHtml, /id="wholeProfileBackendFlowSection"/, "Results panel must contain backend save flow");
assert.match(resultsPanelHtml, /Save to Capture Inbox/, "Results panel must contain Capture Inbox save wording");
assert.match(resultsPanelHtml, /Recent Save Results/, "Results panel must relabel backend results for save outcomes");
assert.match(resultsPanelHtml, /id="wholeProfileQueuePreviewPanel"/, "Results panel must contain queue preview");
assert.match(resultsPanelHtml, /id="wholeProfileExtractionResultsSection"/, "Results panel must contain extraction result rows");
assert.match(resultsPanelHtml, /id="wholeProfileBackendResultsSection"/, "Results panel must contain backend result rows");
assert.match(resultsPanelHtml, /id="wholeProfileCaptureInboxCta"/, "Results panel must contain Capture Inbox CTA");

assert.match(advancedPanelHtml, /Advanced Details/, "Advanced panel must expose advanced details wording");
assert.match(advancedPanelHtml, /id="apiBaseUrl"/, "Advanced panel must contain API base URL");
assert.match(advancedPanelHtml, /id="webAppOrigin"/, "Advanced panel must contain web app origin");
assert.match(advancedPanelHtml, /Reconnect Douyin Tab/, "Advanced panel must contain reconnect control");
assert.match(advancedPanelHtml, /data-feature="calibration-details"/, "Advanced panel must contain calibration section");
assert.match(advancedPanelHtml, /Copy Debug JSON/, "Advanced panel must contain copy debug control");
assert.match(advancedPanelHtml, /Clear Legacy State/, "Advanced panel must contain legacy cleanup control");
assert.match(advancedPanelHtml, /id="wholeProfileBackendDetails"/, "Advanced panel must contain payload/save details");

assert.match(popupSource, /active_tab:\s*"run"\s*\|\s*"results"\s*\|\s*"advanced"/, "UI prefs must still support legacy run/results/advanced tab type");
assert.match(popupSource, /active_panel:\s*"main"\s*\|\s*"results"\s*\|\s*"advanced"/, "UI prefs must support main/results/advanced panel state");
assert.match(popupSource, /function applyDeckActivePanel\(panel: WholeProfileHarvestUiPrefs\["active_panel"\]\)/, "popup must switch overlay panels in local UI state");
assert.match(popupSource, /scannerOpenCaptureInboxButton\?\.addEventListener\("click", \(\) => void openCaptureInboxWebAppFromPopup\(\)\)/, "Results footer button must open the web Capture Inbox");
assert.match(popupSource, /scannerOpenAdvancedButton\?\.addEventListener\("click", \(\) => void setDeckActivePanel\("advanced"\)\)/, "Advanced footer button must switch to advanced panel");
assert.match(popupSource, /deckPanelResultsCloseButton\?\.addEventListener\("click", \(\) => void setDeckActivePanel\("main"\)\)/, "Results close button must return to main");
assert.match(popupSource, /deckPanelAdvancedCloseButton\?\.addEventListener\("click", \(\) => void setDeckActivePanel\("main"\)\)/, "Advanced close button must return to main");
assert.match(popupSource, /async function setDeckActivePanel\(panel: WholeProfileHarvestUiPrefs\["active_panel"\]\): Promise<void> \{[\s\S]*applyDeckActivePanel\(panel\);[\s\S]*saveWholeProfileHarvestUiPrefs\(\{ \.\.\.prefs, active_panel: panel \}\);[\s\S]*\}/, "switching panels must only update local UI prefs");
assert.match(popupSource, /saveWholeProfileHarvestUiPrefs\(\{ \.\.\.prefs, active_panel: panel \}\)/, "panel choice should persist in local UI prefs");

assert.match(popupCss, /\.scanner-shell,\s*\n\.scp-shell\s*\{/, "scanner shell CSS rule must exist");
assert.match(popupCss, /\.scanner-shell,\s*\n\.scp-shell\s*\{[\s\S]*background:\s*radial-gradient/, "scanner shell must use premium light styling");
assert.match(popupCss, /\.scanner-health-inline,\s*\n\.scp-health-row\s*\{/, "scanner-health-inline CSS rule must exist");
assert.match(popupCss, /\.scanner-health-inline,\s*\n\.scp-health-row\s*\{[\s\S]*display:\s*flex/, "health row must use inline flex chips");
assert.match(popupCss, /\.scanner-stats-grid,\s*\n\.scp-counters-block\s*\{[\s\S]*grid-template-columns:\s*repeat\(2, minmax\(0, 1fr\)\)/, "counters must render as compact 2x2 grid");
assert.match(popupCss, /\.scanner-primary-card,\s*\n\.scp-action-block\s*\{/, "scanner primary card CSS rule must exist");
assert.match(popupCss, /\.scanner-alert,\s*\n\.scp-alert\s*\{/, "scanner-alert CSS rule must exist");
assert.match(popupCss, /\.scanner-alert\[hidden\],\s*\n\.scp-alert\[hidden\]\s*\{[\s\S]*display:\s*none/, "hidden alert must not render empty progress-like bar");
assert.match(popupCss, /\.scanner-settings-compact,\s*\n\.scp-settings-bar\s*\{/, "scanner settings CSS rule must exist");
assert.match(popupCss, /\.scanner-settings-compact select,\s*\n\.scp-settings-bar select\s*\{[\s\S]*height:\s*28px/, "settings must render compact selects");
assert.match(popupCss, /\.scanner-bottom-dock,\s*\n\.scp-bottom-bar\s*\{/, "scanner bottom dock CSS rule must exist");
assert.match(popupCss, /\.scanner-bottom-dock,\s*\n\.scp-bottom-bar\s*\{[\s\S]*grid-template-columns:\s*1fr 1fr minmax\(58px, 0\.68fr\) auto/, "bottom actions must render in one compact row");
assert.match(popupCss, /\.deck-panel\s*\{/, "deck-panel CSS rule must exist");
assert.match(popupCss, /\.deck-panel__header\s*\{/, "deck-panel__header CSS rule must exist");
assert.match(popupCss, /\.deck-panel__close\s*\{/, "deck-panel__close CSS rule must exist");
assert.doesNotMatch(popupCss, /\.deck-shell\s*\{/, "old deck-shell CSS rule must be removed");
assert.doesNotMatch(popupCss, /\.scanner-card\s*\{/, "legacy scanner-card CSS rule must be removed");
assert.doesNotMatch(popupCss, /\.scanner-footer\s*\{/, "legacy scanner-footer CSS rule must be removed");

assert.match(popupSource, /function renderDouyinScannerMainScreen\(/, "popup.ts must contain renderDouyinScannerMainScreen function");
assert.match(popupSource, /function ScannerControlPanel\(state: WholeProfileHarvestState\): ScannerControlPanelViewModel/, "popup.ts must contain ScannerControlPanel function");
assert.match(popupSource, /getScannerControlPanelViewModel\(state\)/, "popup.ts must call getScannerControlPanelViewModel");

assert.doesNotMatch(popupCss, /word-break:\s*break-all/, "popup must avoid one-character wrapping regressions");

console.log("wholeProfileHarvest Action Deck tabbed layout tests passed");
