import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const testDir = dirname(fileURLToPath(import.meta.url));
const webRoot = resolve(testDir, "..");
const pageLoadErrorSource = readFileSync(resolve(webRoot, "components/shared/PageLoadError.tsx"), "utf8");
const boundarySource = readFileSync(resolve(webRoot, "components/shared/AsyncContentBoundary.tsx"), "utf8");
const opsSharedSource = readFileSync(resolve(webRoot, "components/ops-console/OpsShared.tsx"), "utf8");
const globalCssSource = readFileSync(resolve(webRoot, "app/globals.css"), "utf8");
const enSource = readFileSync(resolve(webRoot, "lib/i18n/en.json"), "utf8");
const viSource = readFileSync(resolve(webRoot, "lib/i18n/vi.json"), "utf8");

assert.match(pageLoadErrorSource, /export function PageLoadError/, "Shared page-load error surface must exist");
assert.match(pageLoadErrorSource, /page-load-error/, "PageLoadError must use a stable CSS root class");
assert.match(pageLoadErrorSource, /page-load-error__title/, "PageLoadError must expose a title slot");
assert.match(pageLoadErrorSource, /page-load-error__detail/, "PageLoadError must expose a detail slot");
assert.match(pageLoadErrorSource, /page-load-error__retry/, "PageLoadError must expose a Retry CTA class");
assert.match(pageLoadErrorSource, /onRetry/, "PageLoadError must accept an onRetry callback");
assert.match(pageLoadErrorSource, /common\.retry/, "Retry label must use shared i18n by default");
assert.match(pageLoadErrorSource, /common\.couldNotLoadTitle/, "Default title must be i18n-backed");
assert.match(pageLoadErrorSource, /common\.couldNotLoadDetail/, "Default detail must be i18n-backed");
assert.match(pageLoadErrorSource, /role="alert"/, "Standalone page-load errors must announce as alerts");
assert.doesNotMatch(pageLoadErrorSource, /<main\b/, "PageLoadError must not wrap content in a nested main");

assert.match(boundarySource, /PageLoadError/, "AsyncContentBoundary must default to PageLoadError");
assert.match(
  boundarySource,
  /errorState \?\? <PageLoadError/,
  "Boundary error branch must render PageLoadError when callers omit errorState"
);

assert.match(opsSharedSource, /PageLoadError/, "OpsState error branch must reuse PageLoadError");
assert.match(
  opsSharedSource,
  /if \(retry\)[\s\S]*return <PageLoadError/,
  "OpsState with retry must delegate to PageLoadError instead of nesting ops-page/main"
);

assert.match(globalCssSource, /\.page-load-error\b/, "PageLoadError must have shared stylesheet rules");
assert.match(globalCssSource, /\.page-load-error__title/, "Title tone must be styled for error emphasis");
assert.match(globalCssSource, /\.page-load-error__retry/, "Retry button must be styled");
assert.match(
  globalCssSource,
  /\.async-content-state\.is-error[\s\S]*\.page-load-error/,
  "Error wash frame must compose with the shared error card"
);

assert.match(enSource, /"couldNotLoadTitle"/, "EN must define couldNotLoadTitle");
assert.match(enSource, /"couldNotLoadDetail"/, "EN must define couldNotLoadDetail");
assert.match(viSource, /"couldNotLoadTitle"/, "VI must define couldNotLoadTitle");
assert.match(viSource, /"couldNotLoadDetail"/, "VI must define couldNotLoadDetail");

console.log("page load error tests passed");
