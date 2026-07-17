import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const popupHtml = readFileSync(new URL("../public/popup.html", import.meta.url), "utf8");
const popupCss = readFileSync(new URL("../public/popup.css", import.meta.url), "utf8");
const popupSource = readFileSync(new URL("./popup.ts", import.meta.url), "utf8");
const viewModelSource = readFileSync(new URL("./wholeProfileHarvest/viewModel.ts", import.meta.url), "utf8");

const mainHtml = popupHtml.slice(popupHtml.indexOf("<main"), popupHtml.indexOf("</main>") + "</main>".length);
const advancedPanelHtml = popupHtml.slice(popupHtml.indexOf('id="deckPanelAdvanced"'));
const resultsPanelHtml = popupHtml.slice(popupHtml.indexOf('id="deckPanelResults"'), popupHtml.indexOf('id="deckPanelAdvanced"'));

// ── 1. No legacy top tab bar ─────────────────────────────────────────────────
assert.doesNotMatch(popupHtml, /id="wholeProfileTabRun"/, "old Run tab button must be removed");
assert.doesNotMatch(popupHtml, /id="wholeProfileTabResults"/, "old Results tab button must be removed");
assert.doesNotMatch(popupHtml, /id="wholeProfileTabAdvanced"/, "old Advanced tab button must be removed");
assert.doesNotMatch(popupHtml, /id="wholeProfileTabPanelRun"/, "old Run tab panel must be removed");
assert.doesNotMatch(popupHtml, /id="wholeProfileTabPanelResults"/, "old Results tab panel must be removed");
assert.doesNotMatch(popupHtml, /id="wholeProfileTabPanelAdvanced"/, "old Advanced tab panel must be removed");
assert.doesNotMatch(popupHtml, /class="[^"]*tabbar[^"]*"/, "old tabbar class must be removed");
assert.doesNotMatch(popupHtml, /class="[^"]*tab-panel[^"]*"/, "old tab-panel class must be removed from markup");
assert.doesNotMatch(popupCss, /\.tabbar\s*\{/, "old tabbar CSS rule must be removed");
assert.doesNotMatch(popupCss, /\.tab\.active\s*\{/, "old tab.active CSS rule must be removed");
assert.doesNotMatch(popupCss, /\.tab-panel\s*\{/, "old tab-panel CSS rule must be removed");

// ── 2. No legacy card stack / old UI in main shell ──────────────────────────
for (const pattern of [
  /id="wholeProfileStepper"/,
  /id="wholeProfileNextActionCard"/,
  /id="wholeProfileRunMetrics"/,
  /id="wholeProfileRunAlert"/,
  /id="wholeProfileQuickStartHint"/,
  /id="wholeProfileViewResultsButton"/,
  /id="wholeProfileOpenTechnicalButton"/
]) {
  assert.doesNotMatch(mainHtml, pattern, `old card-stack element ${pattern} must not appear in main shell`);
}

// ── 3. ScannerControlPanel main shell structure exists ───────────────────────
assert.match(mainHtml, /id="scannerControlPanelRoot"[^>]*class="[^"]*scanner-shell[^"]*scp-shell/, "main shell must use scanner shell class");
assert.match(mainHtml, /class="[^"]*scanner-hero[^"]*scp-topbar/, "scanner hero must exist");
assert.match(mainHtml, /class="[^"]*scanner-hero-top[^"]*scp-hero-top/, "premium hero top row must exist");
assert.match(mainHtml, /<header class="[^"]*scanner-hero[^"]*scp-topbar[^"]*">[\s\S]*<section class="[^"]*scanner-health-inline[^"]*scp-health-row[^"]*"[\s\S]*<\/header>/, "health chips must render inline inside the hero header");
assert.match(mainHtml, /class="[^"]*scanner-health-inline[^"]*scp-health-row/, "compact status row must exist");
assert.match(mainHtml, /class="[^"]*scanner-main-grid[^"]*scp-main-grid/, "compact main grid must exist");
assert.match(mainHtml, /class="[^"]*scanner-primary-card[^"]*scp-action-block/, "compact primary action card must exist");
assert.match(mainHtml, /class="[^"]*scanner-stats-grid[^"]*scp-counters-block/, "compact counters grid must exist");
assert.match(mainHtml, /class="[^"]*scanner-settings-compact[^"]*scp-settings-bar/, "compact settings section must exist");
assert.match(mainHtml, /class="[^"]*scanner-bottom-dock[^"]*scp-bottom-bar/, "compact bottom dock must exist");
assert.match(mainHtml, /class="[^"]*scanner-alert[^"]*scp-alert/, "inline scanner alert must exist");

// ── 4. Status chips have 4 chips with correct ids ────────────────────────────
assert.match(mainHtml, /id="scannerChipTab"/, "status chips must have Profile chip");
assert.match(mainHtml, /id="scannerChipApi"/, "status chips must have API chip");
assert.match(mainHtml, /id="scannerChipCalibration"/, "status chips must have Calibration chip");
assert.match(mainHtml, /id="scannerChipSafety"/, "status chips must have Safety chip");

// ── 5. Primary action block has title, helper copy, primary button ───────────
assert.match(mainHtml, /id="scannerPrimaryActionTitle"/, "scanner action block must have title");
assert.match(mainHtml, /id="scannerPrimaryActionReason"/, "scanner action block must have helper copy");
assert.match(mainHtml, /id="scannerPrimaryActionButton"/, "scanner action block must have primary button");

// ── 6. Compact settings stay collapsed by default and expose controls on edit ─
assert.match(mainHtml, /id="scannerSettingsSection"[^>]*data-settings-expanded="false"/, "settings section must be collapsed by default");
assert.match(mainHtml, /<strong>Collection settings<\/strong>/, "settings summary must show the compact title");
assert.match(mainHtml, /id="scannerSettingsSummaryValue"[\s\S]*New \+ incomplete · Next 10 · Safe/, "settings collapsed summary must show current defaults");
assert.match(mainHtml, /id="scannerSettingsEditButton"[\s\S]*Edit/, "settings must render collapsed Edit control");
assert.match(mainHtml, /id="scannerSettingsFields"[^>]*hidden/, "settings fields must be collapsed by default");
assert.match(mainHtml, /<span>Mode<\/span>[\s\S]*id="wholeProfileHarvestMode"/, "Edit-expanded settings must contain Mode select markup");
assert.match(mainHtml, /<span>Batch<\/span>[\s\S]*id="wholeProfileHarvestBatch"/, "Edit-expanded settings must contain Batch select markup");
assert.match(mainHtml, /<span>Speed<\/span>[\s\S]*id="wholeProfileHarvestSpeed"/, "Edit-expanded settings must contain Speed select markup");
assert.match(popupSource, /const wholeProfileHarvestModeSelect = document\.querySelector<HTMLSelectElement>\("#wholeProfileHarvestMode"\);/, "compact settings must keep mode select wiring");
assert.match(popupSource, /const wholeProfileHarvestBatchSelect = document\.querySelector<HTMLSelectElement>\("#wholeProfileHarvestBatch"\);/, "compact settings must keep batch select wiring");
assert.match(popupSource, /const wholeProfileHarvestSpeedSelect = document\.querySelector<HTMLSelectElement>\("#wholeProfileHarvestSpeed"\);/, "compact settings must keep speed select wiring");
assert.match(popupSource, /applyScannerSettingsExpanded\(false\);/, "popup init must force settings collapsed by default");
assert.match(popupSource, /scannerSettingsFieldsEl\.hidden = !settingsExpanded;/, "settings expansion must reveal and hide the Mode, Batch, Speed fields locally");
assert.match(popupSource, /scannerSettingsEditButton\.textContent = settingsExpanded \? "Done" : "Edit";/, "settings Edit control must become Done while expanded and return to Edit when collapsed");
assert.match(popupSource, /scannerSettingsEditButton\?\.addEventListener\("click", \(\) => void setScannerSettingsExpanded\(scannerSettingsFieldsEl\?\.hasAttribute\("hidden"\) \?\? true\)\)/, "settings Edit button must toggle expanded and collapsed state locally");

// ── 7. Summary elements exist ────────────────────────────────────────────────
assert.match(mainHtml, /id="scannerHeaderStatus"[^>]*>Ready</, "hero badge must show Ready before profile scan");
assert.match(mainHtml, /id="scannerChipApi"[^>]*>API not checked</, "API idle state must display API not checked in the user-facing chip");
assert.match(mainHtml, /id="scannerEmptyState"[^>]*class="[^"]*scanner-hint[^"]*"[^>]*>Scan a profile to build the collection plan\.</, "pre-scan compact empty state must render as the lighter scanner hint");
assert.match(mainHtml, /id="scannerStatsGrid"[^>]*hidden/, "compact stats grid must exist and be hidden before scan");
assert.doesNotMatch(mainHtml, /id="scannerStatsSubtitle"|id="scannerProgressLabel"|id="scannerProgressDetail"/, "old progress strip elements must be removed from main");
assert.doesNotMatch(mainHtml, /id="scannerProfileMetrics"/, "legacy profile metrics must be removed");
assert.doesNotMatch(mainHtml, /id="scannerPlanMetrics"/, "legacy plan metrics must be removed");

// ── 8. Footer actions have Capture Inbox, Advanced, Pause/Resume, Reset ──────
assert.match(mainHtml, /id="scannerOpenCaptureInboxButton"[^>]*class="[^"]*scanner-secondary-button-blue[^"]*"[\s\S]*Capture Inbox/, "footer must have secondary-blue Capture Inbox button");
assert.match(mainHtml, /id="scannerOpenAdvancedButton"[^>]*class="[^"]*scanner-secondary-button-neutral[^"]*"[\s\S]*Advanced/, "footer must have neutral Advanced button");
assert.match(mainHtml, /id="scannerPauseResumeButton"[^>]*class="[^"]*scanner-secondary-button-neutral[^"]*"/, "footer must keep neutral Pause/Resume button");
assert.match(mainHtml, /id="scannerResetButton"[^>]*class="[^"]*scanner-danger-ghost[^"]*"[\s\S]*Reset/, "footer Reset must use danger ghost styling");

// ── 9. Conditional panels hidden by default ──────────────────────────────────
assert.match(popupHtml, /id="deckPanelResults"[^>]*hidden/, "results panel must start hidden");
assert.match(popupHtml, /id="deckPanelAdvanced"[^>]*hidden/, "advanced panel must start hidden");

// ── 10. Technical/debug content remains outside main ─────────────────────────
assert.match(advancedPanelHtml, /id="apiBaseUrl"/, "API base URL must be in Advanced panel");
assert.match(advancedPanelHtml, /id="webAppOrigin"/, "Web app origin must be in Advanced panel");
assert.match(advancedPanelHtml, /id="wholeProfileProgressDetails"/, "progress details must be in Advanced panel");
assert.match(advancedPanelHtml, /id="wholeProfileTroubleshootingPanel"/, "troubleshooting must be in Advanced panel");
assert.match(advancedPanelHtml, /id="wholeProfileSafetyTipsPanel"/, "safety tips must be in Advanced panel");
assert.match(advancedPanelHtml, /id="advancedDiagnostics"/, "maintenance/diagnostics must be in Advanced panel");
assert.match(resultsPanelHtml, /id="wholeProfileBackendFlowSection"/, "backend flow must be in Results panel");
assert.match(resultsPanelHtml, /id="wholeProfileQueuePreviewPanel"/, "queue preview must be in Results panel");
assert.match(resultsPanelHtml, /id="wholeProfileExtractionResultsSection"/, "extraction results must be in Results panel");
assert.match(resultsPanelHtml, /id="wholeProfileBackendResultsSection"/, "backend results must be in Results panel");

// ── 11. ScannerControlPanel view model exists and is imported ────────────────
assert.match(popupSource, /import\s*\{[^}]*getScannerControlPanelViewModel[^}]*\}\s*from\s*"\.\/wholeProfileHarvest\/viewModel\.js"/, "popup.ts must import getScannerControlPanelViewModel from viewModel.js");
assert.match(popupSource, /function ScannerControlPanel\(state: WholeProfileHarvestState\): ScannerControlPanelViewModel/, "popup.ts must define ScannerControlPanel");
assert.match(popupSource, /function renderDouyinScannerMainScreen\(/, "popup.ts must define renderDouyinScannerMainScreen");
assert.match(popupSource, /getScannerControlPanelViewModel\(state\)/, "scanner renderer must call getScannerControlPanelViewModel");
assert.match(popupSource, /\/\/ 21D-0 POPUP ROOT CONFIRMED/, "popup.ts must contain the Phase 21D-0 root confirmation comment");

// ── 12. active_panel UI prefs ────────────────────────────────────────────────
assert.match(popupSource, /active_panel:\s*"main"\s*\|\s*"results"\s*\|\s*"advanced"/, "UI prefs must define active_panel type");
assert.match(popupSource, /function applyDeckActivePanel\(panel: WholeProfileHarvestUiPrefs\["active_panel"\]\)/, "applyDeckActivePanel must exist");
assert.match(popupSource, /function setDeckActivePanel\(panel: WholeProfileHarvestUiPrefs\["active_panel"\]\)/, "setDeckActivePanel must exist");

// ── 13. Footer/panel click handlers ─────────────────────────────────────────
assert.match(popupSource, /scannerOpenCaptureInboxButton\?\.addEventListener\("click", \(\) => void openCaptureInboxWebAppFromPopup\(\)\)/, "Results footer action must open the web Capture Inbox");
assert.match(popupSource, /scannerOpenAdvancedButton\?\.addEventListener\("click", \(\) => void setDeckActivePanel\("advanced"\)\)/, "Advanced footer action must open advanced panel");
assert.match(popupSource, /deckPanelResultsCloseButton\?\.addEventListener\("click", \(\) => void setDeckActivePanel\("main"\)\)/, "Results close must return to main");
assert.match(popupSource, /deckPanelAdvancedCloseButton\?\.addEventListener\("click", \(\) => void setDeckActivePanel\("main"\)\)/, "Advanced close must return to main");
assert.match(popupSource, /scannerPrimaryActionButton\?\.addEventListener\("click", \(event\) => void runWholeProfilePrimaryActionFromPopup\(event\)\)/, "scanner primary action must call existing handler with the click event");

// ── 14. Settings wired to existing save handler ──────────────────────────────
assert.match(popupSource, /wholeProfileHarvestModeSelect\?\.addEventListener\("change", \(\) => void saveWholeProfileHarvestOptionsFromPopup\(\)\)/, "mode select must save options");
assert.match(popupSource, /wholeProfileHarvestBatchSelect\?\.addEventListener\("change", \(\) => void saveWholeProfileHarvestOptionsFromPopup\(\)\)/, "batch select must save options");
assert.match(popupSource, /wholeProfileHarvestSpeedSelect\?\.addEventListener\("change", \(\) => void saveWholeProfileHarvestOptionsFromPopup\(\)\)/, "speed select must save options");
assert.match(popupSource, /async function saveWholeProfileHarvestOptionsFromPopup\(\)/, "saveWholeProfileHarvestOptionsFromPopup must exist");
assert.match(popupSource, /function selectedWholeProfileHarvestOptions\(\)/, "selectedWholeProfileHarvestOptions must exist");

// ── 15. CSS scp/deck-panel classes exist ─────────────────────────────────────
assert.match(popupCss, /--font-ui:\s*"Google Sans", "Google Sans Text", "Google Sans Flex", "Roboto", "Arial", sans-serif;/, "popup CSS must define the Google Sans UI font stack with safe fallbacks");
assert.match(popupCss, /--font-ui:[^;]*"Google Sans"/, "UI font stack must include Google Sans");
assert.match(popupCss, /--font-ui:[^;]*"Google Sans Text"/, "UI font stack must include Google Sans Text");
assert.match(popupCss, /--font-ui:[^;]*"Google Sans Flex"/, "UI font stack must include Google Sans Flex");
assert.match(popupCss, /--font-ui:[^;]*"Roboto"[^;]*"Arial"/, "UI font stack must include Roboto and Arial fallbacks");
assert.match(popupCss, /--font-mono:\s*"Google Sans Mono", "Google Sans Code", "SFMono-Regular", Consolas, "Liberation Mono", monospace;/, "popup CSS must define the mono font stack for debug/code areas");
assert.match(popupCss, /--fw-regular:\s*400;[\s\S]*--fw-medium:\s*500;[\s\S]*--fw-semibold:\s*600;[\s\S]*--fw-bold:\s*700;[\s\S]*--fw-black:\s*800;/, "popup CSS must define Phase 21D-8 typography weight aliases");
assert.match(popupCss, /body,\s*\n\.scanner-shell,\s*\n\.scp-shell,\s*\n\.dh-shell,\s*\n\.deck-panel\s*\{[\s\S]*font-family:\s*var\(--font-ui\)/, "active popup shells must use the UI font token");
assert.match(popupCss, /\.scanner-shell button,\s*\n\.scanner-shell select,\s*\n\.scanner-shell input,\s*\n\.scanner-shell textarea,\s*\n\.scp-shell button,\s*\n\.scp-shell select,\s*\n\.scp-shell input,\s*\n\.scp-shell textarea\s*\{[\s\S]*font-family:\s*var\(--font-ui\)/, "scanner form controls must inherit the UI font token");
assert.match(popupCss, /\.scanner-debug,\s*\n\.scanner-raw,\s*\n\.scanner-json,\s*\n\.scp-debug,\s*\n\.scp-raw,\s*\n\.scp-json,\s*\npre,\s*\ncode[\s\S]*font-family:\s*var\(--font-mono\)/, "debug and code areas must use the mono font token");
assert.doesNotMatch(popupCss, /fonts\.googleapis\.com|@import\s+url\([^)]*google/i, "Phase 21D-8 must not add remote Google font imports");
assert.doesNotMatch(popupCss, /url\([^)]*\.(?:woff2?|ttf|otf)(?:["')?#]|$)/i, "Phase 21D-8 must not reference local binary font files");
assert.match(popupCss, /\.scanner-shell,\s*\n\.scp-shell\s*\{/, "scanner shell CSS must exist");
assert.match(popupCss, /\.scanner-shell,\s*\n\.scp-shell\s*\{[\s\S]*background:\s*radial-gradient/, "scanner shell must use premium light background");
assert.doesNotMatch(popupCss, /\.scp-shell\s*\{[\s\S]*background:\s*#0f172a/, "scp-shell must not keep the dark debug background");
assert.match(popupCss, /\.scanner-hero,\s*\n\.scp-topbar\s*\{/, "scanner hero CSS must exist");
assert.match(popupCss, /\.scanner-hero,\s*\n\.scp-topbar\s*\{[\s\S]*background:\s*linear-gradient/, "scanner hero must use blue gradient hero styling");
assert.match(popupCss, /\.scanner-health-inline,\s*\n\.scp-health-row\s*\{/, "scanner-health-inline CSS must exist");
assert.match(popupCss, /\.scanner-health-inline,\s*\n\.scp-health-row\s*\{[\s\S]*display:\s*flex/, "health statuses must be inline flex chips, not full-width grid rows");
assert.doesNotMatch(popupCss, /\.scp-health-row\s*\{[\s\S]*grid-template-columns:\s*repeat\(4/, "health row must not reserve four full-width grid cards");
assert.match(popupCss, /\.scanner-main-grid,\s*\n\.scp-main-grid\s*\{/, "scanner main grid CSS must exist");
assert.match(popupCss, /\.scanner-title,\s*\n\.scp-title\s*\{[\s\S]*font-size:\s*20px;[\s\S]*font-weight:\s*var\(--fw-black\);[\s\S]*line-height:\s*1\.1;[\s\S]*letter-spacing:\s*-0\.03em/, "scanner title must use the compact Google-style title scale");
assert.match(popupCss, /\.scanner-subtitle,\s*\n\.scp-subtitle\s*\{[\s\S]*font-size:\s*12px;[\s\S]*font-weight:\s*var\(--fw-medium\);[\s\S]*line-height:\s*1\.35/, "scanner subtitle must use the Google-style subtitle scale");
assert.match(popupCss, /\.scanner-primary-card,\s*\n\.scp-action-block\s*\{/, "scanner primary card CSS must exist");
assert.match(popupCss, /\.scanner-eyebrow,\s*\n\.scp-eyebrow\s*\{[\s\S]*font-size:\s*11px;[\s\S]*font-weight:\s*var\(--fw-bold\);[\s\S]*line-height:\s*1\.2;[\s\S]*letter-spacing:\s*0\.06em/, "section eyebrow must use the Google-style eyebrow scale");
assert.match(popupCss, /\.scanner-primary-card h1,\s*\n\.scp-action-block h1\s*\{[\s\S]*font-size:\s*20px;[\s\S]*font-weight:\s*var\(--fw-black\);[\s\S]*line-height:\s*1\.12/, "primary action title must use the Google-style action title scale");
assert.match(popupCss, /\.scanner-alert,\s*\n\.scp-alert\s*\{/, "scanner-alert CSS must exist");
assert.match(popupCss, /\.scanner-alert\[hidden\],\s*\n\.scp-alert\[hidden\]\s*\{[\s\S]*display:\s*none/, "hidden alert must not render the empty brown/orange bar");
assert.match(popupCss, /\.scanner-settings-compact,\s*\n\.scp-settings-bar\s*\{/, "scanner settings CSS must exist");
assert.match(popupCss, /\.scanner-settings-fields\[hidden\]\s*\{[\s\S]*display:\s*none/, "settings selects must stay hidden while collapsed");
assert.match(popupCss, /\.scanner-settings-compact select,\s*\n\.scp-settings-bar select\s*\{[\s\S]*height:\s*28px/, "settings selects must render compactly when expanded");
assert.match(popupCss, /\.scanner-settings-compact select,\s*\n\.scp-settings-bar select\s*\{[\s\S]*font-size:\s*12px;[\s\S]*font-weight:\s*var\(--fw-semibold\)/, "selects must use the Google-style control scale");
assert.match(popupCss, /\.scanner-stat strong,\s*\n\.scp-counter strong\s*\{[\s\S]*font-size:\s*18px;[\s\S]*font-weight:\s*var\(--fw-black\)/, "stat numbers must use the strong Google-style numeric scale");
assert.match(popupCss, /\.scanner-empty-state,\s*\n\.scanner-hint\s*\{[\s\S]*padding:\s*7px 10px;[\s\S]*background:\s*rgba\(248, 250, 252, 0\.72\);[\s\S]*font-weight:\s*var\(--fw-medium\)/, "empty state must use the lighter compact scanner hint styling");
assert.match(popupCss, /\.scanner-primary-button,\s*\n\.scp-action-block button\s*\{[\s\S]*min-height:\s*38px;[\s\S]*background:\s*linear-gradient/, "primary action button must remain visually primary and largest");
assert.match(popupCss, /\.scanner-bottom-dock,\s*\n\.scp-bottom-bar\s*\{/, "scanner bottom dock CSS must exist");
assert.match(popupCss, /\.scanner-bottom-dock,\s*\n\.scp-bottom-bar\s*\{[\s\S]*grid-template-columns:\s*1fr 1fr minmax\(58px, 0\.68fr\) auto/, "bottom actions must render in one compact dock row");
assert.match(popupCss, /\.scanner-bottom-dock button,\s*\n\.scp-bottom-bar button\s*\{[\s\S]*min-height:\s*30px;[\s\S]*box-shadow:\s*none/, "footer buttons must stay lighter than the primary action");
assert.match(popupCss, /\.scanner-secondary-button-blue,[\s\S]*#scannerOpenCaptureInboxButton[\s\S]*background:\s*#eff6ff;[\s\S]*color:\s*#1d4ed8/, "Capture Inbox footer action must be secondary blue");
assert.match(popupCss, /\.scanner-secondary-button-neutral,[\s\S]*#scannerOpenAdvancedButton[\s\S]*background:\s*#ffffff;[\s\S]*color:\s*#475569/, "Advanced footer action must be neutral");
assert.match(popupCss, /\.scanner-danger-ghost,[\s\S]*#scannerResetButton[\s\S]*background:\s*transparent;[\s\S]*color:\s*#b91c1c/, "Reset footer action must be danger ghost with less visual weight");
assert.match(popupCss, /\.deck-panel\s*\{/, "deck-panel CSS must exist");
assert.match(popupCss, /\.deck-panel__header\s*\{/, "deck-panel__header CSS must exist");
assert.match(popupCss, /\.deck-panel__close\s*\{/, "deck-panel__close CSS must exist");
assert.doesNotMatch(popupCss, /\.deck-shell\s*\{/, "deck-shell CSS must be removed");
assert.doesNotMatch(popupCss, /\.scanner-card\s*\{/, "legacy scanner-card CSS must be removed");
assert.doesNotMatch(popupCss, /\.scanner-footer\s*\{/, "legacy scanner-footer CSS must be removed");

// ── 16. No old card stack classes or forbidden text in main shell ────────────
assert.doesNotMatch(mainHtml, /class="[^"]*dh-card[^"]*"/, "dh-card class must not appear in main shell");
assert.doesNotMatch(mainHtml, /class="[^"]*summary-card[^"]*"/, "summary-card class must not appear in main shell");
assert.doesNotMatch(mainHtml, /class="[^"]*workflow-step[^"]*"/, "workflow-step class must not appear in main shell");
assert.doesNotMatch(mainHtml, /class="[^"]*mini-metric[^"]*"/, "mini-metric class must not appear in main shell");
assert.doesNotMatch(mainHtml, /Douyin Profile Scanner|Profile scan summary|Scan plan summary|Queue Preview|Debug Details|Technical Details|Payload Guard|Flush Batch|Test First|Test Last|Test Random/, "forbidden old main-screen text must not appear in main shell");
assert.doesNotMatch(mainHtml, /Queue Preview/, "main screen must not render Queue Preview");
assert.doesNotMatch(mainHtml, /Payload Guard/, "main screen must not render Payload Guard");
assert.doesNotMatch(mainHtml, /Flush Batch/, "main screen must not render Flush Batch");

// ── 17. Phase 21D-3 visual polish guardrails ─────────────────────────────────
assert.doesNotMatch(mainHtml, /class="[^"]*scp-health-card[^"]*"|>\s*TAB\s*<|>\s*API\s*<|>\s*CALIB\s*<|>\s*SAFETY\s*</, "main screen must not render separate TAB/API/CALIB/SAFETY cards");
assert.equal((mainHtml.match(/Cal needed/g) ?? []).length, 1, "calibration-needed copy must appear once on the static main screen");
assert.doesNotMatch(mainHtml, /Progress|scannerProgressLabel|scannerProgressDetail/, "main screen must not render a separate progress bar during calibration-needed state");
assert.match(mainHtml, /id="scannerOpenCaptureInboxButton"[\s\S]*Capture Inbox/, "main screen must still expose Capture Inbox");
assert.match(mainHtml, /id="scannerOpenAdvancedButton"[\s\S]*Advanced/, "main screen must still expose Advanced");

const scannerRenderMatch = popupSource.match(/function renderDouyinScannerMainScreen\(state: WholeProfileHarvestState\): void \{[\s\S]*?^\}/m);
assert.ok(scannerRenderMatch, "scanner main render function must be statically inspectable");
assert.doesNotMatch(scannerRenderMatch[0], /postJson|createCanonicalHarvestSession|flushCanonicalHarvestPayload|runWholeProfileHarvestProductFromPopup|dryRunWholeProfileFromPopup/, "rendering the main screen must not call backend, scanner, or collector actions");
assert.match(scannerRenderMatch[0], /scannerStatsGridEl\.hidden = !vm\.scanDataVisible/, "rendering must hide stats until scan data is available");
assert.match(scannerRenderMatch[0], /scannerEmptyStateEl\.hidden = vm\.emptyState == null/, "rendering must bind compact empty state from the view model");

// ── 18. panel close buttons exist ────────────────────────────────────────────
assert.match(popupHtml, /id="deckPanelResultsClose"/, "results panel must have close button");
assert.match(popupHtml, /id="deckPanelAdvancedClose"/, "advanced panel must have close button");

// ── 19. View model type exported from viewModel.ts ───────────────────────────
assert.match(viewModelSource, /export type ScannerControlPanelViewModel = /, "ScannerControlPanelViewModel type must be exported");
assert.match(viewModelSource, /export function getScannerControlPanelViewModel\(/, "getScannerControlPanelViewModel function must be exported");

// ── 20. popup.ts applies advanced options selection ──────────────────────────
assert.match(popupSource, /if \(wholeProfileHarvestModeSelect\) wholeProfileHarvestModeSelect\.value = state\.harvest_options\.mode;/, "mode select must sync from state");
assert.match(popupSource, /if \(wholeProfileHarvestBatchSelect\) wholeProfileHarvestBatchSelect\.value = state\.harvest_options\.batch;/, "batch select must sync from state");
assert.match(popupSource, /if \(wholeProfileHarvestSpeedSelect\) wholeProfileHarvestSpeedSelect\.value = state\.harvest_options\.speed;/, "speed select must sync from state");

// ── 21. advanced settings disabled when running ──────────────────────────────
assert.match(popupSource, /if \(wholeProfileHarvestModeSelect\) wholeProfileHarvestModeSelect\.disabled = running \|\| actionState\.loading;/, "mode select must disable when running");
assert.match(popupSource, /if \(wholeProfileHarvestBatchSelect\) wholeProfileHarvestBatchSelect\.disabled = running \|\| actionState\.loading;/, "batch select must disable when running");
assert.match(popupSource, /if \(wholeProfileHarvestSpeedSelect\) wholeProfileHarvestSpeedSelect\.disabled = running \|\| actionState\.loading;/, "speed select must disable when running");

console.log("UI-20C-1 scanner main UI hard-replacement tests passed");
