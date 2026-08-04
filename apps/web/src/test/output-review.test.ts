import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

import {
  isOutputReviewItem,
  outputReviewCounts,
  outputReviewFixTarget,
  outputReviewQueue,
  parseRenderQaVerdict,
  renderQaBadgeLabel,
  renderQaBadgeTone
} from "../lib/outputReview";
import type { ReupQueueItem } from "../types/reup-queue";

function item(overrides: Partial<ReupQueueItem> & { id: string }): ReupQueueItem {
  return {
    workspace_id: "ws",
    video_candidate_id: "cand",
    source_video_id: `src-${overrides.id}`,
    status: "WAITING_FOR_METADATA",
    bucket: "processing",
    next_action: "review",
    priority: 100,
    queued_reason: null,
    operator_note: null,
    last_error_code: null,
    last_error_message: null,
    media_prep_status: "WAITING_FOR_METADATA",
    media_prep_notes: null,
    media_ready_at: null,
    blocked_reason: null,
    blocked_at: null,
    held_at: null,
    failed_at: null,
    last_action: null,
    last_action_at: null,
    last_action_note: null,
    available_actions: [],
    queued_at: null,
    started_at: null,
    completed_at: null,
    cancelled_at: null,
    operator_dismissed_at: null,
    job_id: null,
    render_output_id: null,
    publish_draft_id: null,
    metadata_json: null,
    source_video: null,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    ...overrides
  } as ReupQueueItem;
}

function withQa(id: string, status: string, extra: Record<string, unknown> = {}): ReupQueueItem {
  return item({
    id,
    render_output_id: `render-${id}`,
    metadata_json: {
      pipeline_step: "ready_final",
      render_qa: {
        status,
        summary: `${status} summary`,
        failed: status === "fail" ? ["duration_match"] : [],
        warned: status === "warn" ? ["subtitle_burned"] : [],
        checks: [{ key: "duration_match", status, detail: "detail" }],
        ...extra
      }
    }
  });
}

// Verdict parsing tolerates anything the backend has not written yet.
const passing = withQa("a", "pass");
const verdict = parseRenderQaVerdict(passing);
assert.equal(verdict?.status, "pass");
assert.equal(verdict?.summary, "pass summary");
assert.equal(verdict?.checks[0]?.key, "duration_match");

assert.equal(parseRenderQaVerdict(item({ id: "no-meta" })), null);
assert.equal(parseRenderQaVerdict(item({ id: "junk", metadata_json: { render_qa: "nope" } })), null);
assert.equal(
  parseRenderQaVerdict(item({ id: "odd", metadata_json: { render_qa: { status: "banana" } } })),
  null,
  "Unknown verdict status must not be shown as a badge"
);

// Only items with a rendered product belong on the page.
assert.equal(isOutputReviewItem(withQa("b", "warn")), true);
assert.equal(isOutputReviewItem(item({ id: "c", render_output_id: "render-c" })), true);
assert.equal(
  isOutputReviewItem(item({ id: "d", metadata_json: { pipeline_step: "ready_final" } })),
  false,
  "auto_to_tts stops at ready_final without a render — nothing to watch yet"
);

// Worst first: an operator should meet failures before clean clips.
const queue = outputReviewQueue([
  withQa("pass-1", "pass"),
  item({ id: "ungraded", render_output_id: "render-ungraded" }),
  withQa("fail-1", "fail"),
  withQa("warn-1", "warn"),
  item({ id: "not-rendered" })
]);
assert.deepEqual(
  queue.map((entry) => entry.id),
  ["fail-1", "warn-1", "ungraded", "pass-1"]
);

const counts = outputReviewCounts(queue);
assert.deepEqual(counts, { total: 4, failed: 1, warned: 1, passed: 1, ungraded: 1 });

// Badge presentation
assert.equal(renderQaBadgeTone("fail"), "critical");
assert.equal(renderQaBadgeTone("warn"), "warning");
assert.equal(renderQaBadgeTone("pass"), "positive");
assert.equal(renderQaBadgeTone(null), "neutral");
assert.equal(renderQaBadgeLabel("fail"), "QA failed");
assert.equal(renderQaBadgeLabel(null), "Not graded");

