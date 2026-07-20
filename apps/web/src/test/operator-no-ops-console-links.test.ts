/**
 * Operator Studio pages must not deep-link Ops Console monitor/admin surfaces.
 * Allowlist: /ops/pipeline, /ops/extensions/*
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import {
  isOpsConsoleHref,
  operatorFallbackForOpsHref,
  operatorSafeHref
} from "../lib/opsConsoleBoundary";

const testDir = dirname(fileURLToPath(import.meta.url));
const webSrc = resolve(testDir, "..");

const OPERATOR_SOURCES = [
  "lib/operatorHomeState.ts",
  "components/operator-home/OperatorHomePage.tsx",
  "components/operator-home/FreshnessStrip.tsx",
  "components/operator-routes/PipelineDashboardPage.tsx",
  "components/operator-routes/PublishDraftsIndexPage.tsx",
  "components/operator-routes/OperatorPublishDraftPage.tsx",
  "components/publish-draft/PublishDraftHeader.tsx",
  "components/transcript-editor/TranscriptEditorHeader.tsx",
  "components/reup-queue/ReupQueuePage.tsx",
  "app/production/downloads/page.tsx",
  "app/optimization/page.tsx"
] as const;

const FORBIDDEN_HREF =
  /(?:href|href=)\s*[:=]?\s*["'`](\/ops\/(?:jobs|health|risk|reconciliation|publish-health|publish-attempts|publish-control|accounts|assets|tools|users|routing-rules|translation|caption|tts|optimization)[^"'`]*)["'`]/g;

assert.equal(isOpsConsoleHref("/ops/jobs"), true);
assert.equal(isOpsConsoleHref("/ops/pipeline"), false);
assert.equal(isOpsConsoleHref("/ops/extensions/douyin/capture-inbox"), false);
assert.equal(operatorSafeHref("/ops/risk", "/publishing/drafts"), "/publishing/drafts");
assert.equal(operatorFallbackForOpsHref("/ops/jobs?job_id=x"), "/ops/pipeline");
assert.equal(operatorFallbackForOpsHref("/ops/publish-health"), "/publishing/drafts");
assert.equal(operatorFallbackForOpsHref("/ops/translation-ai"), null);

for (const rel of OPERATOR_SOURCES) {
  const source = readFileSync(resolve(webSrc, rel), "utf8");
  const matches = [...source.matchAll(FORBIDDEN_HREF)];
  assert.equal(
    matches.length,
    0,
    `${rel} must not deep-link Ops Console (found: ${matches.map((m) => m[1]).join(", ") || "none"})`
  );
  assert.doesNotMatch(
    source,
    /href=\{`\/ops\/jobs/,
    `${rel} must not template-link /ops/jobs`
  );
  assert.doesNotMatch(source, /href=["']\/ops["']/, `${rel} must not link Ops Console root`);
}

const pkg = readFileSync(resolve(webSrc, "../package.json"), "utf8");
assert.match(pkg, /operator-no-ops-console-links\.test\.ts/, "package.json must run operator-no-ops-console-links test");

console.log("operator-no-ops-console-links tests passed");
