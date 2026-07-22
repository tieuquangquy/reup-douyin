import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const testDir = dirname(fileURLToPath(import.meta.url));
const routeSource = readFileSync(
  resolve(testDir, "../components/operator-routes/OperatorTranscriptEditorPage.tsx"),
  "utf8"
);
const pageSource = readFileSync(
  resolve(testDir, "../components/transcript-editor/TranscriptEditorPage.tsx"),
  "utf8"
);
const enSource = readFileSync(resolve(testDir, "../lib/i18n/en.json"), "utf8");

assert.match(routeSource, /TopbarRefreshButton/, "Transcript editor topbar must expose Refresh like other Operator pages");
assert.doesNotMatch(
  routeSource,
  /nav\.reviewBoard|nav\.finalReview|common\.home/,
  "Transcript editor must not duplicate shell navigation in the topbar"
);
assert.match(routeSource, /TranscriptEditorPageHandle|refreshRef|useRef/, "Shell must call into the editor refresh handle");
assert.match(pageSource, /useImperativeHandle|forwardRef/, "Transcript editor must expose an imperative refresh handle");
assert.match(pageSource, /refreshUnsavedConfirm|hasUnsavedChanges/, "Refresh must guard unsaved edits");
assert.match(enSource, /"refreshUnsavedConfirm"/, "i18n must include refresh unsaved confirm copy");

console.log("operator-transcript-editor-nav tests passed");