// "Fix" must land on the stage that produced the defect, not a generic details page.
{
  const dubFailure = item({
    id: "dub",
    source_video_id: "src-dub",
    render_output_id: "render-dub",
    metadata_json: {
      render_qa: { status: "fail", summary: "no audio", failed: ["dub_audio"], warned: [], checks: [] }
    }
  });
  const target = outputReviewFixTarget(dubFailure);
  assert.equal(target.href, "/production/transcript-editor/src-dub");
  assert.match(target.reason, /voice|dub/i);
}

{
  const truncated = item({
    id: "dur",
    source_video_id: "src-dur",
    render_output_id: "render-dur",
    metadata_json: {
      render_qa: { status: "fail", summary: "short", failed: ["duration_match"], warned: [], checks: [] }
    }
  });
  assert.equal(outputReviewFixTarget(truncated).href, "/production/final-review/src-dur");
}

{
  const subtitleWarn = item({
    id: "sub",
    source_video_id: "src-sub",
    render_output_id: "render-sub",
    metadata_json: {
      render_qa: { status: "warn", summary: "no subs", failed: [], warned: ["subtitle_burned"], checks: [] }
    }
  });
  assert.equal(
    outputReviewFixTarget(subtitleWarn).href,
    "/production/transcript-editor/src-sub",
    "Missing subtitles are a translation-side problem"
  );
}

{
  const clean = withQa("clean", "pass");
  const target = outputReviewFixTarget(clean);
  assert.equal(target.href, `/production/final-review/${clean.source_video_id}`);
  assert.equal(target.label, "Open full review", "A clean clip has nothing to fix");
}

