#!/usr/bin/env node
/**
 * Lightweight dead-symbol hints for extension popup.ts cleanup.
 * Not a proof — use with ripgrep + tests before deleting.
 */
import { readFileSync, readdirSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const popupPath = join(root, "src", "popup.ts");
const popupHtml = readFileSync(join(root, "public", "popup.html"), "utf8");
const popupSource = readFileSync(popupPath, "utf8");
const srcFiles = readdirSync(join(root, "src"), { recursive: true })
  .filter((f) => typeof f === "string" && f.endsWith(".ts"))
  .map((f) => join(root, "src", f));

const corpus = srcFiles.map((path) => readFileSync(path, "utf8")).join("\n");

const fnPattern = /(?:async\s+)?function\s+([A-Za-z0-9_]+)\s*\(/g;
const functions = new Set();
let m;
while ((m = fnPattern.exec(popupSource)) !== null) functions.add(m[1]);

const idPattern = /id="([A-Za-z0-9_-]+)"/g;
const htmlIds = new Set();
while ((m = idPattern.exec(popupHtml)) !== null) htmlIds.add(m[1]);

const suspect = [];
for (const name of [...functions].sort()) {
  const defRe = new RegExp(`(?:async\\s+)?function\\s+${name}\\s*\\(`);
  const callRe = new RegExp(`\\b${name}\\s*\\(`, "g");
  const defs = (popupSource.match(defRe) ?? []).length;
  const callsInPopup = [...popupSource.matchAll(callRe)].filter((x) => !defRe.test(x.input.slice(x.index, x.index + 40))).length;
  const callsInRepo = [...corpus.matchAll(callRe)].length - defs;
  if (callsInPopup === 0 && callsInRepo === 0) suspect.push({ name, reason: "zero call sites in src/" });
}

const domOrphans = [];
for (const id of [...htmlIds].sort()) {
  if (!popupSource.includes(`#${id}`) && !popupSource.includes(`"${id}"`)) {
    domOrphans.push(id);
  }
}

console.log("=== popup.ts functions with zero call sites (hint only) ===");
for (const row of suspect.slice(0, 40)) console.log(`  ${row.name}`);
if (suspect.length > 40) console.log(`  ... and ${suspect.length - 40} more`);

console.log("\n=== popup.html ids not referenced in popup.ts (hint only) ===");
for (const id of domOrphans.slice(0, 30)) console.log(`  #${id}`);
if (domOrphans.length > 30) console.log(`  ... and ${domOrphans.length - 30} more`);
