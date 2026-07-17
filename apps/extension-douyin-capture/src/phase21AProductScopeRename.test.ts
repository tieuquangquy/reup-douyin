import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const testDir = dirname(fileURLToPath(import.meta.url));
const repoRoot = join(testDir, "..", "..", "..");
const popupHtml = readFileSync(join(repoRoot, "public", "popup.html"), "utf8");
const popupSource = readFileSync(join(repoRoot, "src", "popup.ts"), "utf8");
const readinessSource = readFileSync(join(repoRoot, "src", "wholeProfileHarvest", "readiness.ts"), "utf8");
const viewModelSource = readFileSync(join(repoRoot, "src", "wholeProfileHarvest", "viewModel.ts"), "utf8");

const mainHtml = popupHtml.slice(popupHtml.indexOf("<main"), popupHtml.indexOf("</main>") + "</main>".length);

assert.match(mainHtml, /Douyin Scanner/, "main popup must identify the product as Douyin Scanner");
assert.match(mainHtml, /Collect profile videos for Capture Inbox/, "main popup must describe the locked scan-collect-review workflow");
assert.match(popupHtml, /Save to Capture Inbox/, "popup must use Capture Inbox save wording");
assert.match(popupHtml, /Scan session/, "popup save flow must rename session wording for operators");
assert.match(popupHtml, /Save data/, "popup save flow must rename payload wording for operators");
assert.match(popupHtml, /Save 1 Video/, "popup save flow must keep the one-video save action");
assert.match(popupHtml, /Save to Capture Inbox/, "popup save flow must keep the batch save action in product wording");
assert.doesNotMatch(mainHtml, /Payload Guard/, "main popup must not show Payload Guard");
assert.doesNotMatch(mainHtml, /Flush Batch/, "main popup must not show Flush Batch");
assert.doesNotMatch(mainHtml, /Review Board/, "main popup must not show Review Board");
assert.doesNotMatch(mainHtml, /Douyin Profile Scanner/, "main popup must remove the old Phase 21D-2 scanner title");
assert.doesNotMatch(popupHtml, /Douyin Harvest Command Center/, "main popup must not keep the old harvest product title");
assert.doesNotMatch(popupHtml, /<h1>Douyin Harvest<\/h1>/, "main popup must not keep the old harvest heading");

assert.match(popupSource, /Starting collecting\.\.\./, "popup runtime must use Start Collecting wording where applicable");
assert.match(popupSource, /Collecting started\. Keep the modal open until collecting finishes\./, "popup runtime must use collect wording for start status");
assert.match(popupSource, /Collecting completed\. Open Capture Inbox to review collected videos\./, "popup runtime must direct operators to Capture Inbox after collection");
assert.match(popupSource, /Resuming collecting\.\.\./, "popup runtime must use collect wording for resume status");
assert.match(popupSource, /Collecting resumed\./, "popup runtime must use collect wording for resumable state");
assert.doesNotMatch(popupSource, /Open Review Board/, "popup runtime must not emit Review Board CTA wording");
assert.doesNotMatch(popupSource, /\/extensions\/douyin\/review(?!-board)/, "popup runtime must not emit /extensions/douyin/review CTA route");
assert.doesNotMatch(popupSource, /\/extensions\/douyin\/review-board/, "popup runtime must not emit /extensions/douyin/review-board CTA route");

assert.match(readinessSource, /label: "Open Capture Inbox"/, "review CTA label must be Open Capture Inbox");
assert.match(readinessSource, /Open \/extensions\/douyin\/capture-inbox to review collected videos\./, "review CTA copy must point to the locked capture-inbox route");
assert.doesNotMatch(readinessSource, /Open Review Board/, "readiness copy must not mention Review Board");

assert.match(viewModelSource, /export const PRODUCT_TERMS = \{/, "view-model layer must expose a shared terminology helper");
assert.match(viewModelSource, /startCollecting: "Start Collecting"/, "terminology helper must include Start Collecting wording");
assert.match(viewModelSource, /saveToCaptureInbox: "Save to Capture Inbox"/, "terminology helper must include Save to Capture Inbox wording");
assert.match(viewModelSource, /openCaptureInbox: "Open Capture Inbox"/, "terminology helper must include Open Capture Inbox wording");
assert.match(viewModelSource, /dataCheck: "Data check"/, "terminology helper must include Data check wording");
assert.match(viewModelSource, /scanSession: "Scan session"/, "terminology helper must include Scan session wording");
assert.match(viewModelSource, /Create Scan Session/, "view-model layer must rename Create Save Session in user-facing wording");
assert.match(viewModelSource, /Data check/, "view-model layer must use Data check in user-facing wording");
assert.match(viewModelSource, /Save to Capture Inbox/, "view-model layer must use Save to Capture Inbox in user-facing wording");
assert.doesNotMatch(viewModelSource, /Open Review Board/, "view-model layer must not mention Review Board in user-facing wording");

assert.match(popupHtml, /Advanced Details/, "advanced/debug surface may remain available");
assert.match(popupHtml, /Maintenance/, "advanced/debug maintenance section may remain available");
assert.match(popupHtml, /Modal Whole Profile Test/, "advanced/debug technical labels may remain available when needed");

console.log("phase21A scope rename tests passed");
