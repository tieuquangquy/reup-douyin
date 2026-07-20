/**
 * App shell content horizontal inset must be a single 24px token shared with the topbar.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const testDir = dirname(fileURLToPath(import.meta.url));
const css = readFileSync(resolve(testDir, "../app/globals.css"), "utf8");

assert.match(
  css,
  /:root\s*\{[^}]*--app-content-inset-x:\s*24px;/,
  "globals must define --app-content-inset-x: 24px on :root"
);

assert.match(
  css,
  /\.app-topbar\s*\{[^}]*padding:\s*18px\s+var\(--app-content-inset-x\)/,
  "Topbar horizontal padding must use --app-content-inset-x"
);

assert.match(
  css,
  /\.ops-console-page\s*\{[^}]*padding:[^;]*var\(--app-content-inset-x\)/,
  "Ops console page gutter must use inset token"
);

assert.match(
  css,
  /\.ops-page--settings\s*\{[^}]*padding:[^;]*var\(--app-content-inset-x\)/,
  "Ops settings pages must use inset token"
);

assert.match(
  css,
  /\.operator-home\s*\{[^}]*padding:[^;]*var\(--app-content-inset-x\)/,
  "Operator home must use inset token"
);

assert.match(
  css,
  /\.ops-jobs-monitor\.is-compact\s*\{[^}]*padding:[^;]*var\(--app-content-inset-x\)/,
  "Jobs monitor compact must use inset token"
);

assert.match(
  css,
  /\.transcript-bench\s*\{[^}]*padding:[^;]*var\(--app-content-inset-x\)|\.transcript-bench\s*\{[^}]*padding-inline:\s*var\(--app-content-inset-x\)/,
  "Transcript bench page gutter must use inset token"
);

assert.match(
  css,
  /\.final-review-layout\s*\{[^}]*padding:[^;]*var\(--app-content-inset-x\)|\.fr-workspace\s*\{[^}]*padding:[^;]*var\(--app-content-inset-x\)/,
  "Final review page gutter must use inset token"
);

// Ops triage roots must not keep the old 1.25rem horizontal gutter as page inset.
assert.doesNotMatch(
  css,
  /\.ops-home-page\s*\{[^}]*padding:\s*1rem 1\.25rem/,
  "ops-home-page must leave 1.25rem horizontal inset"
);

console.log("app-content-inset tests passed");
