/**
 * Guard against unstable `load` in useEffect deps (infinite refetch / UI flicker).
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const testDir = dirname(fileURLToPath(import.meta.url));
const webSrcDir = resolve(testDir, "..");

const byId = readFileSync(resolve(webSrcDir, "components/operator-routes/PublishDraftByIdPage.tsx"), "utf8");
const draftsIndex = readFileSync(resolve(webSrcDir, "components/operator-routes/PublishDraftsIndexPage.tsx"), "utf8");
const optimization = readFileSync(resolve(webSrcDir, "components/optimization/OptimizationPage.tsx"), "utf8");
const pkg = readFileSync(resolve(webSrcDir, "../package.json"), "utf8");

assert.doesNotMatch(
  byId,
  /\[\s*draftId\s*,\s*load\s*\]/,
  "PublishDraftByIdPage must not depend on unstable load identity (causes flicker)"
);
assert.match(byId, /useEffect\(\(\) => \{\s*void load\(\);\s*\},\s*\[draftId(?:,\s*t)?\]\)/s, "PublishDraftByIdPage effect must re-run only on draftId (and optional stable t)");

assert.doesNotMatch(
  draftsIndex,
  /useEffect\(\(\) => \{\s*void load\(\);\s*\},\s*\[load\]\)/s,
  "PublishDraftsIndexPage must not depend on unstable load identity"
);
assert.match(draftsIndex, /useEffect\(\(\) => \{\s*void load\(\);\s*\},\s*\[t\]\)/s, "PublishDraftsIndexPage effect must use stable t dep");

assert.doesNotMatch(
  optimization,
  /useEffect\(\(\) => \{\s*void load\(\);\s*\},\s*\[load\]\)/s,
  "OptimizationPage must not depend on unstable load identity"
);
assert.match(optimization, /useEffect\(\(\) => \{\s*void load\(\);\s*\},\s*\[t\]\)/s, "OptimizationPage effect must use stable t dep");

assert.match(pkg, /publish-draft-load-effect\.test\.ts/, "package.json must run publish-draft-load-effect test");

console.log("publish-draft-load-effect tests passed");
