/** Ops Home V9 - creative command center with evidence-backed admission control. */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const testDir = dirname(fileURLToPath(import.meta.url));
const webSrc = resolve(testDir, "..");

const page = readFileSync(resolve(webSrc, "components/ops-console/OpsHomePage.tsx"), "utf8");
const api = readFileSync(resolve(webSrc, "lib/api.ts"), "utf8");
const types = readFileSync(resolve(webSrc, "types/operations.ts"), "utf8");
const css = readFileSync(resolve(webSrc, "app/globals.css"), "utf8");
const pkg = readFileSync(resolve(webSrc, "../package.json"), "utf8");

assert.match(page, /ops-home-v6/, "Ops Home must use the scoped V6 dashboard shell");
assert.match(page, /ops-home-v7/, "Ops Home must apply the V7 creative command-center layer");
assert.match(page, /ops-home-v9/, "Ops Home must apply the V9 hidden-risk and admission layer");
assert.match(page, /fetchOpsHomeSummary/, "Ops Home must load one canonical summary");
assert.doesNotMatch(page, /Promise\.all\(/, "Ops Home must not compose competing authorities in the browser");
assert.doesNotMatch(page, /fetchOperationalMetrics|fetchPublishHealthDashboard|fetchPublishControlQueue/, "Ops Home must not call legacy authorities directly");
assert.match(api, /\/ops\/home-summary/, "API client must call the canonical Ops Home endpoint");
assert.match(types, /OpsHomeSummaryResponse/, "Web types must model the Ops Home contract");

assert.match(page, /OverviewHeader/, "Home must lead with a concise operational status header");
assert.match(page, /ops-home-v7-beacon/, "The status header must use one expressive system beacon");
assert.match(page, /DecisionMetrics/, "Home must expose only the three decision metrics");
assert.match(page, /Critical incidents/, "Decision metrics must include distinct critical signals");
assert.match(page, /queue\.oldest_queued_at/, "Decision metrics must expose oldest backlog age");
assert.match(page, /queue\.busy_worker_count/, "Decision metrics must expose busy worker signals");
assert.match(page, /running_without_lock/, "Home must surface running work without a worker lock");
assert.doesNotMatch(page, /SystemPulse|ProductionTopology|QueueCommandStrip/, "Legacy pulse, topology, and five-card strip must be removed");
assert.match(page, /OperationalRibbon/, "Current operational domains must form a compact status ribbon");
assert.match(page, /summary\.operational_status/, "The status ribbon must use canonical domain state");
assert.match(page, /Admission control/, "The command stage must expose a safe-to-accept-work verdict");
assert.match(page, /summary\.admission_verdict/, "Admission control must come from the canonical backend verdict");

assert.match(page, /HiddenRiskStrip/, "Home must expose overlooked operational signals as one compact strip");
assert.match(page, /Hidden operational risks/, "The hidden-risk strip needs an explicit operator label");
assert.match(page, /observability_coverage|Observability coverage/, "Hidden risks must include active-work observability coverage");
assert.match(page, /risk\.segments/, "Hidden risks must retain their evidence breakdown");
assert.match(page, /ops-home-v9-risk-strip__summary/, "Hidden risks must summarize clear and attention states before detail");
assert.match(page, /ops-home-v9-risk__state/, "Every hidden-risk lane must carry a text status, not color alone");
assert.match(page, /ops-home-v9-risk__evidence/, "Every hidden-risk lane must progressively disclose its evidence");
assert.match(types, /OpsHomeHiddenRisk/, "Web types must model hidden-risk evidence");
assert.match(types, /OpsHomeAdmissionVerdict/, "Web types must model the admission verdict");

assert.match(page, /PipelineWorkloadChart/, "The dominant visualization must be pipeline workload");
assert.match(page, /Stacked horizontal bar chart/, "Pipeline workload must declare its chart form accessibly");
assert.match(page, /values\[segment\.key\] \/ maximum/, "Workload bars must use one shared scale across job types");
assert.match(page, /activeMaximum === 0[\s\S]*Queue is clear/, "An idle queue must render an explicit clear state instead of an axis");
assert.match(page, /chartRows\.filter\(\(item\) => item\.total > 0\)/, "The workload chart must hide inactive job types");
assert.doesNotMatch(page, /Completed history/, "Completed history must not be repurposed as active workload");
assert.match(page, /running[\s\S]*queued[\s\S]*review[\s\S]*retryable[\s\S]*failed/, "Workload chart must preserve actionable state categories");
assert.match(page, /failure_rate_percent/, "Workload rows must expose failure rate");
assert.match(page, /average_step_seconds/, "Workload rows must expose observed duration");

assert.match(page, /IncidentQueue/, "Operational actions must remain a prioritized incident list");
assert.match(page, /items\.slice\(0, 4\)/, "Incident density must be capped on Home");
assert.match(page, /item\.detail/, "Incident rows must expose context without tooltips");
assert.match(page, /item\.recommended_action/, "Incident rows must expose the recommended next action");

assert.match(page, /PublishOutcomeChart/, "Publish outcomes must use a seven-day chart");
assert.match(page, /Seven-day stacked column chart/, "Publish outcomes must use stacked daily columns");
assert.match(page, /No publish activity[\s\S]*neutral/, "A zero-attempt publish window must stay neutral");
assert.doesNotMatch(page, /conic-gradient|ops-home-v4-ring/, "Home must not use donut or ring charts");

assert.match(page, /FailurePareto/, "Recurring failures must use a Pareto bar view");
assert.match(page, /ops-home-v7-rank/, "Pareto rows must expose a readable visual rank");
assert.match(page, /FetchHealthChart/, "Fetch health must use ranked account bars");
assert.match(page, /blocked_rate_percent/, "Fetch bars must use blocked-rate values");
assert.match(page, /resolvedAccounts[\s\S]*Account attribution unavailable/, "Missing account ids must render an attribution state instead of a fake ranking");
assert.match(page, /row\.runs_total/, "Resolved account rows must show their own run count");
assert.match(page, /top_blocked_reasons\.slice\(0, 3\)/, "Fetch reasons must be progressively disclosed");
assert.match(page, /DependencyReadiness/, "Dependency readiness must use explicit status rows");
assert.match(page, /not_observed/, "Unproven dependencies must remain explicitly not observed");
assert.match(page, /storage_capacity/, "Dependency readiness must retain numeric storage headroom");
assert.match(page, /Control plane[\s\S]*Execution[\s\S]*Media runtime[\s\S]*External & publishing/, "Dependencies must be grouped into architecture layers");
assert.match(page, /ops-home-v8-dependency-summary/, "Dependency readiness must expose one compact state summary");
assert.match(page, /FreshnessLedger/, "Home must show source read-model check times");
assert.doesNotMatch(page, /<table/, "Ops Home must defer dense tables to specialist pages");

assert.match(css, /\.ops-home-v6-overview/, "CSS must define the operational header");
assert.match(css, /\.ops-home-v7-command-stage/, "CSS must define the creative command stage");
assert.match(css, /\.ops-home-v7-beacon/, "CSS must define the system beacon");
assert.match(css, /\.ops-home-v7-ribbon/, "CSS must define the operational status ribbon");
assert.match(css, /\.ops-home-v6-decisions[\s\S]*repeat\(3/, "Desktop decision metrics must use three columns");
assert.match(css, /\.ops-home-v6-primary-grid/, "CSS must define the dominant workload plus incident layout");
assert.match(css, /\.ops-home-v6-workload-row__plot/, "CSS must define shared-scale workload bars");
assert.match(css, /\.ops-home-v6-columns/, "CSS must define stacked publish columns");
assert.match(css, /\.ops-home-v6-pareto/, "CSS must define Pareto bars");
assert.match(css, /\.ops-home-v6-fetch-rows/, "CSS must define ranked fetch bars");
assert.match(css, /\.ops-home-v7-attribution-missing/, "CSS must define the missing-attribution state");
assert.match(css, /ops-home-v6-analytics-grid[\s\S]*align-items: start/, "Analytics panels must keep independent content height");
assert.match(css, /\.ops-home-v6-dependencies/, "CSS must define dependency readiness rows");
assert.match(css, /\.ops-home-v8-dependency-stack/, "Dependency readiness must use the layered system stack");
assert.match(css, /\.ops-home-v8-dependency-layer/, "CSS must define architecture layers");
assert.match(css, /\.ops-home-v9-admission/, "CSS must visually distinguish the admission verdict");
assert.match(css, /\.ops-home-v9-risk-strip/, "CSS must define the connected hidden-risk strip");
assert.match(css, /\.ops-home-v9-risk-grid[\s\S]*repeat\(4/, "Desktop hidden risks must use four connected instruments");
assert.match(css, /\.ops-home-v9-risk__value > strong[\s\S]*font-size:\s*1\.55rem/, "Risk values must remain readable at dashboard distance");
assert.match(css, /@media \(max-width: 1180px\)[\s\S]*ops-home-v9-risk-grid[\s\S]*repeat\(2/, "Risk lanes must become a readable 2x2 grid before they become cramped");
assert.match(css, /@media \(max-width: 680px\)[\s\S]*ops-home-v6-decisions[\s\S]*grid-template-columns: 1fr/, "Decision metrics must stack on mobile");
assert.match(css, /@media \(prefers-reduced-motion: reduce\)[\s\S]*ops-home-v6/, "V6 interactions must respect reduced motion");
assert.match(pkg, /ops-home-ui\.test\.ts/, "package.json must run the Ops Home UI contract test");

console.log("ops-home-ui tests passed");
