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
  assert.doesNotMatch(source, /skeleton=\{<(OpsState|OpsStatePanel)[\s\S]*?\}/, `${pagePath} must not use OpsState panels as loading skeletons`);
  assert.match(source, /loadingLabel=\{t\(/, `${pagePath} must pass an i18n loadingLabel`);
}

const jobs = read(readPages[0]);
assert.match(jobs, /useAsyncAction/, "Ops Jobs must gate mutations and clipboard writes");
assert.match(jobs, /useNotice/, "Ops Jobs must publish terminal action notices");
assert.match(jobs, /<AsyncButton[\s\S]*?pending=\{action\.isPending\(`retry-\$\{job\.id\}`\)\}/, "Retry must expose per-job pending feedback");
assert.match(jobs, /<AsyncButton[\s\S]*?pending=\{action\.isPending\(`delete-\$\{job\.id\}`\)\}/, "Delete must expose per-job pending feedback");
assert.match(jobs, /action\.run\(`copy-\$\{jobId\}`/, "Clipboard writes must be synchronously gated");
assert.match(jobs, /OpsJobsPagination/, "Ops Jobs must preserve explicit pagination navigation");
assert.match(jobs, /busy=\{request\.refreshing\}/, "Ops Jobs pagination must expose refresh feedback");
assert.match(jobs, /ops-job-row-\$\{/, "Ops Jobs must preserve job detail focus rows");
assert.match(jobs, /skeletonVariant="table"/, "Ops Jobs must use the table skeleton shape");

const draft = read(readPages[1]);
assert.match(draft, /skeletonVariant="detail"/, "Draft detail must use a detail-shaped loading state");

const handoff = read(readPages[2]);
assert.match(handoff, /OpsDetailPanel/, "Handoff detail rendering must remain");
assert.match(handoff, /skeletonVariant="detail"/, "Handoff detail must use the shared detail skeleton");
assert.doesNotMatch(handoff, /skeleton=\{<OpsStatePanel/, "Handoff detail must not keep OpsStatePanel as the loading skeleton");

const home = read(readPages[3]);
assert.match(home, /skeletonVariant="dashboard"/, "Ops Home must use the dashboard skeleton shape");

const routing = read(readPages[4]);
assert.match(routing, /skeletonVariant="dashboard"/, "Routing rules must use the dashboard skeleton shape");

console.log("final page async UX contract tests passed");