// The page must exist, be a client component, and reuse shared UX primitives.
const page = readFileSync("src/components/operator-routes/OutputReviewPage.tsx", "utf8");
assert.ok(page.includes('"use client"'));
assert.ok(page.includes("OperatorStudioShell"));
assert.ok(page.includes("AsyncContentBoundary"));
assert.ok(page.includes("fetchReupQueueItems"));
assert.ok(page.includes("fetchMediaAssetObjectUrl"), "Protected media needs a blob URL, not a raw src");
assert.ok(page.includes("outputReviewQueue"));
assert.ok(page.includes("runReupQueueAction"), "Reviewer must be able to act without leaving the page");
assert.ok(page.includes("URL.revokeObjectURL"), "Blob URLs must be released when switching clips");
assert.ok(page.includes("outputReviewFixTarget"), "Fix must route by failure, not to a generic page");
assert.ok(page.includes("keydown"), "Back-to-back review needs keyboard paging");
assert.ok(/ArrowDown|"j"/.test(page), "Next clip needs a one-key shortcut");
assert.ok(page.includes("ops-output-review-summary"), "Review metrics should use one compact dashboard summary");
assert.ok(page.includes("ops-output-review-pulse__body"), "QA summary should use one unified decision surface");
assert.ok(page.includes("ops-output-review-pulse__deck"), "QA summary needs a compact command deck");
assert.ok(page.includes("ops-output-review-pulse__deck-signal"), "The deck needs one clear priority signal");
assert.ok(page.includes("ops-output-review-pulse__deck-metrics"), "Readiness metrics should stay inside the deck");
assert.ok(page.includes("ops-output-review-pulse__deck-ring"), "Pass rate needs one compact circular chart");
assert.ok(page.includes('role="img"'), "The circular chart needs accessible chart semantics");
assert.ok(page.includes('"--pass-rate": `${passRatePercentage}%`'), "The circular chart must use persisted pass-rate data");
assert.ok(page.includes("ops-output-review-pulse__deck-bars"), "Attention causes need a compact bar chart");
assert.equal((page.match(/role="progressbar"/g) ?? []).length, 2, "Only failed and warning outcomes should remain as bars");
assert.ok(page.includes("aria-valuenow={failedPercentage}"), "Failed chart width must use persisted QA data");
assert.ok(page.includes("aria-valuenow={warnedPercentage}"), "Warning chart width must use persisted QA data");
assert.doesNotMatch(page, /aria-valuenow=\{passRatePercentage\}/, "Pass rate should not be repeated as a bar");
assert.equal((page.match(/Pass rate/g) ?? []).length, 1, "Pass rate should have one visual authority");
assert.ok(page.includes("summaryCue"), "The command deck needs a state-aware operator cue");
assert.ok(page.includes("normalizedOutcomePercentages"), "Displayed outcome percentages must be normalized to exactly 100%");
assert.doesNotMatch(page, /ops-output-review-pulse__matrix/, "The rejected decision matrix must stay out of the rendered page");
assert.doesNotMatch(page, /ops-output-review-pulse__orbit/, "The rejected constellation layout must stay removed");
assert.doesNotMatch(page, /ops-output-review-pulse__tile-map/, "The rejected tile map must stay removed");
assert.doesNotMatch(page, /outcomeTiles/, "The rejected per-render tile model must stay removed");
assert.doesNotMatch(page, /ops-output-review-pulse__editorial-score/, "The rejected editorial score must stay removed");
assert.doesNotMatch(page, /ops-output-review-pulse__editorial-ledger/, "The rejected editorial ledger must stay removed");
assert.doesNotMatch(page, /SummaryDistributionDonut/, "The rejected radial-chart concept must stay removed");
assert.doesNotMatch(page, /ops-output-review-pulse__quality/, "The rejected three-zone quality pulse must stay removed");
assert.doesNotMatch(page, /ops-output-review-pulse__signal-board/, "The rejected signal board must stay removed");
assert.doesNotMatch(page, /ops-output-review-pulse__verdict-board/, "The rejected verdict spotlight must stay removed");
assert.doesNotMatch(page, /ops-output-review-pulse__mosaic/, "The rejected treemap concept must stay removed");
assert.doesNotMatch(page, /ops-output-review-pulse__skyline/, "The rejected column-chart concept must stay removed");
assert.doesNotMatch(page, /SummaryMetricVisual/, "The summary should not fall back to four template KPI cards");
assert.doesNotMatch(page, /ops-output-review-pulse__rail/, "The rejected horizontal distribution rail must stay removed");
assert.doesNotMatch(page, /ops-output-review-pulse__distribution-body/, "The breakdown should not reserve a separate donut column");
assert.ok(page.includes("Manual review pending"), "Ungraded renders must not be described as a clear queue");
assert.ok(page.includes("sourceQueueIsTruncated"), "A partial source queue must be disclosed instead of looking complete");
assert.ok(page.includes("ops-output-review-queue-panel"), "The queue needs a labelled workstation rail");
assert.ok(page.includes("ops-output-review-stage__body"), "Playback and QA should share the main review workspace");
assert.ok(page.includes("has-no-playback"), "Missing playback should switch to a compact adaptive workspace");
assert.ok(page.includes("ops-output-review-player-empty"), "Missing playback needs a designed diagnostic empty state");
assert.ok(page.includes("ops-output-review-stage__facts"), "The selected render should expose compact technical facts");
assert.ok(page.includes("resolveRenderTechSpecs"), "Render facts must use persisted render data, not guessed values");
assert.ok(page.includes("ops-output-review-inspection"), "QA checks need a dedicated inspection pane");
assert.ok(page.includes("skippedChecks"), "Skipped QA checks must remain distinct from verified checks");
assert.ok(page.includes("not measured"), "Skipped QA checks need an explicit operator-facing label");
assert.match(page, /is-verified" open/, "Verified QA checks should use available inspection space by default");
assert.ok(page.includes("source_video_external_id"), "Worklist rows need a stable source reference when captions repeat");
assert.ok(page.includes("ops-output-review-command-bar"), "Actions and clip navigation need one grouped command bar");
assert.ok(page.includes("Previous clip"), "Back-to-back review needs visible previous navigation");
assert.ok(page.includes("WorkItemActionIcon"), "Output Review actions should reuse the shared action icon system");
assert.ok(page.includes("outputReviewActionIconKind"), "Lifecycle actions need stable semantic icon mapping");
assert.ok(page.includes("leadingIcon"), "Async lifecycle buttons should render their semantic icon");
assert.ok(page.includes("ops-output-review-pager__icon"), "Previous and next controls need compact direction icons");

const route = readFileSync("src/app/production/output-review/page.tsx", "utf8");
assert.ok(route.includes("OutputReviewPage"));

const nav = readFileSync("src/lib/navigationConfig.ts", "utf8");
assert.ok(nav.includes("/production/output-review"));

const css = readFileSync("src/app/globals.css", "utf8");
assert.ok(css.includes(".ops-output-review-page"));
assert.ok(css.includes("9 / 16"), "Final clips are vertical");
assert.ok(css.includes(".ops-output-review-summary"));
assert.ok(css.includes(".ops-output-review-pulse__deck"), "The QA summary needs a dedicated command deck surface");
assert.ok(css.includes(".ops-output-review-pulse__deck-signal"), "The priority signal needs dedicated styling");
assert.ok(css.includes(".ops-output-review-pulse__deck-metrics"), "Readiness metrics need dedicated styling");
assert.ok(css.includes(".ops-output-review-pulse__deck-ring"), "The circular pass-rate chart needs dedicated styling");
assert.ok(css.includes(".ops-output-review-pulse__deck-bars"), "The outcome chart needs dedicated styling");
assert.doesNotMatch(css, /\.ops-output-review-pulse__donut/, "Rejected radial-chart styles must be removed");
assert.match(css, /\.ops-output-review-pulse__body\s*\{[^}]*display:\s*block/s, "QA summary should use one unified decision surface");
assert.match(css, /\.ops-output-review-pulse__deck\s*\{[^}]*gap:\s*0\.5rem[^}]*grid-template-columns:\s*minmax\(240px, 0\.32fr\) minmax\(0, 1\.68fr\)[^}]*min-height:\s*178px[^}]*padding:\s*0\.48rem/s, "Desktop deck should use a balanced inset composition");
assert.match(css, /\.ops-output-review-pulse__deck-bar > span\s*\{[^}]*font-size:\s*0\.8125rem/s, "Outcome labels should be at least 13px");
assert.match(css, /\.ops-output-review-pulse__deck-metrics dd > strong\s*\{[^}]*font-size:\s*1\.625rem/s, "Readiness metrics should be visually prominent");
assert.match(css, /\.ops-output-review-pulse__deck-ring\s*\{[^}]*background:\s*conic-gradient\([^;]*var\(--pass-rate\)/s, "The ring fill should be driven by the real pass-rate value");
assert.match(css, /\.ops-output-review-pulse__deck-ring\s*\{[^}]*height:\s*6\.15rem[^}]*width:\s*6\.15rem/s, "The circular chart should have a clear visual presence");
assert.match(css, /\.ops-output-review-pulse__deck-ring strong\s*\{[^}]*font-size:\s*1\.9rem/s, "Pass rate should be the strongest outcome number");
assert.match(css, /\.ops-output-review-pulse__deck-issues\s*\{[^}]*border-radius:\s*11px[^}]*max-width:\s*68rem/s, "Attention data should sit in a focused, width-controlled surface");
assert.match(css, /\.ops-output-review-pulse__deck-bar > div\s*\{[^}]*height:\s*0\.56rem/s, "Attention bars should be substantial enough to scan quickly");
assert.match(css, /\.ops-output-review-pulse__deck-bar > strong\s*\{[^}]*font-size:\s*1\.125rem/s, "Attention counts should be visually prominent");
assert.match(css, /\.ops-output-review-pulse__deck-bar > strong > small\s*\{[^}]*font-size:\s*0\.75rem/s, "Chart percentages should be at least 12px");
assert.match(css, /@media \(max-width: 680px\)[\s\S]*?\.ops-output-review-pulse__deck\s*\{[^}]*grid-template-columns:\s*1fr/s, "The deck should collapse cleanly on small screens");
assert.match(css, /@media \(max-width: 480px\)[\s\S]*?\.ops-output-review-pulse__deck-chart\s*\{[^}]*grid-template-columns:\s*1fr/s, "The circular chart should stack above bars on narrow screens");
assert.ok(css.includes(".ops-output-review-player-empty"), "The adaptive playback empty state needs dedicated styling");
assert.ok(css.includes(".ops-output-review-stage__facts"), "Render facts need a compact responsive treatment");
assert.ok(css.includes(".ops-output-review-command-bar"));

console.log("output-review tests passed");
