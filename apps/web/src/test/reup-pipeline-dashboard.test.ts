/** Pipeline Dashboard — flat Operations Board, distinct from Home. */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const testDir = dirname(fileURLToPath(import.meta.url));
const webSrcDir = resolve(testDir, "..");
const pageSource = readFileSync(resolve(webSrcDir, "components/operator-routes/PipelineDashboardPage.tsx"), "utf8");
const routeSource = readFileSync(resolve(webSrcDir, "app/ops/pipeline/page.tsx"), "utf8");
const apiSource = readFileSync(resolve(webSrcDir, "lib/api.ts"), "utf8");
const operationsTypesSource = readFileSync(resolve(webSrcDir, "types/operations.ts"), "utf8");
const navSource = readFileSync(resolve(webSrcDir, "lib/navigationConfig.ts"), "utf8");
const globalCssSource = readFileSync(resolve(webSrcDir, "app/globals.css"), "utf8");
const en = readFileSync(resolve(webSrcDir, "lib/i18n/en.json"), "utf8");
const vi = readFileSync(resolve(webSrcDir, "lib/i18n/vi.json"), "utf8");
const pkg = readFileSync(resolve(webSrcDir, "../package.json"), "utf8");

assert.match(routeSource, /PipelineDashboardPage/, "The /ops/pipeline route must render PipelineDashboardPage");
assert.match(apiSource, /fetchPipelineDashboard/, "API client must expose fetchPipelineDashboard");
assert.match(apiSource, /\/pipeline-dashboard/, "API client must call the operator-accessible aggregation endpoint");
assert.doesNotMatch(apiSource, /\/ops\/pipeline-dashboard/, "Pipeline API must not stay under the Ops-only prefix");
assert.match(navSource, /\/ops\/pipeline/, "Navigation must expose the pipeline route");

assert.match(
  operationsTypesSource,
  /"capture"[\s\S]*"review"[\s\S]*"reup_queue"[\s\S]*"download"[\s\S]*"audio_analysis"[\s\S]*"translate"[\s\S]*"tts"[\s\S]*"ocr"[\s\S]*"render"[\s\S]*"output_review"[\s\S]*"draft"[\s\S]*"export_package"[\s\S]*"publish_handoff"/,
  "PipelineStageKey must define the canonical 13-stage order",
);
assert.match(
  operationsTypesSource,
  /waiting_count[\s\S]*running_count[\s\S]*review_count[\s\S]*failed_count[\s\S]*ready_count[\s\S]*total_count/,
  "Stage contract must expose five exclusive workload buckets and a total",
);
assert.match(operationsTypesSource, /output_qa_summary/, "Pipeline contract must expose canonical Output QA buckets");

assert.match(pageSource, /OperatorStudioShell/, "Pipeline must keep OperatorStudioShell");
assert.match(pageSource, /TopbarRefreshButton/, "Refresh must stay in the topbar");
assert.match(pageSource, /AsyncContentBoundary/, "Pipeline must preserve loading, refresh, and error states");
assert.match(pageSource, /ops-pipeline-control-strip[\s\S]*ops-pipeline-board[\s\S]*ops-pipeline-inspector/, "Control strip, Pipeline Composition, and Stage Inspector must define the primary hierarchy");
assert.match(pageSource, /ops-pipeline-studio-grid[\s\S]*ops-pipeline-board[\s\S]*ops-pipeline-inspector/, "Desktop must compose Pipeline Composition and Stage Focus Rail in one studio grid");
assert.match(pageSource, /active_backlog[\s\S]*attention_items[\s\S]*running/, "Control strip must keep the three decision-oriented point-in-time metrics");
assert.doesNotMatch(pageSource, /\["active_backlog", "attention_items", "running", "ready_downstream"\]/, "Control strip must not repeat downstream readiness outside the stage chart");
assert.match(pageSource, /function PipelineMetricIcon[\s\S]*attention_items[\s\S]*running/, "Control metrics must use dedicated semantic icons");
assert.match(pageSource, /PipelineClockIcon[\s\S]*ops-pipeline-control-strip__time/, "Snapshot freshness must include a compact clock icon");
assert.match(pageSource, /metric\.value > 0[\s\S]*has-value/, "Activity effects must be gated by real metric values");
assert.doesNotMatch(pageSource, /byKey\.get\("published"\)|metric\.key === "published"/, "Lifetime Published must not be compared with point-in-time metrics");

