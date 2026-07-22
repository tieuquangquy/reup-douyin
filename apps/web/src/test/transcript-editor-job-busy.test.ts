import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { pollAnalyzeJobUntilSettled } from "../lib/transcriptEditorReanalyze";

const testDir = dirname(fileURLToPath(import.meta.url));
const bannerSource = readFileSync(
  resolve(testDir, "../components/transcript-editor/TranscriptJobBusyBanner.tsx"),
  "utf8"
);
const pageSource = readFileSync(
  resolve(testDir, "../components/transcript-editor/TranscriptEditorPage.tsx"),
  "utf8"
);
const noticeSource = readFileSync(
  resolve(testDir, "../components/transcript-editor/TranscriptInlineNotice.tsx"),
  "utf8"
);
const headerSource = readFileSync(
  resolve(testDir, "../components/transcript-editor/TranscriptEditorHeader.tsx"),
  "utf8"
);
const apiSource = readFileSync(resolve(testDir, "../lib/api.ts"), "utf8");
const enSource = readFileSync(resolve(testDir, "../lib/i18n/en.json"), "utf8");
const viSource = readFileSync(resolve(testDir, "../lib/i18n/vi.json"), "utf8");
const cssSource = readFileSync(resolve(testDir, "../app/globals.css"), "utf8");

assert.match(bannerSource, /role="status"/, "Busy banner must expose status role");
assert.match(bannerSource, /transcript-job-busy/, "Busy banner must use dedicated class");
assert.match(bannerSource, /progressPercent|progress_percent|%\s*\}/, "Busy banner must show loading percent");
assert.match(bannerSource, /transcript-job-busy__cancel/, "Cancel must use dedicated button class");
assert.match(bannerSource, /CancelIcon|function CancelIcon/, "Cancel must show icon + text");
assert.match(bannerSource, /tts|translate|reanalyze/i, "Busy banner must cover job kinds");

assert.match(pageSource, /TranscriptJobBusyBanner/, "Page must render shared job busy banner");
assert.match(pageSource, /transcript-job-strip/, "Job banner strip must separate from sticky header");
assert.match(pageSource, /is-job-busy|transcript-bench.*busy/, "Bench must soft-dim while job runs");
assert.match(pageSource, /cancelJob/, "Page must cancel running transcript jobs");
assert.match(pageSource, /progressPercent|jobProgress/, "Page must track job progress percent");
assert.match(pageSource, /TranscriptInlineNotice|inline-success|successMessage|jobSuccess/, "Page must show success notice after job completes");
assert.match(pageSource, /TRANSCRIPT_SUCCESS_NOTICE_AUTO_DISMISS_MS|tone=\"success\"[\s\S]*autoDismissMs/, "Success notice must auto-dismiss");
assert.match(pageSource, /setSuccessMessage\(null\)/, "Success notice must clear on dismiss");
assert.match(pageSource, /tone=\"cancelled\"|cancelledMessage/, "Page must show styled cancelled notice");
assert.match(pageSource, /TRANSCRIPT_CANCELLED_NOTICE_AUTO_DISMISS_MS|autoDismissMs/, "Cancelled notice must auto-dismiss");
assert.match(pageSource, /setCancelledMessage\(null\)/, "Cancelled notice must clear on dismiss");
assert.match(noticeSource, /transcript-inline-notice__dismiss/, "Notice must expose dismiss button");
assert.match(noticeSource, /autoDismissMs/, "Notice component must support auto-dismiss timer");
assert.match(noticeSource, /TRANSCRIPT_SUCCESS_NOTICE_AUTO_DISMISS_MS/, "Notice must export success auto-dismiss constant");
assert.match(cssSource, /transcript-job-strip/, "Job banner must sit in separated strip from header");

assert.match(headerSource, /AsyncButton[\s\S]*pending=/, "Active command buttons must show pending feedback while running");
assert.match(apiSource, /export async function cancelJob/, "API must expose cancelJob");

{
  const percents: number[] = [];
  const result = await pollAnalyzeJobUntilSettled({
    fetchStatus: async () => ({
      status: "RUNNING",
      progress_percent: 42,
      error_message: null,
      error_code: null
    }),
    onSnapshot: (snap) => {
      if (typeof snap.progress_percent === "number") percents.push(snap.progress_percent);
    },
    shouldStop: () => percents.length >= 1,
    sleep: async () => undefined,
    intervalMs: 1,
    maxAttempts: 5
  });
  assert.equal(result.outcome, "cancelled");
  assert.ok(percents.includes(42));
}

{
  const result = await pollAnalyzeJobUntilSettled({
    fetchStatus: async () => ({ status: "CANCELLED", progress_percent: 30, error_message: null, error_code: null }),
    sleep: async () => undefined,
    intervalMs: 1,
    maxAttempts: 5
  });
  assert.equal(result.outcome, "cancelled");
}

const en = JSON.parse(enSource) as {
  transcriptEditorJobBusy: {
    titleTts: string;
    titleTranslate: string;
    titleReanalyze: string;
    hint: string;
    cancel: string;
    cancelling: string;
  };
};
const vi = JSON.parse(viSource) as {
  transcriptEditorJobBusy: {
    titleTts: string;
    cancel: string;
    cancelling: string;
    hint: string;
  };
};

assert.ok(en.transcriptEditorJobBusy.titleTts.length > 0);
assert.ok(en.transcriptEditorJobBusy.cancel.length > 0);
assert.ok(en.transcriptEditorJobBusy.cancelling.length > 0);
assert.ok(vi.transcriptEditorJobBusy.cancel.length > 0);
assert.ok((JSON.parse(enSource) as { transcriptEditorPage: { ttsSuccess: string } }).transcriptEditorPage.ttsSuccess.length > 0);
assert.ok((JSON.parse(viSource) as { transcriptEditorPage: { ttsSuccess: string } }).transcriptEditorPage.ttsSuccess.length > 0);

assert.match(cssSource, /\.transcript-job-busy/, "globals must style job busy banner");
assert.match(cssSource, /\.transcript-bench\.is-job-busy/, "globals must soft-dim bench when busy");
assert.match(cssSource, /transcript-job-busy__cancel/, "globals must style cancel button");
assert.match(cssSource, /transcript-inline-notice__dismiss/, "globals must style notice dismiss button");
assert.match(
  cssSource,
  /\.transcript-inline-notice\.is-cancelled[\s\S]*?(?:#fffbeb|#f79009|#9a6700)/,
  "Cancelled notice must use soft warning palette"
);
assert.match(
  cssSource,
  /\.transcript-inline-notice\.is-cancelled[\s\S]*?padding:\s*7px/,
  "Cancelled notice must be vertically compact"
);
assert.doesNotMatch(
  cssSource,
  /\.transcript-inline-notice\.is-cancelled[\s\S]*?max-width:\s*min\(28rem/,
  "Cancelled notice must stay full width horizontally"
);
assert.match(
  cssSource,
  /\.transcript-inline-notice\.is-success[\s\S]*?(?:#ecfdf3|#12b76a|#067647)/,
  "Success notice must use soft green palette"
);
assert.match(
  cssSource,
  /\.transcript-inline-notice\.is-success[\s\S]*?padding:\s*7px/,
  "Success notice must be vertically compact"
);

console.log("transcript-editor job busy tests passed");
