#!/usr/bin/env node
import { execFileSync } from "node:child_process";
import { existsSync, readFileSync } from "node:fs";
import path from "node:path";
import process from "node:process";

const repoRoot = process.cwd();
const targetFile = "apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts";
const targetPath = path.join(repoRoot, targetFile);
const assertionMethods = ["equal", "deepEqual", "notEqual", "ok", "match", "doesNotMatch", "throws"];
const assertionPattern = new RegExp(`\\bassert\\.(${assertionMethods.join("|")})\\s*\\(`, "g");
const ignoreMarker = "assertion-message-ignore";

const requiredMessageRegions = [
  { label: "safe-batch contracts", start: "const safeBatchStorage = new MemoryStorage();", end: "const lockReadTimeStorage = new MemoryStorage();" },
  { label: "start/resume dispatch contracts", start: "const startCollectingSafeBatchStorage = new MemoryStorage();", end: "const backendCapturedFilterStorage = new MemoryStorage();" },
  { label: "backend filtering gates", start: "const backendCapturedFilterStorage = new MemoryStorage();", end: "const resumeSafeBatchStorage = new MemoryStorage();" },
  { label: "resume checkpoint contracts", start: "const resumedHarvest = await resumeHarvest", end: "const guarded = guardCanonicalHarvestPayload" },
  { label: "reset/fix-stuck invariants", start: "const beforeResetIdleCollectJob = await readWholeProfileHarvestState(storage);", end: "const newProfileResetStorage = new MemoryStorage();" }
];

function usageError(message) {
  console.error(`usage error: ${message}`);
  process.exit(2);
}

if (!existsSync(targetPath)) {
  usageError(`target file not found: ${targetFile}`);
}

const rawArgs = process.argv.slice(2);
const args = new Set(rawArgs);
const modeArg = rawArgs.find((arg) => arg.startsWith("--mode="));
const mode = modeArg ? modeArg.slice("--mode=".length) : process.env.EXTENSION_TEST_ASSERTIONS_MODE ?? "soft";
const allowedModes = new Set(["warn", "soft", "strict"]);
if (!allowedModes.has(mode)) {
  usageError(`unsupported mode \"${mode}\"; expected one of: warn, soft, strict`);
}
const checkScope = args.has("--check-scope") || process.env.CHECK_EXTENSION_TEST_ASSERTIONS_SCOPE === "1";
const source = readFileSync(targetPath, "utf8");
const lines = source.split(/\r?\n/);

function lineNumberAt(index) {
  let line = 1;
  for (let i = 0; i < index; i += 1) {
    if (source.charCodeAt(i) === 10) line += 1;
  }
  return line;
}

function findClosingParen(openParenIndex) {
  let depth = 0;
  let quote = null;
  let escaped = false;
  let templateExpressionDepth = 0;
  for (let i = openParenIndex; i < source.length; i += 1) {
    const char = source[i];
    const next = source[i + 1];

    if (quote) {
      if (escaped) {
        escaped = false;
        continue;
      }
      if (char === "\\") {
        escaped = true;
        continue;
      }
      if (quote === "`" && char === "$" && next === "{") {
        templateExpressionDepth += 1;
        i += 1;
        continue;
      }
      if (quote === "`" && templateExpressionDepth > 0) {
        if (char === "{") templateExpressionDepth += 1;
        if (char === "}") templateExpressionDepth -= 1;
        continue;
      }
      if (char === quote) quote = null;
      continue;
    }

    if (char === '"' || char === "'" || char === "`") {
      quote = char;
      continue;
    }
    if (char === "/" && next !== "/" && next !== "*") {
      const previous = source.slice(0, i).trimEnd().at(-1);
      if (!previous || "(,[=:!?.".includes(previous)) {
        i += 1;
        let regexEscaped = false;
        for (; i < source.length; i += 1) {
          const regexChar = source[i];
          if (regexEscaped) {
            regexEscaped = false;
            continue;
          }
          if (regexChar === "\\") {
            regexEscaped = true;
            continue;
          }
          if (regexChar === "/") break;
        }
        continue;
      }
    }
    if (char === "/" && next === "/") {
      const newline = source.indexOf("\n", i + 2);
      i = newline === -1 ? source.length : newline;
      continue;
    }
    if (char === "/" && next === "*") {
      const close = source.indexOf("*/", i + 2);
      i = close === -1 ? source.length : close + 1;
      continue;
    }
    if (char === "(") depth += 1;
    if (char === ")") {
      depth -= 1;
      if (depth === 0) return i;
    }
  }
  return -1;
}

function splitTopLevelArgs(argumentSource) {
  const args = [];
  let current = "";
  let paren = 0;
  let brace = 0;
  let bracket = 0;
  let quote = null;
  let escaped = false;

  for (let i = 0; i < argumentSource.length; i += 1) {
    const char = argumentSource[i];
    const next = argumentSource[i + 1];

    if (quote) {
      current += char;
      if (escaped) {
        escaped = false;
        continue;
      }
      if (char === "\\") {
        escaped = true;
        continue;
      }
      if (char === quote) quote = null;
      continue;
    }

    if (char === '"' || char === "'" || char === "`") {
      quote = char;
      current += char;
      continue;
    }
    if (char === "/" && next === "/") {
      const newline = argumentSource.indexOf("\n", i + 2);
      current += newline === -1 ? argumentSource.slice(i) : argumentSource.slice(i, newline);
      i = newline === -1 ? argumentSource.length : newline - 1;
      continue;
    }
    if (char === "/" && next === "*") {
      const close = argumentSource.indexOf("*/", i + 2);
      current += close === -1 ? argumentSource.slice(i) : argumentSource.slice(i, close + 2);
      i = close === -1 ? argumentSource.length : close + 1;
      continue;
    }

    if (char === "(") paren += 1;
    if (char === ")") paren -= 1;
    if (char === "{") brace += 1;
    if (char === "}") brace -= 1;
    if (char === "[") bracket += 1;
    if (char === "]") bracket -= 1;

    if (char === "," && paren === 0 && brace === 0 && bracket === 0) {
      args.push(current.trim());
      current = "";
      continue;
    }

    current += char;
  }

  if (current.trim().length > 0) args.push(current.trim());
  return args;
}