assert.match(pageSource, /function PipelineFlowMap/, "Pipeline must render a dedicated visual flow map");
assert.match(pageSource, /ops-pipeline-composition__node-state[\s\S]*ops-pipeline-composition__track[\s\S]*ops-pipeline-composition__segment/, "Each stage node must expose status and a stacked workload strip");
assert.match(pageSource, /PIPELINE_GROUPS[\s\S]*intake[\s\S]*production[\s\S]*delivery/, "The 13 stages must be grouped into Intake, Production, and Delivery");
assert.match(pageSource, /stage\.waiting_count[\s\S]*stage\.running_count[\s\S]*stage\.review_count[\s\S]*stage\.failed_count[\s\S]*stage\.ready_count/, "Board cells must read canonical stage buckets");
assert.match(pageSource, /value \/ stage\.total_count/, "Stacked segments must use the stage total as their composition denominator");
assert.match(pageSource, /stage\.total_count > 0[\s\S]*noWorkload/, "Zero-workload stages must render an explicit empty state");
assert.match(pageSource, /selectedStageKey[\s\S]*setSelectedStageKey/, "Selecting a stage must update the Stage Inspector locally");
assert.match(pageSource, /aria-pressed=\{selected\}/, "Stage selection must expose its current state to assistive technology");
assert.match(pageSource, /function BottleneckSpotlight[\s\S]*featured[\s\S]*remaining/, "Pipeline must promote the largest bottleneck into a visual spotlight");
assert.match(pageSource, /function OutputQaGauge[\s\S]*conic-gradient[\s\S]*summary\.total|function OutputQaGauge[\s\S]*summary\.total[\s\S]*conic-gradient/, "Output QA must render as a canonical gauge distribution");
assert.match(pageSource, /href="\/production\/output-review"/, "Output QA chart must link to the operator review authority");
assert.match(pageSource, /function ActionDeck[\s\S]*ops-pipeline-action-deck__card/, "Exceptions must render as a compact action deck");
assert.match(pageSource, /ACTION_DECK_LIMIT\s*=\s*3[\s\S]*items\.slice\(0, ACTION_DECK_LIMIT\)[\s\S]*item\.recommended_action/, "Action Deck must show three action-oriented priorities instead of duplicating every bottleneck");
assert.match(pageSource, /function ActivityPulse[\s\S]*clusterActivity/, "Recent events must render as a clustered activity pulse");
assert.match(pageSource, /JSON\.stringify\(\[item\.stage_key, item\.title, item\.detail, item\.href\]\)/, "Activity clustering must only combine fully equivalent event signals");
assert.match(pageSource, /ACTIVITY_CLUSTER_WINDOW_MS\s*=\s*2 \* 60 \* 1000[\s\S]*withinClusterWindow/, "Equivalent activity signals must only cluster inside the two-minute time window");
assert.match(pageSource, /time\(earliest\) === time\(latest\)[\s\S]*formatCompactActivityTime/, "Activity ranges within the same displayed minute must collapse to one timestamp");
assert.match(pageSource, /activity-pulse__summary[\s\S]*stageKeyLabel\(stageKey, t\)/, "Activity summary icons must keep visible stage labels");

assert.doesNotMatch(pageSource, /TRIAGE_LINKS/, "Toolbar must not keep a second hardcoded quick-link authority");
assert.doesNotMatch(pageSource, /\/ops\/publish-health|\/ops\/publish-attempts|\/ops\/reconciliation/, "Operator page must not deep-link Ops Console surfaces");
assert.match(pageSource, /EXCEPTION_LIMIT[\s\S]*slice\(0, EXCEPTION_LIMIT\)/, "Exception Queue must stay bounded");
assert.match(pageSource, /recent_activity/, "Recent Activity must remain visible");
assert.match(pageSource, /stage\.href|item\.href|row\.href/, "Board and lists must preserve authority deep links");
assert.match(pageSource, /PipelineOpenIcon|ops-pipeline-open-icon/, "Compact open actions must keep an icon");
assert.match(pageSource, /aria-label=\{label\}/, "Icon-only open actions must have an accessible label");
assert.match(pageSource, /ops-pipeline-control-strip__beacon/, "Control status must have a dedicated semantic beacon");
assert.match(pageSource, /ops-pipeline-stage-marker/, "Stages must have compact ordinal markers for scanability");
assert.doesNotMatch(pageSource, /cookie|secret|token/i, "Pipeline UI must not expose sensitive data");

assert.doesNotMatch(pageSource, /ops-pipeline-kpi|PipelineKpi/, "Pipeline must not reuse Home-style KPI cards");
assert.doesNotMatch(pageSource, /ops-pipeline-workload-map|WorkloadMap/, "Pipeline must not reuse Home's Workload Map composition");
assert.doesNotMatch(pageSource, /ops-pipeline-attention-chart|AttentionByStage/, "Pipeline must not reuse Home's Attention chart");

