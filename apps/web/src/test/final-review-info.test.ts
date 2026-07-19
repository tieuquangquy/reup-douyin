import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const testDir = dirname(fileURLToPath(import.meta.url));
const panelSource = readFileSync(
  resolve(testDir, "../components/final-review/FinalRenderMetadataPanel.tsx"),
  "utf8"
);
const pageSource = readFileSync(resolve(testDir, "../components/final-review/FinalReviewPage.tsx"), "utf8");
const stateSource = readFileSync(resolve(testDir, "../lib/finalReviewState.ts"), "utf8");
const en = JSON.parse(readFileSync(resolve(testDir, "../lib/i18n/en.json"), "utf8")) as {
  finalReviewInfo: Record<string, string>;
};
const vi = JSON.parse(readFileSync(resolve(testDir, "../lib/i18n/vi.json"), "utf8")) as {
  finalReviewInfo: Record<string, string>;
};

assert.match(stateSource, /FINAL_RENDER_VIDEO/, "Info specs must fall back to FINAL_RENDER_VIDEO asset size/job");
assert.match(panelSource, /resolveRenderTechSpecs/, "Info panel must use resolved tech specs");
assert.match(panelSource, /finalReviewInfo\./, "Info panel must use i18n labels");
assert.match(panelSource, /jobIdMissing/, "Empty job id must explain why it is missing");
assert.ok(en.finalReviewInfo.jobIdMissing.length > 0);
assert.ok(vi.finalReviewInfo.jobIdMissing.length > 0);
assert.match(pageSource, /FinalRenderMetadataPanel[\s\S]*manifest=\{manifest\}/, "Info panel must receive asset manifest");
assert.doesNotMatch(panelSource, /"unknown"/, "Info panel must not hardcode English unknown");

assert.ok(en.finalReviewInfo.resolution.length > 0);
assert.ok(vi.finalReviewInfo.duration.length > 0);
assert.ok(en.finalReviewInfo.publishReadyNotSet.length > 0);

console.log("final-review info panel tests passed");
