/** Publish Drafts index: Intelligence Queue poster spectrum + dense sheet. */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const webSrc = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const page = readFileSync(resolve(webSrc, "components/operator-routes/PublishDraftsIndexPage.tsx"), "utf8");
const cssFull = readFileSync(resolve(webSrc, "app/globals.css"), "utf8");
const en = readFileSync(resolve(webSrc, "lib/i18n/en.json"), "utf8");
const vi = readFileSync(resolve(webSrc, "lib/i18n/vi.json"), "utf8");

assert.match(page, /publish-drafts-page is-v1/, "Drafts index must mark the Intelligence worksheet");
assert.match(page, /publish-drafts-spectrum is-v7/, "Spectrum must mark the Queue poster layout");
assert.match(page, /publish-drafts-spectrum__poster/, "Spectrum must use the poster composition");
assert.match(page, /publish-drafts-spectrum__score/, "Spectrum must render proportional score rows");
assert.match(page, /publish-drafts-spectrum__track/, "Score rows must keep a visible track behind the fill");
assert.match(page, /publish-drafts-spectrum__rule/, "Spectrum must render a dominant accent rule");
assert.match(page, /is-wash-/, "Stage must apply a dominant-status wash class");
assert.match(page, /TopbarRefreshButton/, "Drafts must keep the default topbar Refresh control");
assert.match(page, /publish-drafts-spectrum__metrics/, "Spectrum must include a ticker metrics row");
assert.match(page, /publish-drafts-spectrum__metric/, "Ticker must use metric cells");
assert.match(page, /needs_attention/, "Metrics must read needs_attention authority");
assert.match(page, /warnings\.length > 0/, "Metrics must count drafts with warnings");
assert.match(page, /planned_publish_at/, "Metrics must surface next planned publish time");
assert.match(page, /accounts\.length/, "Metrics must surface accounts in the queue view");
assert.match(page, /generated_at/, "Metrics must surface queue generated_at");
assert.match(
  page,
  /legendClassName:\s*unassignedCount > 0 \? "is-unassigned is-warning" : "is-unassigned"/,
  "Unassigned warning tint must apply only to score rows when count > 0",
);
assert.match(page, /barClassName:\s*"is-unassigned"/, "Score rule fill must keep the status color class");
assert.doesNotMatch(
  page,
  /barClassName:\s*"[^"]*is-warning/,
  "Warning tint must not ride on score rule fill classes",
);
assert.match(
  page,
  /attentionCount > 0 \? "publish-drafts-spectrum__metric is-warning" : "publish-drafts-spectrum__metric"/,
  "Attention metric tint must apply only when count > 0",
);
assert.match(
  page,
  /warningDraftCount > 0 \? "publish-drafts-spectrum__metric is-warning" : "publish-drafts-spectrum__metric"/,
  "Warnings metric tint must apply only when count > 0",
);
assert.doesNotMatch(page, /publish-drafts-spectrum__donut|conic-gradient/, "Poster must not revive the donut");
assert.doesNotMatch(page, /publish-drafts-spectrum__ledger|publish-drafts-spectrum__stack/, "Poster must retire ledger stack chrome");
assert.doesNotMatch(
  page,
  /publish-drafts-spectrum is-v6|publish-drafts-spectrum is-v5|publish-drafts-spectrum is-v4|publish-drafts-spectrum is-v3|publish-drafts-spectrum is-v2/,
  "Prior spectrum marks must retire",
);
assert.doesNotMatch(page, /ops-drafts-kpi|DraftsKpi|ops-drafts-kpis/, "Retired Ops KPI marks must go");
assert.match(page, /publish-drafts-ledger/, "Drafts must render as a split ledger table");
assert.match(page, /publish-drafts-ledger__row/, "Each draft must render as a ledger row");
assert.match(page, /publish-drafts-ledger__identity/, "Ledger rows must keep a draft identity column");
assert.match(page, /publish-drafts-ledger__signal/, "Ledger rows must keep a signal column");
assert.match(
  page,
  /<Link[\s\S]{0,220}?className=\{`publish-drafts-ledger__row|className="publish-drafts-ledger__row/,
  "Ledger rows must be whole-row links into draft detail",
);
assert.match(page, /publish-drafts-ledger__open/, "Ledger rows must keep an open affordance");
assert.match(page, /publish-drafts-ledger__open-icon/, "Open affordance must use a chevron icon");
assert.doesNotMatch(
  page,
  /publish-drafts-ledger__open"[^>]*>\s*\{t\("publishDraftsIndex\.open"\)\}/,
  "Open affordance must not show the Open text label",
);
assert.doesNotMatch(
  page,
  /<Link[\s\S]{0,180}?className="publish-drafts-ledger__open"/,
  "Open chevron must not be a nested link inside the row",
);
assert.doesNotMatch(page, /publish-drafts-mosaic|publish-drafts-tile|DraftTile/, "Ledger must retire mosaic tiles");

assert.doesNotMatch(page, /publish-drafts-tickets|publish-drafts-ticket/, "Ledger must retire ticket list chrome");
assert.doesNotMatch(page, /publish-drafts-row is-head/, "Ledger must retire the 6-column sheet head");
assert.doesNotMatch(page, /publish-drafts-toolbar/, "Triage links must fold into the queue panel header");
assert.match(page, /publish-drafts-panel__links/, "Queue panel header must host triage links");
assert.match(page, /className="publish-drafts-panel__link"/, "Triage links must render as styled link buttons");
assert.match(page, /publish-drafts-panel__link-icon/, "Triage link buttons must include icons");
assert.match(page, /\/publishing\/export-packages/, "Export Packages triage link must remain");
assert.match(page, /\/publishing\/publish-handoffs/, "Publish Handoffs triage link must remain");
assert.match(page, /IntelligenceSpectrumSkeleton/, "Cold load must use the shared Intelligence spectrum skeleton");
assert.match(page, /IntelligenceTableSkeleton/, "Cold load must still skeleton the dense sheet");
assert.match(page, /publish-drafts-attention/, "Needs-attention must remain available as a quiet strip");
assert.match(en, /"spectrumStatusMix"/, "en.json must define spectrumStatusMix");
assert.match(vi, /"spectrumStatusMix"/, "vi.json must define spectrumStatusMix");



const cssStart = cssFull.indexOf("/* Publishing Drafts Intelligence worksheet v1");
assert.ok(cssStart >= 0, "v1 Publish Drafts CSS block must exist");
const css = cssFull.slice(cssStart, cssStart + 48000);
assert.match(css, /--pl-iq-mint:\s*#f4f8f6/, "Drafts worksheet must use Intelligence mint");
assert.match(css, /--pl-iq-label-strong:\s*#2a4d41/, "Drafts worksheet must use Intelligence strong ink");
assert.match(css, /publish-drafts-spectrum\.is-v7/, "v7 CSS must style the Queue poster");
assert.match(css, /publish-drafts-spectrum__poster/, "v7 CSS must style the poster composition");
assert.match(css, /publish-drafts-spectrum__score/, "v7 CSS must style score rows");
assert.match(css, /publish-drafts-spectrum__track/, "v7 CSS must style persistent score tracks");
assert.match(css, /publish-drafts-spectrum__metrics/, "v7 CSS must style the ticker metrics");
assert.match(
  css,
  /publish-drafts-spectrum__stage \{[\s\S]{0,900}?box-shadow:/,
  "Poster stage must carry a soft elevation",
);
assert.match(
  css,
  /publish-drafts-spectrum__stage \{[\s\S]{0,900}?padding:\s*0\.8rem/,
  "Poster stage must use compact padding",
);
assert.match(
  css,
  /publish-drafts-spectrum__total > b \{[\s\S]{0,280}?clamp\(2rem/,
  "Poster total must use a compact display size",
);
assert.match(
  css,
  /publish-drafts-spectrum__score > li \{[\s\S]{0,420}?padding:\s*0\.3rem/,
  "Score rows must use compact padding",
);
assert.match(
  css,
  /publish-drafts-spectrum\.is-v7 \.publish-drafts-spectrum__stage \{[\s\S]{0,900}?width:\s*100%/,
  "Poster stage must span the content width",
);
assert.doesNotMatch(
  css,
  /publish-drafts-spectrum\.is-v7 \.publish-drafts-spectrum__stage \{[\s\S]{0,900}?max-width:/,
  "Poster stage must not use a left-anchored max-width",
);
assert.doesNotMatch(css, /publish-drafts-spectrum__donut/, "Donut CSS must retire with Queue poster");
assert.match(css, /publish-drafts-attention/, "Attention strip styles must exist");
assert.match(css, /publish-drafts-ledger/, "Ledger table styles must exist");
assert.match(css, /publish-drafts-ledger__signal/, "Ledger signal column styles must exist");
assert.match(css, /publish-drafts-panel__link \{/, "Triage link button styles must exist");
assert.match(css, /publish-drafts-panel__link-icon/, "Triage link icon styles must exist");
assert.match(
  css,
  /publish-drafts-panel__link \{[\s\S]{0,420}?border-radius:\s*(?:8|9|10)px/,
  "Triage link buttons must use soft chip radius, not plain text",
);
assert.match(
  css,
  /publish-drafts-ledger__row \{[\s\S]{0,420}?grid-template-columns:\s*minmax\(0,\s*1fr\)\s+auto/,
  "Ledger rows must give leftover width to identity and size signal to content",
);
assert.match(
  css,
  /publish-drafts-ledger__row \{[\s\S]{0,480}?padding:\s*0\.3(?:2|4|5|6)rem/,
  "Ledger rows must use denser vertical padding",
);
assert.match(
  css,
  /publish-drafts-ledger__body \{[\s\S]{0,220}?gap:\s*0\.2rem/,
  "Ledger body must tighten row spacing for long queues",
);
assert.match(
  css,
  /publish-drafts-ledger__row:hover|:hover[\s\S]{0,80}?publish-drafts-ledger__row/,
  "Whole-row links must have a hover affordance",
);
assert.match(
  css,
  /publish-drafts-ledger__head \{[\s\S]{0,360}?grid-template-columns:\s*minmax\(0,\s*1fr\)\s+auto/,
  "Ledger head must align DRAFT/SIGNAL with the content-sized columns",
);
assert.match(
  css,
  /publish-drafts-ledger__open \{[\s\S]{0,280}?margin-left:\s*0(?:\.?\d*rem)?/,
  "Open icon must sit next to chips without auto trailing space",
);
assert.doesNotMatch(
  css,
  /publish-drafts-ledger__open \{[\s\S]{0,280}?margin-left:\s*auto/,
  "Open icon must not push to the far edge of a half-width signal column",
);
assert.doesNotMatch(css, /publish-drafts-mosaic|publish-drafts-tile__/, "Retired mosaic styles must go");
assert.doesNotMatch(css, /publish-drafts-tickets|publish-drafts-ticket__/, "Retired ticket styles must go");
assert.doesNotMatch(css, /publish-drafts-row\.is-head/, "Retired sheet head styles must go");

console.log("publish-drafts-index-polish: PASS");
