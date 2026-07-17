import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

import { createWholeProfileHarvestIdleState } from "./wholeProfileHarvest/state.js";
import { getWholeProfileHarvestActionState, getWholeProfileHarvestReadiness } from "./wholeProfileHarvest/readiness.js";

const popupHtml = readFileSync(new URL("../public/popup.html", import.meta.url), "utf8");
const popupCss = readFileSync(new URL("../public/popup.css", import.meta.url), "utf8");
const readinessSource = readFileSync(new URL("./wholeProfileHarvest/readiness.ts", import.meta.url), "utf8");
const popupSource = readFileSync(new URL("./popup.ts", import.meta.url), "utf8");

const idle = createWholeProfileHarvestIdleState("2026-05-06T16:00:00.000Z");
const readiness = getWholeProfileHarvestReadiness(idle);
const actions = getWholeProfileHarvestActionState(idle);

const mainHtml = popupHtml.slice(popupHtml.indexOf("<main"), popupHtml.indexOf("</main>") + "</main>".length);

assert.match(mainHtml, /Douyin Scanner/, "main title must use scanner branding");
assert.match(mainHtml, /Collect profile videos for Capture Inbox/, "subtitle must explain the scan-to-review workflow briefly");
assert.match(popupHtml, /id="scannerPrimaryActionButton"/, "main shell must render the scanner primary action button");
assert.match(mainHtml, /Scan/, "scanner copy must use friendly scan wording");
assert.doesNotMatch(mainHtml, /Test 3 Random Videos|Test First|Test Last|Test Random/, "legacy dry-run wording must be removed from the main popup");
assert.doesNotMatch(mainHtml, /Douyin Profile Scanner|Profile scan summary|Scan plan summary|Queue Preview|Debug Details|Technical Details|Payload Guard|Flush Batch/, "old technical wording must be removed from the main popup");
assert.match(popupHtml, /Save to Capture Inbox/, "results panel must keep friendly Capture Inbox wording");
assert.match(popupHtml, /Results Dashboard/, "results panel must keep clear results wording");
assert.match(popupHtml, /Advanced Details/, "advanced panel must use advanced-details wording");
assert.match(popupHtml, /Troubleshooting/, "popup must expose troubleshooting guidance");
assert.match(popupHtml, /Safety tips/, "popup must expose safety tips guidance");
assert.match(popupHtml, /Save to Capture Inbox/, "popup must label the save section with friendly Capture Inbox wording");
assert.doesNotMatch(popupHtml, /What do these mean\?/, "Action Deck must not keep the long settings explainer in the main shell");
assert.match(popupHtml, /Advanced Details/, "main progress details must use advanced-details wording");
assert.match(popupHtml, /Maintenance \+ Debug/, "advanced diagnostics must use maintenance wording");
assert.doesNotMatch(popupHtml, /<button id="probeHarvestButton"/, "main popup must not render the legacy probe-only button");
assert.doesNotMatch(popupHtml, /id="harvestProgressPanel"/, "main popup must not render legacy harvest progress panel markup");
assert.doesNotMatch(popupHtml, /id="wholeProfileStagedHarvestV2Panel"/, "main popup must not render legacy V2 progress panel markup");
assert.doesNotMatch(popupHtml, />Technical<\//, "main popup must not expose Technical as a top-level tab label");

assert.equal(readiness.next_recommended_action.label, "Scan Profile");
assert.equal(actions.verifyProfile.label, "Scan Profile");

assert.match(readinessSource, /Solve security check/, "captcha next action wording must be friendly");
assert.match(readinessSource, /Create Scan Session/, "backend session wording must be friendly");
assert.match(readinessSource, /Data check/, "payload preview wording must be friendly");
assert.match(readinessSource, /Save 1 Video/, "one-item save wording must be friendly");
assert.match(readinessSource, /Save to Capture Inbox/, "batch save wording must be friendly");
assert.match(readinessSource, /Data check failed/, "payload guard failure wording must be friendly");
assert.match(readinessSource, /Create a scan session first\./, "save session wording must stay operator-friendly");

assert.match(popupSource, /friendlyWholeProfileErrorMessage/, "popup must map technical errors to friendly status copy");
assert.match(popupSource, /successWholeProfileMessage/, "popup must map successful steps to friendly success copy");
assert.match(popupSource, /WHOLE_PROFILE_UI_PREFS_KEY/, "popup must persist guide panel UI preferences locally");
assert.match(popupSource, /scannerPrimaryActionReasonEl/, "popup must render a dedicated scanner disabled reason helper");
assert.match(popupSource, /scannerPrimaryActionButton/, "popup must expose a one-primary-action workflow button");
assert.match(popupCss, /\.scp-subtitle/, "popup must style the compact control-panel subtitle block");
assert.match(popupCss, /\.scp-alert/, "popup must style inline scanner alerts");
assert.match(popupCss, /\.operator-guide/, "popup must style operator guide panels");
assert.match(popupCss, /\.compact-api-row/, "popup must style advanced settings rows");
assert.match(popupCss, /max-width:\s*420px;/, "popup width must remain stable");
assert.doesNotMatch(popupCss, /word-break:\s*break-all/, "UI must avoid one-character-per-line wrapping");

console.log("wholeProfileHarvest wording polish tests passed");
