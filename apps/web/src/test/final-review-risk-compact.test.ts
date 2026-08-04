import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const testDir = dirname(fileURLToPath(import.meta.url));
const cardSource = readFileSync(resolve(testDir, "../components/risk/RiskSummaryCard.tsx"), "utf8");
const cssSource = readFileSync(resolve(testDir, "../app/globals.css"), "utf8");
const en = JSON.parse(readFileSync(resolve(testDir, "../lib/i18n/en.json"), "utf8")) as {
  riskSummary: Record<string, string>;
};
const vi = JSON.parse(readFileSync(resolve(testDir, "../lib/i18n/vi.json"), "utf8")) as {
  riskSummary: Record<string, string>;
};

assert.match(cardSource, /fr-risk/, "Risk card must use compact fr-risk layout");
assert.match(cardSource, /fr-risk__row/, "Flags must render as compact rows");
assert.match(
  cardSource,
  /fr-risk__detail|fr-risk__evidence|fr-risk__label/,
  "Flag meaning must be visible without hover"
);
assert.match(
  cardSource,
  /resolveRiskWarningLabel|riskWarnings\.|flag\.evidence_summary/,
  "Evidence/warning code must drive the visible flag label"
);
assert.match(
  cardSource,
  /OPEN|ACKNOWLEDGED|isActiveRiskFlag|activeRiskFlags/,
  "Action buttons must only show for actionable flag statuses"
);
assert.doesNotMatch(
  cardSource,
  /flagTooltip|<li[^>]*\btitle=\{/,
  "Flag meaning must not depend on title/hover tooltip as the only detail channel"
);
assert.match(cardSource, /fr-risk__decisions/, "Operator decisions must stay in a compact row");
assert.match(
  cardSource,
  /fr-risk__title-row[\s\S]*fr-risk__identity[\s\S]*fr-risk__scan|fr-risk__title-row[\s\S]*className=\"primary fr-risk__scan\"/,
  "Scan must sit on the title row beside Risk + severity badge"
);
assert.match(
  cardSource,
  /fr-risk__gate[\s\S]*fr-risk__decisions[\s\S]*fr-risk__list/,
  "Operator decisions must sit under gate and before the flag list"
);
assert.doesNotMatch(
  cardSource,
  /fr-risk__list[\s\S]*fr-risk__decisions/,
  "Decisions must not remain below the flag list"
);
assert.match(
  cardSource,
  /WorkItemActionIcon/,
  "Risk action buttons must include WorkItemActionIcon glyphs"
);
assert.match(
  cardSource,
  /kind=\"recheck\"|kind=\"retry\"/,
  "Scan button must use a refresh/recheck icon"
);
assert.match(
  cardSource,
  /fr-risk__scan[\s\S]*is-loading|className=\{`[^`]*fr-risk__scan[^`]*is-loading/,
  "Scan pending state must use is-loading class instead of swapping visible label"
);
assert.doesNotMatch(
  cardSource,
  /<span>\{\s*loading \? t\([\"']riskSummary\.scanning[\"']\)/,
  "Visible Scan label must not swap to Scanning… (causes blink/width jump)"
);
assert.match(
  cardSource,
  /<span>\{\s*t\([\"']riskSummary\.runRiskScan[\"']\)\s*\}<\/span>/,
  "Visible Scan label stays Scan while icon spins"
);
assert.match(
  cssSource,
  /\.fr-risk__scan\.is-loading[^{]*\{[^}]*animation|\.fr-risk__scan\.is-loading[\s\S]*?animation:\s*async-button-spin/,
  "Loading Scan must spin the icon smoothly"
);
assert.match(
  cardSource,
  /kind=\"approve\"/,
  "Resolve / accept decisions must use approve-style icons"
);
assert.match(
  cssSource,
  /\.fr-risk__row-actions button[\s\S]*inline-flex|\.fr-risk__scan[\s\S]*inline-flex|\.fr-risk__decisions button[\s\S]*inline-flex/,
  "Icon buttons need inline-flex alignment"
);
assert.match(
  cssSource,
  /\.fr-risk__detail|\.fr-risk__evidence|\.fr-risk__label|\.fr-risk__code/,
  "Visible flag detail styles must exist"
);
assert.match(cssSource, /\.fr-risk__row\.is-closed|\.fr-risk__row\.is-done/, "Closed flags need a muted row state");
assert.match(
  cssSource,
  /\.fr-risk__identity/,
  "Title row must cluster Risk title + severity badge"
);

assert.ok(en.riskSummary.hintShort.length > 0);
assert.ok(vi.riskSummary.hintShort.length > 0);
assert.ok(en.riskSummary.acceptWithWarning.length <= 18, "EN accept label should stay short");
assert.ok(vi.riskSummary.acceptWithWarning.length <= 16, "VI accept label should stay short");
assert.ok(
  (en as { riskWarnings?: Record<string, string> }).riskWarnings?.subtitle_lines_wrapped_for_burn,
  "EN must humanize subtitle_lines_wrapped_for_burn"
);
assert.ok(
  (vi as { riskWarnings?: Record<string, string> }).riskWarnings?.subtitle_lines_wrapped_for_burn,
  "VI must humanize subtitle_lines_wrapped_for_burn"
);

console.log("final-review risk compact tests passed");
