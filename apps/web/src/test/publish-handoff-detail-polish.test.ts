/**
 * Publish Handoff detail — dossier polish contract.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const testDir = dirname(fileURLToPath(import.meta.url));
const webSrc = resolve(testDir, "..");

const page = readFileSync(resolve(webSrc, "components/operator-routes/PublishHandoffByIdPage.tsx"), "utf8");
const css = readFileSync(resolve(webSrc, "app/globals.css"), "utf8");
const en = JSON.parse(readFileSync(resolve(webSrc, "lib/i18n/en.json"), "utf8")) as {
  opsPublishHandoffs: Record<string, string>;
};
const vi = JSON.parse(readFileSync(resolve(webSrc, "lib/i18n/vi.json"), "utf8")) as {
  opsPublishHandoffs: Record<string, string>;
};

assert.match(page, /OperatorStudioShell/, "Detail must keep OperatorStudioShell");
assert.match(page, /TopbarRefreshButton/, "Detail must keep Refresh in the Topbar");
assert.match(page, /OpsDetailPanel/, "Detail must keep OpsDetailPanel");
assert.match(page, /fetchPublishHandoff/, "Detail must keep handoff authority");
assert.match(page, /publish-handoff-dossier/, "Detail must use dossier shell class");
assert.match(page, /publish-handoff-dossier__stamp|publish-handoff-dossier__hero/, "Detail must expose a stamp/hero status strip");
assert.match(page, /publish-handoff-dossier__rail/, "Detail must expose an in-page related rail");
assert.match(page, /opsPublishHandoffs\.detailTitle|t\("opsPublishHandoffs\.title"\)/, "Shell title must be i18n");
assert.match(page, /opsPublishHandoffs\.description/, "Shell description must be i18n");
assert.match(page, /humanizeStatus/, "Detail status must be humanized");
assert.match(page, /\/publishing\/publish-handoffs"/, "Rail must link all handoffs");
assert.match(page, /\/publishing\/export-packages\/\$\{/, "Rail must link export package");
assert.match(page, /\/selection\/reup-queue/, "Rail must link Reup Queue");
assert.doesNotMatch(
  page,
  /actions=\{[\s\S]*?<a href="\/publishing\/publish-handoffs">All Publish Handoffs<\/a>/,
  "Related links must leave the topbar actions soup"
);
assert.match(page, /do(?:es)? not call platform APIs or auto-publish/, "Manual publishing boundary must stay explicit");
assert.match(page, /payload_json/, "Payload must remain inspectable");
assert.match(page, /diagnostics_json/, "Diagnostics must remain inspectable");
assert.doesNotMatch(page, /OpsSummaryCards/, "Detail must not reuse OpsSummaryCards (Click a card leftover)");
assert.doesNotMatch(page, /summaryCardsForHandoff/, "KPI-style state cards must stay retired");
assert.doesNotMatch(page, /publish-handoff-dossier__facts/, "Stacked 2-col facts grid must not be the layout");
assert.doesNotMatch(page, /publish-handoff-dossier__split|publish-handoff-dossier__identity/, "Two-column overview inspector must stay retired");
assert.match(page, /publish-handoff-dossier is-open/, "Detail must open as a Dispatch-family card, not a poster or sheet");
assert.doesNotMatch(page, /is-sheet|is-pass|is-compact|is-poster/, "Sheet, ticket, ribbon, and off-palette poster chrome must stay retired");
assert.doesNotMatch(page, /publish-handoff-dossier__ghost/, "Oversized ghost type must not leave the ops palette");
assert.match(page, /publish-handoff-dossier__ring/, "Lifecycle progress must use the same ring language as the bay donut");
assert.doesNotMatch(page, /data-field=|is-hero|is-wide/, "Asymmetric mosaic tiles must stay retired");
assert.doesNotMatch(page, /cargo-group/, "Manifest must not spend height on Media/References subheads");
assert.doesNotMatch(page, /publish-handoff-dossier__ids/, "Full workspace/handoff dumps must not repeat beside cargo");
assert.match(page, /publish-handoff-dossier__stub/, "Platform destination must live on the mast");
assert.match(
  page,
  /publish-handoff-dossier__stub[\s\S]{0,420}<h2[\s\S]{0,180}publish-handoff-dossier__stamp-chip/,
  "Status chip must sit on the destination row, not a third stacked line"
);
assert.match(page, /publish-handoff-dossier__cargo/, "Payload scalars must render as a copyable manifest, not a hero JSON dump");
assert.match(page, /buildHandoffCargo/, "Manifest rows must use grouped cargo helper");
assert.match(page, /clipboard\.writeText/, "Manifest values must be copyable");
assert.match(page, /publish-handoff-dossier__timeline/, "Lifecycle must render as a timeline, not another definition list");
assert.match(page, /mergeLifecycleByMinute/, "Same-minute lifecycle stamps must collapse");
assert.match(page, /publish-handoff-dossier__note/, "Operator note must be a single line, not a quote box");
assert.doesNotMatch(page, /<blockquote>/, "Full-width operator note banner must stay retired");
assert.doesNotMatch(
  page,
  /OpsDetailSection collapsed[\s\S]{0,80}description=\{t\("opsPublishHandoffs.payloadDesc"\)\}/,
  "Collapsed payload must not show the inspect disclaimer in the closed summary"
);
assert.match(page, /publish-handoff-dossier__stamp[\s\S]*noPlatformApi|noPlatformApi[\s\S]*stamp/, "Manual-publish boundary must live on the stamp");
assert.match(
  page,
  /publish-handoff-dossier__stub[\s\S]*publishAutomationValue/,
  "Manual-automation note must live on the mast, not beside Manifest"
);
assert.doesNotMatch(
  page,
  /cargo-head[\s\S]{0,280}publishAutomationValue/,
  "Manifest heading must not orphan publishAutomationValue"
);
assert.match(page, /publish-handoff-dossier__link-icon/, "Related rail buttons must use Dispatch-bay link icons");
assert.match(page, /publish-handoff-dossier__copy-icon/, "Copy actions must include a clipboard icon");
assert.match(
  page,
  /aria-label=\{copied \? copiedLabel : copyLabel\}[\s\S]{0,180}<HandoffDetailIcon kind=\{copied \? "copied" : "copy"\} \/>/,
  "Cargo copy must keep the label in aria-label and show only the icon"
);
assert.doesNotMatch(
  page,
  /HandoffDetailIcon kind=\{copied \? "copied" : "copy"\} \/>\s*\{copied \? copiedLabel : copyLabel\}/,
  "Cargo copy buttons must not repeat the Copy word beside the icon"
);
assert.match(
  css,
  /\.publish-handoff-dossier\.is-open\s*\{[\s\S]{0,420}padding:\s*18px\s+var\(--app-content-inset-x\)/,
  "Detail must use the same content inset as the operator topbar and Dispatch bay"
);
assert.match(
  css,
  /\.publish-handoff-dossier\.is-open\s*\{[\s\S]{0,500}--pl-iq-mint:[\s\S]{0,200}--ph-stage-ready:/,
  "Detail tokens must match the Publish Handoffs Dispatch bay"
);
assert.match(css, /\.publish-handoff-dossier__link-icon\s*\{/, "Rail link icons must be sized");
assert.match(css, /\.publish-handoff-dossier__copy-icon\s*\{/, "Copy icons must be sized");
assert.match(css, /\.publish-handoff-dossier__ring\s*\{/, "Lifecycle ring must be styled");
assert.match(
  css,
  /\.publish-handoff-dossier\.is-open \.publish-handoff-dossier__rail[\s\S]{0,280}justify-content:\s*flex-end/,
  "Related rail buttons must sit on the right of the mint bar"
);
assert.match(
  css,
  /\.publish-handoff-dossier\.is-open \.ops-console-detail-panel[\s\S]{0,260}flex-direction:\s*row/,
  "Inspect must collapse into a compact toolbar row instead of a stacked empty stack"
);
assert.match(
  css,
  /\.publish-handoff-dossier\.is-open[\s\S]{0,2800}\.publish-handoff-dossier__cargo ul[\s\S]{0,180}minmax\(0,\s*1fr\)/,
  "Cargo must stack as full-width rows, not a mosaic or two-column sheet"
);
assert.doesNotMatch(css, /\.publish-handoff-dossier\.is-sheet\s*\{/, "Property-sheet shell CSS must not remain");
assert.doesNotMatch(css, /\.publish-handoff-dossier\.is-poster\s*\{/, "Off-palette poster shell CSS must not remain");
assert.doesNotMatch(css, /publish-handoff-dossier\.is-compact/, "Compact ribbon CSS must not remain");
assert.match(css, /\.publish-handoff-dossier__stub\s*\{/, "Mast must be styled");
assert.match(css, /\.publish-handoff-dossier__cargo\s*\{/, "Manifest rows must be styled");
assert.match(css, /\.publish-handoff-dossier__row\s*\{/, "Copy rows must share a compact cluster class");
assert.match(css, /\.publish-handoff-dossier__timeline\s*\{/, "Lifecycle timeline must be styled");
assert.doesNotMatch(
  css,
  /\.publish-handoff-dossier__cargo[\s\S]{0,900}justify-content:\s*space-between/,
  "Copy must sit next to the value, not the far card edge"
);
assert.doesNotMatch(css, /publish-handoff-dossier__stub::after/, "Fake perforation dots must not sit on the stub");
assert.doesNotMatch(css, /publish-handoff-dossier__facts|publish-handoff-dossier__split\s*\{|publish-handoff-dossier__identity\s*\{/, "Retired inspector CSS must not remain");
assert.doesNotMatch(page, /cookie|secret|token/i, "Must not expose secrets");
assert.doesNotMatch(page, /publish-handoffs-bay|manifest__slip/, "Detail must not reuse Export Packages bay chrome");

assert.ok(en.opsPublishHandoffs.detailTitle || en.opsPublishHandoffs.title, "EN must define detail/title");
assert.ok(en.opsPublishHandoffs.allHandoffs, "EN must define allHandoffs rail label");
assert.ok(en.opsPublishHandoffs.openPackage, "EN must define openPackage rail label");
assert.ok(en.opsPublishHandoffs.cargo, "EN must define cargo/manifest label");
assert.ok(en.opsPublishHandoffs.copy, "EN must define copy action");
assert.ok(en.opsPublishHandoffs.cargoMedia, "EN must define media cargo group");
assert.ok(en.opsPublishHandoffs.cargoRefs, "EN must define reference cargo group");
assert.ok(vi.opsPublishHandoffs.cargoMedia, "VI must define media cargo group");
assert.ok(vi.opsPublishHandoffs.cargoRefs, "VI must define reference cargo group");
assert.ok(vi.opsPublishHandoffs.allHandoffs, "VI must define allHandoffs rail label");
assert.ok(vi.opsPublishHandoffs.openPackage, "VI must define openPackage rail label");
assert.ok(vi.opsPublishHandoffs.cargo, "VI must define cargo/manifest label");
assert.ok(vi.opsPublishHandoffs.copy, "VI must define copy action");

console.log("publish-handoff-detail-polish tests passed");
