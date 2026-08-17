import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import {
  parseFinalReviewActionStatus,
  shouldAutoDismissFinalReviewActionStatus
} from "../lib/finalReviewState";

const testDir = dirname(fileURLToPath(import.meta.url));
const statusSource = readFileSync(
  resolve(testDir, "../components/final-review/FinalReviewActionStatus.tsx"),
  "utf8"
);
const cssSource = readFileSync(resolve(testDir, "../app/globals.css"), "utf8");

const visualCleanFailed =
  "Visual Clean preview failed: Adaptive Phase 4 preflight execution failed: RenderPolicyError: Sparse ui geometry exceeds automatic safety limits [transient · retries exhausted · needs manual check].";

const parsed = parseFinalReviewActionStatus("error", visualCleanFailed);
assert.equal(parsed.title, "Visual Clean preview failed");
assert.equal(parsed.detail, "Sparse ui geometry exceeds automatic safety limits");
assert.deepEqual(parsed.flags, ["transient", "retries exhausted", "needs manual check"]);
assert.doesNotMatch(parsed.detail, /RenderPolicyError|preflight|Adaptive Phase 4/);
assert.doesNotMatch(parsed.title ?? "", /RenderPolicyError/);

const renderPrep = parseFinalReviewActionStatus(
  "error",
  "Render failed: missing_render_prep_manifest: Current render-prep manifest is missing"
);
assert.equal(renderPrep.title, "Render failed");
assert.equal(renderPrep.detail, "Current render-prep manifest is missing");
assert.deepEqual(renderPrep.flags, []);

const success = parseFinalReviewActionStatus("success", "Visual Clean preview ready.");
assert.equal(success.title, null);
assert.equal(success.detail, "Visual Clean preview ready.");
assert.deepEqual(success.flags, []);

const plainError = parseFinalReviewActionStatus("error", "Visual Clean preview failed");
assert.equal(plainError.title, null);
assert.equal(plainError.detail, "Visual Clean preview failed");

assert.match(
  statusSource,
  /parseFinalReviewActionStatus/,
  "Action status strip must parse operator messages at the shared helper"
);
assert.match(
  statusSource,
  /fr-action-status__flags/,
  "Error notices with recovery flags must render as chips, not inline dump text"
);
assert.match(
  statusSource,
  /fr-action-status__flag/,
  "Each recovery flag must be its own chip"
);
assert.match(
  cssSource,
  /\.fr-action-status__message-title[\s\S]{0,120}display:\s*block/,
  "Error title must stack above the reason instead of flowing as one log line"
);
assert.match(
  cssSource,
  /\.fr-action-status__flags[\s\S]{0,160}display:\s*flex/,
  "Recovery flags must lay out as a chip row"
);
assert.match(
  cssSource,
  /\.fr-action-status__flag[\s\S]{0,180}border-radius:\s*999px/,
  "Flag chips must use the operator pill shape"
);
assert.equal(shouldAutoDismissFinalReviewActionStatus("success"), true);
assert.equal(shouldAutoDismissFinalReviewActionStatus("warning"), true);
assert.equal(shouldAutoDismissFinalReviewActionStatus("error"), false);
assert.equal(shouldAutoDismissFinalReviewActionStatus("queued"), false);
assert.equal(shouldAutoDismissFinalReviewActionStatus("running"), false);

assert.match(
  statusSource,
  /shouldAutoDismissFinalReviewActionStatus/,
  "Status strip must use the shared auto-dismiss gate so errors stay for diagnosis"
);

const pageSource = readFileSync(
  resolve(testDir, "../components/final-review/FinalReviewPage.tsx"),
  "utf8"
);
assert.doesNotMatch(
  pageSource,
  /visualCleanFailed[\s\S]{0,400}setError\(message\)/,
  "Visual Clean job failures must not also dump the exception chain into page inline-error"
);
assert.doesNotMatch(
  statusSource,
  /cookie|secret|token/i,
  "Status parser wiring must not introduce secret-bearing copy"
);
