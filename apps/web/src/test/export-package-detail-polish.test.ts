/**
 * Export Package detail — inspect dossier polish contract.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const testDir = dirname(fileURLToPath(import.meta.url));
const webSrc = resolve(testDir, "..");

const page = readFileSync(resolve(webSrc, "components/operator-routes/ExportPackageByIdPage.tsx"), "utf8");
const cssFull = readFileSync(resolve(webSrc, "app/globals.css"), "utf8");
const en = JSON.parse(readFileSync(resolve(webSrc, "lib/i18n/en.json"), "utf8")) as {
  opsExportPackages: Record<string, string>;
};
const vi = JSON.parse(readFileSync(resolve(webSrc, "lib/i18n/vi.json"), "utf8")) as {
  opsExportPackages: Record<string, string>;
};
const pkg = readFileSync(resolve(webSrc, "../package.json"), "utf8");

assert.match(page, /OperatorStudioShell/, "Detail must keep OperatorStudioShell");
assert.match(page, /TopbarRefreshButton/, "Detail must keep Refresh in the Topbar");
assert.match(page, /OpsDetailPanel/, "Detail must keep OpsDetailPanel for collapsed diagnostics");
assert.match(page, /fetchExportPackage/, "Detail must keep package GET authority");
assert.match(page, /action\.run\("create-handoff"/, "Create Handoff must stay synchronously gated");
assert.match(page, /createdHandoff/, "Created handoff follow-up must remain visible");
assert.match(page, /inline-error/, "Inline action errors must remain");
assert.match(page, /skeletonVariant="detail"/, "Cold load must use the detail skeleton");
assert.match(page, /export-package-dossier is-open/, "Detail must open as an inspect dossier, not Ops inventory");
assert.match(page, /export-package-dossier__stamp/, "Detail must expose a stamp strip");
assert.match(page, /export-package-dossier__rail/, "Related links must live on an in-page rail");
assert.match(page, /export-package-dossier__contents/, "Packaged rows must be the inspect hero");
assert.match(page, /export-package-dossier__flag/, "Each row must separate Render and Draft readiness, not a chip soup");
assert.doesNotMatch(
  page,
  /export-package-dossier__flag[\s\S]{0,180}<small>/,
  "Render/Draft chips must not stack a redundant kicker above the readiness copy"
);
assert.match(page, /export-package-dossier__rowhead/, "Item hops must sit with identity, not a far-right island");
assert.match(
  page,
  /export-package-dossier__identity[\s\S]{0,280}source_video_id/,
  "Cargo row must identify the packaged video from GET source_video_id, not INCLUDED"
);
assert.doesNotMatch(
  page,
  /<strong>\{humanizeStatus\(item\.item_status\)\}/,
  "INCLUDED item_status must not masquerade as the row title"
);
assert.match(
  page,
  /export-package-dossier__rowhead[\s\S]{0,900}export-package-dossier__flags[\s\S]{0,700}<nav>/,
  "Render/Draft chips and hops must stay in the identity sentence, not a far-right column"
);
assert.doesNotMatch(page, /export-package-dossier__slip/, "Packing-slip chrome must leave; detail must match operator bay pages");
assert.doesNotMatch(page, /export-package-dossier__desk/, "Two-column desk layout must stay retired");
assert.match(
  page,
  /export-package-dossier__body[\s\S]{0,1200}OpsDetailPanel/,
  "Diagnostics must live with cargo, not below leftover whitespace"
);
assert.match(page, /MISSING_PUBLISH_DRAFT[\s\S]{0,180}publish_draft_id/, "Missing-draft warnings must not repeat beside Draft missing");
assert.match(
  page,
  /export-package-dossier__who[\s\S]{0,350}export-package-dossier__stamp-chip/,
  "Status chip must sit beside the package label, not with the far-right CTAs"
);
assert.match(
  page,
  /export-package-dossier__who[\s\S]{0,900}opsExportPackages\.blocked/,
  "Blocked count is the only facts label that belongs with Handoff created"
);
assert.doesNotMatch(
  page,
  /export-package-dossier__stub-meta[\s\S]{0,600}opsExportPackages\.blocked/,
  "Blocked must leave the facts line once it sits with the status chip"
);
assert.match(page, /item\.ready_at \?\? item\.created_at/, "Created and Ready instants must collapse to one recorded time");
assert.doesNotMatch(
  page,
  /opsExportPackages\.createdAt|opsExportPackages\.readyAt/,
  "Created/Ready words must not compete with humanizeStatus on the chip"
);
assert.match(page, /mergeLifecycleByMinute|format\(prev\.at\) === format\(step\.at\)/, "Same-minute failure stamps must still collapse");
assert.doesNotMatch(
  page,
  /actionMessage \? <p className="success-message"/,
  "Toast already announces create; body must not repeat the handoff id"
);
assert.match(
  page,
  /createdHandoff && !item\.publish_handoff_ids\.includes\(createdHandoff\.id\)/,
  "Open-created follow-up must hide once the stamp already links that handoff"
);
assert.match(page, /opsExportPackages\.detailTitle/, "Shell title must be i18n");
assert.match(page, /opsExportPackages\.description/, "Shell description must be i18n");
assert.match(page, /item\.label/, "Package title must read label from GET authority");
assert.match(page, /humanizeStatus/, "Package status must be humanized");
assert.match(page, /render_output_id/, "Contents must surface render_output_id readiness");
assert.match(page, /publish_draft_id/, "Contents must surface publish_draft_id readiness");
assert.match(page, /diagnostics_json/, "Item warnings must read diagnostics_json");
assert.match(page, /\/publishing\/drafts\/\$\{/, "Ready drafts must deep-link the draft desk");
assert.match(page, /\/production\/final-review\/\$\{/, "Each row must jump to Final Review");
assert.match(page, /\/production\/transcript-editor\/\$\{/, "Each row must jump to Transcript");
assert.match(page, /\/publishing\/publish-handoffs\/\$\{/, "Existing handoffs must remain openable");
assert.match(page, /\/publishing\/export-packages"/, "Rail must link all packages");
assert.match(page, /\/selection\/reup-queue/, "Rail must link Reup Queue");
assert.match(page, /\/publishing\/publish-handoffs"/, "Rail must link Publish Handoffs");
assert.doesNotMatch(
  page,
  /actions=\{[\s\S]*?<a href="\/publishing\/export-packages">/,
  "All Export Packages must leave the topbar actions soup"
);
assert.doesNotMatch(
  page,
  /actions=\{[\s\S]*?Create Publish Handoff/,
  "Create Handoff must leave the topbar and sit on the stamp"
);
assert.match(page, /does not call platform APIs/, "Handoff creation must stay separate from platform publishing");
assert.match(page, /FACEBOOK_REELS/, "Create Handoff must keep the API default destination");
assert.match(page, /failed_at/, "Lifecycle must read failed_at");
assert.match(page, /cancelled_at/, "Lifecycle must read cancelled_at");
assert.match(page, /export-package-dossier__timeline/, "Lifecycle must render as a timeline");
assert.match(
  page,
  /\{step\.label \? <i aria-hidden="true" \/> : null\}/,
  "Recorded time must not keep a status pip after Created/Ready labels left"
);
assert.doesNotMatch(page, /OpsSummaryCards|summaryCardsForPackage/, "KPI summary cards must stay retired");
assert.doesNotMatch(page, /OpsItemCard|PackageContentCard/, "Ops item cards must stay retired");
assert.doesNotMatch(page, /workspace_id/, "Workspace UUID must leave the operator-facing metadata");
assert.doesNotMatch(page, /Package content row preserved/, "Placeholder item copy must stay retired");
assert.doesNotMatch(page, /statusTone="good"/, "Item rows must not fake a pass tone");
assert.doesNotMatch(page, /title="Export Package detail"/, "Hardcoded English shell title must leave");
assert.doesNotMatch(page, /OpsMetadataList/, "Raw UUID metadata list must stay retired");
assert.doesNotMatch(page, /publish-handoff-dossier|export-packages-mix|export-packages-page is-v4/, "Must not clone handoff dossier classes or index donut chrome");
assert.doesNotMatch(page, /cookie|secret|token/i, "Must not expose secrets");

assert.ok(en.opsExportPackages.detailTitle, "en.json must define detailTitle");
assert.ok(vi.opsExportPackages.detailTitle, "vi.json must define detailTitle");
assert.ok(en.opsExportPackages.createHandoff, "en.json must define createHandoff");
assert.ok(vi.opsExportPackages.createHandoff, "vi.json must define createHandoff");
assert.ok(en.opsExportPackages.renderSealed || en.opsExportPackages.renderMissing, "en.json must name render readiness");
assert.ok(vi.opsExportPackages.renderSealed || vi.opsExportPackages.renderMissing, "vi.json must name render readiness");
assert.ok(en.opsExportPackages.facebookReelsHandoff, "en.json must name the Facebook Reels handoff destination");
assert.ok(vi.opsExportPackages.facebookReelsHandoff, "vi.json must name the Facebook Reels handoff destination");

const cssStart = cssFull.indexOf("/* Export Package detail inspect");
assert.ok(cssStart >= 0, "Export Package detail inspect CSS block must exist");
const css = cssFull.slice(cssStart, cssStart + 18000);
assert.match(css, /\.export-package-dossier/, "CSS must define the dossier shell");
assert.match(css, /--ep-stage-ready:\s*#2f8f6f/, "Dossier must reuse Export Packages Ready token");
assert.match(css, /--ep-stage-handed:\s*#4f6fbf/, "Dossier must reuse Export Packages Handoff token");
assert.match(css, /\.export-package-dossier__contents/, "CSS must style packaged contents");
assert.match(css, /\.export-package-dossier__flag/, "CSS must style render/draft flags as a pair");
assert.match(
  page,
  /export-package-dossier__lead[\s\S]{0,1200}export-package-dossier__cta/,
  "Open/Create must sit on the identity lead, not a far-right island"
);
assert.match(
  page,
  /export-package-dossier__facts[\s\S]{0,2200}export-package-dossier__metrics[\s\S]{0,900}export-package-dossier__timeline/,
  "Note and items/id/time must share the facts cluster"
);
assert.match(
  css,
  /\.export-package-dossier__facts[\s\S]{0,200}display:\s*flex/,
  "Operator note and metrics must share one wrapping row"
);
assert.match(
  css,
  /\.export-package-dossier__metrics \{[\s\S]{0,280}background:\s*#fff/,
  "Items, id, and time must read as a raised cluster beside the note"
);
assert.match(
  css,
  /\.export-package-dossier__metrics \{[\s\S]{0,360}font-size:\s*0\.72rem/,
  "Metrics type must stay readable; shrink the capsule via padding instead"
);
assert.match(
  css,
  /\.export-package-dossier__metrics \{[\s\S]{0,420}line-height:\s*1;/,
  "Metrics pill must lose vertical slack via line-height, not smaller type"
);
assert.match(
  css,
  /\.export-package-dossier__metrics \{[\s\S]{0,460}padding:\s*0 /,
  "Metrics pill must lose vertical slack via padding-block 0, not smaller type"
);
assert.match(
  page,
  /export-package-dossier__tools[\s\S]{0,1400}export-package-dossier__stamp-note/,
  "Facebook Reels footnote must sit under Open/Create, not mixed into package facts"
);
assert.doesNotMatch(
  page,
  /export-package-dossier__facts[\s\S]{0,2400}export-package-dossier__stamp-note/,
  "Handoff helper copy must leave the facts row"
);
assert.doesNotMatch(
  css,
  /\.export-package-dossier__mix[\s\S]{0,280}minmax\(0,\s*1fr\)\s+minmax\(/,
  "Mix must not stretch a 1fr void between identity and CTAs"
);
assert.match(
  css,
  /\.export-package-dossier__lead[\s\S]{0,220}flex-wrap:\s*wrap/,
  "Lead must keep title and CTAs on one wrapping row"
);
assert.match(
  css,
  /\.export-package-dossier__stub h2[\s\S]{0,200}text-overflow:\s*ellipsis/,
  "Long package labels must ellipsis instead of shoving CTAs onto a second stack"
);
assert.match(
  css,
  /\.export-package-dossier__metrics > \* \+ \*[\s\S]{0,200}border-left/,
  "Items, id, and time must split with a visible rail, not loose whitespace"
);
assert.doesNotMatch(
  css,
  /\.export-package-dossier__timeline \{[\s\S]{0,220}padding:\s*0/,
  "Timeline must not zero padding and glue the time to the package id"
);
assert.doesNotMatch(
  css,
  /\.export-package-dossier__stub-meta button \{[\s\S]{0,220}padding:\s*0/,
  "Copy-id control must not zero the rail padding beside Items"
);
assert.match(
  css,
  /\.export-package-dossier__cta[\s\S]{0,180}display:\s*inline-flex/,
  "Open/Create must hug as pills on the title row"
);
assert.match(
  css,
  /\.export-package-dossier\.is-open[\s\S]{0,360}padding:\s*18px var\(--app-content-inset-x\)/,
  "Detail inset must match Export Packages and Publish Handoff pages"
);
assert.match(
  css,
  /\.export-package-dossier__stamp[\s\S]{0,240}border-radius:\s*14px/,
  "Stamp card must use the shared 14px operator bay radius"
);
assert.match(
  css,
  /\.export-package-dossier__mix[\s\S]{0,280}var\(--pl-iq-mint\) 38%/,
  "Identity band must use the shared mint mix wash, not a dark waybill"
);
assert.match(
  css,
  /\.export-package-dossier__rail[\s\S]{0,280}var\(--pl-iq-mint\) 55%/,
  "Related rail must match the Export Packages bay rail"
);
assert.match(
  css,
  /\.export-package-dossier__contents li[\s\S]{0,220}display:\s*flex/,
  "Packaged item must scan as one hugging sentence, not a stretched table"
);
assert.doesNotMatch(
  css,
  /\.export-package-dossier__contents li[\s\S]{0,320}minmax\(0,\s*1fr\)/,
  "Packaged item must not leave a 1fr ocean between identity and flags"
);
assert.doesNotMatch(
  css,
  /\.export-package-dossier__flags[\s\S]{0,200}justify-self:\s*end/,
  "Render/Draft chips must sit in the sentence, not the far-right island"
);
assert.doesNotMatch(
  css,
  /\.export-package-dossier__who[\s\S]{0,180}flex:\s*1 /,
  "Title cluster must not eat leftover width and shove Open/Create to the far edge"
);
assert.doesNotMatch(
  css,
  /\.export-package-dossier__tools[\s\S]{0,180}margin-left:\s*auto/,
  "Open/Create must hug the title chips, not ride the far-right margin"
);
assert.match(
  css,
  /\.export-package-dossier__idx[\s\S]{0,220}position:\s*static/,
  "Item index must sit in the row flow so the cargo line can hug vertically"
);
assert.match(
  css,
  /\.export-package-dossier__flags[\s\S]{0,180}display:\s*inline-flex/,
  "Render and Draft must sit as compact chips, not two full-width stacked cards"
);
assert.match(
  css,
  /\.export-package-dossier__flag \{[\s\S]{0,280}display:\s*inline-flex/,
  "Each readiness flag must be a one-line chip, not a stacked RENDER/DRAFT card"
);
assert.match(
  css,
  /\.export-package-dossier__flag \{[\s\S]{0,360}line-height:\s*1;/,
  "Readiness chips must lose vertical slack via line-height, not a second label row"
);
assert.match(
  css,
  /\.export-package-dossier__flag \{[\s\S]{0,420}padding:\s*0\.[\d]+rem 0\.[\d]+rem;/,
  "Readiness chips must hug copy with compact padding instead of card wells"
);
assert.doesNotMatch(
  css,
  /\.export-package-dossier__flags[\s\S]{0,220}repeat\(2,\s*minmax\(0,\s*1fr\)\)/,
  "Render/Draft must not stretch as equal full-width status tiles"
);
assert.doesNotMatch(css, /#fffaf4/, "Cream packing-slip paper must leave");
assert.match(
  css,
  /\.export-package-dossier\.is-open[\s\S]{0,420}align-content:\s*start/,
  "Dossier must hug content instead of stretching leftover viewport into empty wells"
);
assert.match(
  css,
  /\.export-package-dossier\.is-open \.ops-console-detail-panel[\s\S]{0,180}padding:\s*0/,
  "Collapsed Inspect must not leave a tall empty white box"
);
assert.doesNotMatch(css, /export-packages-mix__donut/, "Detail CSS must not copy the index donut");
assert.doesNotMatch(css, /publish-handoff-dossier/, "Detail CSS must not reuse handoff dossier selectors");

assert.match(pkg, /export-package-detail-polish\.test\.ts/, "package.json must run export package detail polish");

console.log("export-package-detail-polish: PASS");
