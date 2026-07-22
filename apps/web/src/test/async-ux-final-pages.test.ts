import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const read = (path: string) => readFileSync(`src/components/${path}`, "utf8");

const readPages = [
  "ops-console/OpsJobsPage.tsx",
  "operator-routes/PublishDraftByIdPage.tsx",
  "operator-routes/PublishHandoffByIdPage.tsx",
  "ops-console/OpsHomePage.tsx",
  "ops-console/OpsRoutingRulesPage.tsx",
] as const;

for (const pagePath of readPages) {
  const source = read(pagePath);
  assert.match(source, /AsyncContentBoundary/, `${pagePath} must standardize initial and refresh states`);
  assert.match(source, /useLatestRequest/, `${pagePath} must ignore stale read responses`);
  assert.match(source, /refreshing=\{request\.refreshing\}/, `${pagePath} must keep content visible during refresh`);
  assert.match(source, /request\.error/, `${pagePath} must surface read failures`);
}

const jobs = read(readPages[0]);
assert.match(jobs, /useAsyncAction/, "Ops Jobs must gate mutations and clipboard writes");
assert.match(jobs, /useNotice/, "Ops Jobs must publish terminal action notices");
assert.match(jobs, /<AsyncButton[\s\S]*?pending=\{action\.isPending\(`retry-\$\{job\.id\}`\)\}/, "Retry must expose per-job pending feedback");
assert.match(jobs, /<AsyncButton[\s\S]*?pending=\{action\.isPending\(`delete-\$\{job\.id\}`\)\}/, "Delete must expose per-job pending feedback");
assert.match(jobs, /action\.run\(`copy-\$\{jobId\}`/, "Clipboard writes must be synchronously gated");
assert.match(jobs, /OffsetLoadMoreFooter/, "Ops Jobs must preserve load-more pagination");
assert.match(jobs, /ops-job-row-\$\{/, "Ops Jobs must preserve job detail focus rows");

const draft = read(readPages[1]);
assert.match(draft, /skeletonVariant="detail"|skeleton=\{/, "Draft detail must use a detail-shaped loading state");

const handoff = read(readPages[2]);
assert.match(handoff, /OpsDetailPanel/, "Handoff detail rendering must remain");
assert.match(handoff, /skeleton=\{<OpsStatePanel/, "Handoff detail must retain its existing skeleton slot");

console.log("final page async UX contract tests passed");