function hasMessageArg(callSource) {
  if (callSource.includes(ignoreMarker)) return true;
  const openParen = callSource.indexOf("(");
  const closeParen = callSource.lastIndexOf(")");
  if (openParen === -1 || closeParen === -1 || closeParen <= openParen) return false;
  const args = splitTopLevelArgs(callSource.slice(openParen + 1, closeParen));
  const lastArg = args.at(-1)?.trim() ?? "";
  return /^(["'`])/.test(lastArg);
}

function requiredRegionForLine(lineNumber) {
  for (const region of requiredMessageRegions) {
    const startLine = lines.findIndex((line) => line.includes(region.start)) + 1;
    const endLine = lines.findIndex((line, index) => index + 1 > startLine && line.includes(region.end)) + 1;
    if (startLine > 0 && endLine > startLine && lineNumber >= startLine && lineNumber < endLine) return region.label;
  }
  return null;
}

function normalizeStatement(statement) {
  return statement.replace(/\s+/g, " ").trim();
}

const missingMessages = [];
const duplicateWarnings = [];
const seenAssertions = new Map();
const allAssertions = [];

for (const match of source.matchAll(assertionPattern)) {
  const openParenIndex = source.indexOf("(", match.index);
  const closeParenIndex = findClosingParen(openParenIndex);
  if (closeParenIndex === -1) {
    usageError(`could not parse assertion starting at ${targetFile}:${lineNumberAt(match.index)}`);
  }
  const statementEnd = source[closeParenIndex + 1] === ";" ? closeParenIndex + 2 : closeParenIndex + 1;
  const statement = source.slice(match.index, statementEnd);
  const line = lineNumberAt(match.index);
  const method = match[1];
  const region = requiredRegionForLine(line);
  allAssertions.push({ line, method, statement, region });

  if (region && !hasMessageArg(statement)) {
    missingMessages.push({ line, method, region, statement: statement.split(/\r?\n/)[0].trim() });
  }

  const normalized = normalizeStatement(statement);
  const previous = seenAssertions.get(normalized);
  if (previous) {
    duplicateWarnings.push({ line, previousLine: previous.line, statement: statement.split(/\r?\n/)[0].trim() });
  } else {
    seenAssertions.set(normalized, { line });
  }
}

const scopeWarnings = [];
if (checkScope) {
  const allowed = new Set([
    targetFile,
    "scripts/check-extension-test-assertions.mjs",
    "package.json",
    "apps/extension-douyin-capture/package.json"
  ]);
  try {
    const changed = execFileSync("git", ["diff", "--name-only", "HEAD", "--"], { cwd: repoRoot, encoding: "utf8" })
      .split(/\r?\n/)
      .map((entry) => entry.trim().replace(/\\/g, "/"))
      .filter(Boolean);
    for (const file of changed) {
      if (!allowed.has(file)) scopeWarnings.push({ file });
    }
  } catch (error) {
    scopeWarnings.push({ file: `scope check skipped: ${error instanceof Error ? error.message : String(error)}` });
  }
}

const blockingIssues = {
  warn: 0,
  soft: missingMessages.length,
  strict: missingMessages.length + duplicateWarnings.length
};

console.log("Extension assertion guardrails");
console.log(`Target: ${targetFile}`);
console.log(`Mode: ${mode}`);
console.log(`Assertions scanned: ${allAssertions.length}`);
console.log(`Missing required messages: ${missingMessages.length}`);
console.log(`Duplicate assertion warnings: ${duplicateWarnings.length}`);
console.log(`Scope warnings: ${scopeWarnings.length}`);

if (missingMessages.length > 0) {
  console.log("\nMissing assertion messages:");
  for (const entry of missingMessages) {
    console.log(`- ${targetFile}:${entry.line} [${entry.region}] assert.${entry.method} is missing a final message argument`);
  }
}

if (duplicateWarnings.length > 0) {
  console.log("\nDuplicate assertion warnings:");
  for (const entry of duplicateWarnings) {
    console.log(`- ${targetFile}:${entry.line} duplicates ${targetFile}:${entry.previousLine}`);
  }
}

if (scopeWarnings.length > 0) {
  console.log("\nScope warnings:");
  for (const entry of scopeWarnings) console.log(`- ${entry.file}`);
}

if (blockingIssues[mode] > 0) {
  if (mode === "strict" && duplicateWarnings.length > 0 && missingMessages.length === 0) {
    console.log("\nFAIL: strict assertion guardrails blocked duplicate assertion warnings");
  } else {
    console.log(`\nFAIL: ${mode} assertion guardrails found blocking violations`);
  }
  process.exit(1);
}

if (mode === "warn" && (missingMessages.length > 0 || duplicateWarnings.length > 0 || scopeWarnings.length > 0)) {
  console.log("\nWARN: assertion guardrails reported non-blocking findings");
  process.exit(0);
}

console.log(`\nPASS: ${mode} assertion guardrails passed`);
