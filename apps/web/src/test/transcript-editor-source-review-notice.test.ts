import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const testDir = dirname(fileURLToPath(import.meta.url));
const pageSource = readFileSync(resolve(testDir, "../components/transcript-editor/TranscriptEditorPage.tsx"), "utf8");
const noticeSource = readFileSync(
  resolve(testDir, "../components/transcript-editor/TranscriptSourceReviewNotice.tsx"),
  "utf8"
);
const cssSource = readFileSync(resolve(testDir, "../app/globals.css"), "utf8");
const enSource = readFileSync(resolve(testDir, "../lib/i18n/en.json"), "utf8");

assert.match(noticeSource, /export function TranscriptSourceReviewNotice/, "Must expose a dedicated source-review callout");
assert.match(noticeSource, /transcript-source-review/, "Callout must use a stable CSS root class");
assert.match(noticeSource, /sourceApprovalTitle|sourceApprovalRequiredTitle/, "Callout must expose a short title");
assert.match(noticeSource, /sourceApprovalRequired/, "Callout must keep the ASR-reset explanation body");
assert.match(noticeSource, /approveSource/, "Callout must keep Approve source CTA");
assert.match(noticeSource, /leadingIcon/, "Approve CTA must include a leading icon");
assert.match(noticeSource, /segmentIndex|reviewSegmentIndexes/, "Callout must surface review segment indexes");
assert.match(cssSource, /\.transcript-source-review\.is-compact|\.transcript-source-review__cta\b/, "Callout must stay compact with a styled CTA");
assert.match(
  cssSource,
  /\.transcript-source-review[\s\S]{0,280}#(d97706|f59e0b|b45309|92400e|fffbeb|fef3c7)/i,
  "Source-review colors must use attention amber, matching review-required semantics"
);
assert.match(noticeSource, /role="status"|role="region"/, "Callout must be announced accessibly");
assert.doesNotMatch(noticeSource, /tone="error"|is-error/, "Source review must not reuse the error notice tone");

assert.match(pageSource, /TranscriptSourceReviewNotice/, "Transcript page must mount the dedicated source-review callout");
{
  const gateBlock = pageSource.match(/!sourceTranscriptApproved[\s\S]*?(?=\{jobBusyKind)/)?.[0] ?? "";
  assert.match(gateBlock, /TranscriptSourceReviewNotice/, "Unapproved source must render the dedicated callout");
  assert.doesNotMatch(
    gateBlock,
    /TranscriptInlineNotice\s+tone="error"/,
    "Unapproved source must not render as an error inline notice"
  );
}

assert.match(cssSource, /\.transcript-source-review\b/, "Source-review callout must have stylesheet rules");
assert.match(cssSource, /\.transcript-source-review__chip\b/, "Segment indexes must render as chips");
assert.match(enSource, /"sourceApprovalTitle"/, "EN copy must include a short source-approval title");

console.log("transcript-editor source-review notice tests passed");
