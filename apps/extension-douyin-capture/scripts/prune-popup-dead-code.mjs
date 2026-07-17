#!/usr/bin/env node
import { readFileSync, writeFileSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const popupPath = join(dirname(fileURLToPath(import.meta.url)), "..", "src", "popup.ts");
const raw = readFileSync(popupPath, "utf8");
const lines = raw.split(/\n/).map((line, index, all) => (index < all.length - 1 ? `${line}\n` : line));

function findLine(substr) {
  const idx = lines.findIndex((l) => l.includes(substr));
  if (idx < 0) throw new Error(`missing marker: ${substr}`);
  return idx;
}

function findFunctionEnd(startIdx) {
  let depth = 0;
  let started = false;
  for (let i = startIdx; i < lines.length; i++) {
    const line = lines[i];
    if (line.includes("function ") || line.includes("async function ")) {
      if (i === startIdx) started = true;
    }
    if (i === startIdx) started = true;
    if (!started) continue;
    for (const ch of line) {
      if (ch === "{") depth++;
      if (ch === "}") depth--;
    }
    if (started && depth === 0 && i > startIdx) return i + 1;
  }
  throw new Error(`no end for line ${startIdx + 1}`);
}

function dropFunction(marker) {
  const start = findLine(marker);
  const end = findFunctionEnd(start);
  lines.splice(start, end - start);
  console.log(`removed ${marker} (${end - start} lines)`);
}

// Delete from bottom to top so indices stay valid
dropFunction("async function startHarvestWithBinding(");
dropFunction("async function runProfileScanRequest(");
dropFunction("async function runHarvestPlanCurrentPage(");
dropFunction("function renderHarvestProgress(progress:");
dropFunction("function renderCaptureDetails(payload:");
dropFunction("function buildWholeProfileStagedEvidenceMap(");
dropFunction("async function startWholeProfileStagedHarvest(");

// Remove orphaned staged-harvest options type block
const optsIdx = lines.findIndex((l) => l.startsWith("type WholeProfileStagedHarvestOptions"));
if (optsIdx >= 0) {
  let end = optsIdx;
  while (end < lines.length && lines[end].trim() !== "};") end++;
  lines.splice(optsIdx, end - optsIdx + 1);
  console.log("removed WholeProfileStagedHarvestOptions type");
}

writeFileSync(popupPath, lines.join(""), "utf8");
console.log("new line count", lines.length);