assert.match(globalCssSource, /\.ops-pipeline-control-strip/, "CSS must define the flat control strip");
assert.match(globalCssSource, /\.ops-pipeline-control-strip__metric-icon/, "CSS must define visual KPI icon tiles");
assert.match(globalCssSource, /@keyframes ops-pipeline-control-reveal[\s\S]*@keyframes ops-pipeline-control-item-reveal[\s\S]*@keyframes ops-pipeline-beacon-pulse/, "Control strip must define restrained entrance and status motion");
assert.match(globalCssSource, /\.is-running\.has-value[\s\S]*ops-pipeline-running-ripple/, "Running motion must only appear for active work");
assert.match(globalCssSource, /@media \(prefers-reduced-motion: reduce\)[\s\S]*ops-pipeline-control-strip/, "Control strip motion must respect reduced-motion preferences");
assert.match(globalCssSource, /\.ops-pipeline-studio-grid\s*\{[\s\S]*?grid-template-columns:\s*minmax\(0,\s*2fr\)\s+minmax\(18rem,\s*0\.72fr\)/, "Desktop Studio must use an approximately 70/30 Board-to-Focus split");
assert.match(globalCssSource, /\.ops-pipeline-composition__row/, "CSS must define composition chart stage rows");
assert.match(globalCssSource, /\.ops-pipeline-composition__row:not\(:last-child\)::after[\s\S]*\.ops-pipeline-composition__row:not\(:last-child\)::before/, "Stage nodes must use directional connectors");
assert.match(globalCssSource, /\.ops-pipeline-composition__segment\.is-running[\s\S]*\.is-review[\s\S]*\.is-failed[\s\S]*\.is-ready/, "CSS must use stable semantic colors for stacked status segments");
assert.match(globalCssSource, /\.ops-pipeline-analytics-grid/, "CSS must define a dedicated analytics row");
assert.match(globalCssSource, /\.ops-pipeline-bottleneck-spotlight__hero/, "CSS must define the bottleneck spotlight");
assert.match(pageSource, /ops-pipeline-visual-head__title/, "Visual panel titles must use a dedicated wrapper instead of overriding icon spans");
assert.doesNotMatch(globalCssSource, /\.ops-pipeline-visual-head > div > span\s*\{/, "Visual header selectors must not force every icon span into text layout");
assert.match(globalCssSource, /\.ops-pipeline-panel-glyph,[\s\S]*place-items:\s*center/, "Panel glyph boxes must center their SVG content");
assert.match(globalCssSource, /\.ops-pipeline-qa-gauge__ring/, "CSS must define the Output QA gauge");
assert.match(globalCssSource, /\.ops-pipeline-qa-gauge\.is-empty[\s\S]*min-height:\s*6\.1rem/, "Empty Output QA must collapse into a compact status card");
assert.match(globalCssSource, /\.ops-pipeline-action-deck__grid/, "CSS must define the action tile grid");
assert.match(globalCssSource, /\.ops-pipeline-activity-pulse__summary/, "CSS must define the compact activity summary");
assert.match(globalCssSource, /\.ops-pipeline-inspector/, "CSS must define the selected-stage inspector");
assert.match(globalCssSource, /\.ops-pipeline-inspector\s*\{[^}]*position:\s*sticky[^}]*top:/, "Stage Focus Rail must stay visible beside the board on desktop");
assert.match(globalCssSource, /\.ops-pipeline-lower-grid\s*\{[^}]*align-items:\s*stretch/, "Lower panels must balance their heights instead of leaving a large blank column");
assert.match(globalCssSource, /\.ops-pipeline-flat-section\s*\{[^}]*border:[^}]*border-radius:[^}]*background:\s*#fff/, "Lower sections must render as independent polished panels");
assert.match(globalCssSource, /\.ops-pipeline-event-tape/, "CSS must define the Event Tape");
assert.match(globalCssSource, /@media \(max-width: 900px\)[\s\S]*ops-pipeline-analytics-grid[\s\S]*ops-pipeline-lower-grid/, "Analytics and operations layouts must collapse on narrower screens");
assert.match(globalCssSource, /@media \(max-width: 1100px\)[\s\S]*ops-pipeline-studio-grid[\s\S]*grid-template-columns:\s*1fr[\s\S]*ops-pipeline-inspector[\s\S]*position:\s*static/, "Stage Focus Rail must move below the board on narrower screens");
assert.match(globalCssSource, /@media \(max-width: 640px\)[\s\S]*ops-pipeline-action-deck__grid\s*\{\s*grid-template-columns:\s*minmax\(0,\s*1fr\)/, "Action Deck must collapse without widening the mobile document");

assert.doesNotThrow(() => JSON.parse(en), "English translations must stay valid JSON");
assert.doesNotThrow(() => JSON.parse(vi), "Vietnamese translations must stay valid JSON");
assert.match(en, /"pipelineComposition"[\s\S]*"bottlenecks"[\s\S]*"stageInspector"[\s\S]*"exceptionQueue"[\s\S]*"eventTape"/, "English chart and operations labels must exist");
assert.match(vi, /"pipelineComposition"[\s\S]*"bottlenecks"[\s\S]*"stageInspector"[\s\S]*"exceptionQueue"[\s\S]*"eventTape"/, "Vietnamese chart and operations labels must exist");
assert.match(pkg, /reup-pipeline-dashboard\.test\.ts/, "Web test script must run Pipeline contract checks");

console.log("reup pipeline dashboard visualization tests passed");
