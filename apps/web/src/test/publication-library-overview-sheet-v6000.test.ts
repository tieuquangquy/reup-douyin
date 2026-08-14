/** Overview Workbench sheet continuity — section rhythm without nested metric/draft cards. */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const testDir = dirname(fileURLToPath(import.meta.url));
const webSrc = resolve(testDir, "..");
const page = readFileSync(resolve(webSrc, "components/operator-routes/PublicationLibraryPage.tsx"), "utf8");
const cssAll = readFileSync(resolve(webSrc, "app/globals.css"), "utf8");
const en = readFileSync(resolve(webSrc, "lib/i18n/en.json"), "utf8");
const vi = readFileSync(resolve(webSrc, "lib/i18n/vi.json"), "utf8");

const marker = "/* Workbench Drawer v6000";
const start = cssAll.indexOf(marker);
assert.ok(start >= 0, "Workbench Drawer v6000 CSS block must exist");
const css = cssAll.slice(start, start + 120_000);

assert.match(
  css,
  /workbench__identity\.workbench__identity \{[\s\S]{0,220}?padding-bottom:\s*[0-9.]+rem/,
  "Identity must leave clear air before the signals band",
);
assert.match(
  css,
  /workbench__tiles\.workbench__tiles \{[\s\S]{0,320}?background:\s*#f4f8f6[\s\S]{0,220}?grid-template-columns:\s*repeat\(2/,
  "Signals must read as one quiet band under identity, not raw sheet text",
);
assert.match(
  css,
  /workbench__tiles\.workbench__tiles \{[\s\S]{0,360}?border-radius:\s*[0-9.]+rem[\s\S]{0,220}?padding:\s*[0-9.]+rem/,
  "Signals band must be inset with radius and padding so it separates from identity and draft",
);
assert.match(
  css,
  /workbench__tiles\.workbench__tiles > li:nth-child\(odd\)[\s\S]{0,160}border-right:\s*1px solid/,
  "Signals band must separate left/right columns with a hairline",
);
assert.match(
  css,
  /workbench__tiles\.workbench__tiles > li:nth-child\(-n\+2\)[\s\S]{0,160}border-bottom:\s*1px solid/,
  "Signals band must separate top/bottom rows with a hairline",
);
assert.match(
  css,
  /workbench__tiles\.workbench__tiles > li \{[\s\S]{0,180}?background:\s*transparent[\s\S]{0,120}?border:\s*0/,
  "Metric cells must stay flush inside the band without nested wells",
);
assert.doesNotMatch(
  css,
  /workbench__tiles\.workbench__tiles > li \{[^}]*linear-gradient/,
  "Metric cells must not paint nested gradient wells",
);
assert.match(
  css,
  /workbench__tile\.workbench__tile \{[\s\S]{0,180}?background:\s*transparent[\s\S]{0,120}?border:\s*0/,
  "Workbench metrics must read as a hairline table inside one band, not nested grey cards",
);
assert.match(
  css,
  /workbench__draft-bar\.workbench__draft-bar \{[\s\S]{0,220}?border-top:\s*1px solid\s*#cfdfd6/,
  "Draft row must use a stronger divider after the signals band",
);
assert.match(
  css,
  /workbench__draft-bar\.workbench__draft-bar \{[\s\S]{0,360}?padding:\s*1\.25rem 0 0/,
  "Draft row must keep extra air after the signals band",
);
assert.match(
  css,
  /workbench__draft-bar\.workbench__draft-bar \{[\s\S]{0,180}?background:\s*transparent[\s\S]{0,80}?border:\s*0/,
  "Draft row must stay flush on the sheet without a nested action card fill",
);
assert.doesNotMatch(
  css,
  /workbench__draft-bar\.workbench__draft-bar \{[^}]*linear-gradient/,
  "Draft row must not keep a mint boxed action band",
);
assert.match(
  css,
  /workbench__draft-label \{[\s\S]{0,160}?letter-spacing:\s*0\.1em/,
  "Draft label must stay clearly uppercase-separated from the CTA controls",
);
assert.match(
  css,
  /workbench__actions\.workbench__actions \{[\s\S]{0,220}?display:\s*grid[\s\S]{0,160}?grid-template-columns:\s*minmax\(0,\s*1fr\)\s+auto/,
  "Identity actions must use a status|Open primary row instead of wrapping three chips",
);
assert.match(
  css,
  /workbench__status\.workbench__status \{[\s\S]{0,420}?grid-column:\s*1[\s\S]{0,120}?grid-row:\s*1/,
  "Status must sit on the primary actions row",
);
assert.match(
  css,
  /canvas__open \{[\s\S]{0,420}?grid-column:\s*2[\s\S]{0,120}?grid-row:\s*1/,
  "Open on Facebook must sit opposite status on the primary row",
);
assert.match(
  css,
  /canvas__copy\.is-id \{[\s\S]{0,280}?grid-column:\s*1\s*\/\s*-1[\s\S]{0,120}?grid-row:\s*2/,
  "Reel ID must sit on a secondary full-width row under status and Open",
);
assert.doesNotMatch(
  css,
  /workbench__actions\.workbench__actions \{[^}]*flex-wrap:\s*wrap/,
  "Identity actions must not rely on flex-wrap that drops Open under a long Reel ID",
);
assert.match(
  page,
  /workbench__actions[\s\S]{0,1200}workbench__status[\s\S]{0,1200}canvas__open[\s\S]{0,1200}canvas__copy is-id/,
  "Actions markup must keep status, then Open, then Reel ID",
);
assert.match(
  css,
  /workbench__identity\.workbench__identity \{[\s\S]{0,200}?align-items:\s*stretch/,
  "Identity must stretch meta to the thumb height so actions can sit on the baseline",
);
assert.match(
  css,
  /workbench__meta\.workbench__meta \{[\s\S]{0,200}?min-height:\s*100%/,
  "Meta column must fill the identity row height",
);
assert.match(
  css,
  /workbench__actions\.workbench__actions \{[\s\S]{0,260}?margin-top:\s*auto/,
  "Status/Open/Reel ID must pin to the bottom of the meta column under a tall thumb",
);
assert.match(
  page,
  /workbench__tiles[\s\S]{0,2500}publicationLibrary\.publishedAt/,
  "Overview signals must label the publish time as Published at, not the same Published status word",
);
assert.match(en, /"publishedAt":\s*"Published at"/, "English i18n must distinguish publish time from status");
assert.match(vi, /"publishedAt":\s*"Đăng lúc"/, "Vietnamese i18n must distinguish publish time from status");
assert.match(
  page,
  /growth\?\.latest_view_count == null \? t\("publicationLibrary\.notCollectedYet"\)/,
  "Overview Views idle must say Not collected yet instead of a bare dash",
);
assert.match(en, /"notCollectedYet"/, "English i18n must include Not collected yet");
assert.match(vi, /"notCollectedYet"/, "Vietnamese i18n must include Not collected yet");

assert.doesNotMatch(
  page,
  /draft-menu__label">—</,
  "Draft clear option must not use a bare em dash as the only label",
);
assert.match(
  page,
  /publication-library-draft-menu__copy[\s\S]{0,120}?publicationLibrary\.draftPickerNone/,
  "Clear draft option must use the same copy row as draft items with None label",
);
assert.match(
  page,
  /drafts\.length === 0[\s\S]{0,320}?draft-menu__empty[\s\S]{0,200}?publicationLibrary\.noFacebookDrafts/,
  "Empty draft list must show an empty-state row inside the menu",
);
assert.match(en, /"draftPickerNone":\s*"None"/, "English i18n must label clear draft choice as None");
assert.match(vi, /"draftPickerNone":\s*"Không chọn"/, "Vietnamese i18n must label clear draft choice");
assert.match(en, /"noFacebookDrafts":\s*"No Facebook drafts are available\."/, "English publicationLibrary empty drafts copy");
assert.match(vi, /"noFacebookDrafts":/, "Vietnamese publicationLibrary empty drafts copy");
assert.match(
  css,
  /draft-menu__item \{[\s\S]{0,280}?display:\s*grid[\s\S]{0,160}?grid-template-columns:\s*minmax\(0,\s*1fr\)\s+auto/,
  "Draft menu items must use a full-width copy|check grid like the desk picker",
);
assert.match(
  css,
  /draft-menu__copy \{[\s\S]{0,160}?min-width:\s*0[\s\S]{0,80}?width:\s*100%/,
  "Draft menu copy must fill the item so selected mint is not a short chip",
);
assert.match(
  css,
  /draft-menu__empty \{/,
  "Draft menu must style the empty-state row",
);
assert.match(
  css,
  /draft-menu \{[\s\S]{0,360}?top:\s*calc\(100%\s*\+\s*[0-9.]+rem\)/,
  "Draft menu must open downward under the trigger",
);
assert.doesNotMatch(
  css,
  /is-v6000 \.publication-library-draft-menu \{[^}]*bottom:\s*calc\(100%/,
  "Draft menu must not flip upward as the clipping workaround",
);
assert.match(
  css,
  /mode-shell\.mode-shell:has\(\.publication-library-draft-picker\.is-open\)[\s\S]{0,120}?overflow:\s*visible/,
  "Mode shell must stop clipping the draft menu while the picker is open",
);
assert.match(
  css,
  /work-item-details-drawer:has\(\.publication-library-draft-picker\.is-open\)[\s\S]{0,160}?work-item-details-drawer__body[\s\S]{0,120}?overflow:\s*visible/,
  "Drawer body must not clip the open draft menu below the shell",
);

console.log("publication-library-overview-sheet-v6000: PASS");
