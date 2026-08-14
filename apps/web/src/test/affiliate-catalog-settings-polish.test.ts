/** Publishing Settings / Affiliate Catalog v10: Intelligence worksheet, no KPI card stack. */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const webSrc = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const page = readFileSync(resolve(webSrc, "components/operator-routes/AffiliateCatalogPage.tsx"), "utf8");
const settings = page;
const skeleton = readFileSync(resolve(webSrc, "components/operator-routes/IntelligenceDataSkeleton.tsx"), "utf8");
const cssFull = readFileSync(resolve(webSrc, "app/globals.css"), "utf8");

const v10Start = cssFull.indexOf("/* Publishing Settings Affiliate Catalog v10");
assert.ok(v10Start >= 0, "v10 Affiliate Catalog CSS block must exist");
const v10 = cssFull.slice(v10Start, v10Start + 18000);
const v12Start = cssFull.indexOf("/* Publishing Settings Affiliate Catalog v12");
assert.ok(v12Start >= 0, "v12 editorial create sheet CSS block must exist");
const v12 = cssFull.slice(v12Start, v12Start + 5000);
const v13Start = cssFull.indexOf("/* Publishing Settings Affiliate Catalog v13");
assert.ok(v13Start >= 0, "v13 identity-band CSS block must exist");
const v13 = cssFull.slice(v13Start, v13Start + 4000);

assert.match(settings, /publishing-settings-page is-v1 is-v4/, "Settings page must keep the v4 horizontal switcher shell");
assert.match(page, /affiliate-catalog-page is-v10 is-v11 is-v12 is-v13 is-v14 is-v15 is-v16 is-v17 is-v18/, "Catalog workbench must mark is-v18 fact-strip meta");
assert.match(page, /affiliate-catalog-status-cell/, "Status and timestamp must stack in one cell, not sit inline");
assert.match(page, /affiliate-catalog-metric/, "Commission must stay a dedicated metric cell");
assert.match(page, /toolbar__icon-btn is-add/, "Add product must be the strong toolbar CTA");
assert.match(page, /is-version[\s\S]{0,180}?<b>V1<\/b>/, "Version chip must show a short V1, full id stays on title");
assert.doesNotMatch(page, /affiliate-catalog-header/, "Nav already names the section; drop the duplicate page header");
assert.doesNotMatch(page, /affiliate-catalog-kpis/, "Counts must not sit in a 3-card KPI strip");
assert.match(page, /affiliate-catalog-toolbar/, "Catalog must use a compact Intelligence toolbar");
assert.match(page, /affiliate-catalog-toolbar__meta/, "Toolbar must show counts as inline meta, not cards");
assert.match(page, /affiliate-catalog-meta/, "Count chips must use the shared meta mark");
assert.match(page, /affiliate-catalog-toolbar__icon-btn/, "Refresh / Import / Add must be icon-only toolbar actions");
assert.match(page, /aria-label=\{t\("affiliateCatalog\.addProduct"\)\}/, "Icon-only Add must keep an accessible name");
assert.match(page, /aria-label=\{t\("affiliateCatalog\.importCsv"\)\}/, "Icon-only Import must keep an accessible name");
assert.match(page, /CatalogGlyph kind="plus"/, "Add must use the plus glyph");
assert.match(page, /CatalogGlyph kind="import"/, "Import must use the import glyph");
assert.match(page, /CatalogGlyph kind="edit"/, "Row edit must use the pencil glyph");
assert.match(page, /affiliate-catalog-note/, "API errors must render as a worksheet note, not a floating danger banner");
assert.match(page, /affiliate-catalog-upload-panel[\s\S]*type="file"/, "Image upload must stay on the product editor");
assert.match(page, /showForm \?[\s\S]*affiliate-catalog-form[\s\S]*affiliate-catalog-upload-panel/, "Upload must live inside the product form, not a separate dashed card");
assert.match(page, /IntelligenceCatalogWorksheetSkeleton/, "Cold load must use the Catalog worksheet skeleton (toolbar + table)");
assert.match(page, /is-editing/, "The open editor must mark its catalog row");
assert.match(page, /is-inactive/, "Inactive products must keep a row mark");
assert.match(page, /createAffiliateProduct[\s\S]*bulkImportAffiliateProducts[\s\S]*updateAffiliateProduct/, "Create, CSV import, and updates must remain");
assert.match(page, /openEditForm[\s\S]*editingProductId[\s\S]*updateAffiliateProduct\(productId, changedPayload\)/, "Edit must PATCH only changed fields");
assert.match(page, /affiliateCatalog\.imageUrl[\s\S]{0,220}?draft\.image_url|draft\.image_url \? "affiliateCatalog\.imageUrl"/, "Image URL field must remain on the editor");
assert.match(page, /affiliate-catalog-image-preview[\s\S]{0,180}?affiliateImagePreviewUrl\(draft\.image_url\)/, "Cover must preview the selected product image");
assert.match(page, /uploadAffiliateProductImage[\s\S]*uploadImage[\s\S]*type="file"/, "Disk upload must remain");
assert.match(page, /edit_product_id[\s\S]*deepLink[\s\S]*affiliateUrlInputRef/, "Deep-link focus on Affiliate URL must remain");
assert.match(page, /isPublicHttpsUrl\(draft\.affiliate_url\)[\s\S]*affiliateUrlInvalid/, "Affiliate URL must stay public HTTPS");

const catalogCss = cssFull.slice(cssFull.indexOf(".affiliate-catalog-page,"));
assert.match(catalogCss, /\.affiliate-catalog-page[\s\S]{0,80}\.affiliate-matching-page/, "Catalog and matching must keep adjacent scoped styles");
assert.match(catalogCss, /\.affiliate-catalog-upload-panel[\s\S]{0,900}input\[type="file"\]/, "Upload panel must keep a file input style");

assert.match(v10, /--pl-iq-mint|--pl-iq-label-quiet|--pl-iq-label-strong/, "v10 CSS must use Intelligence tokens");
assert.match(v10, /affiliate-catalog-page\.is-v10/, "v10 CSS must scope to the workbench mark");
assert.doesNotMatch(v10, /affiliate-catalog-kpis article/, "v10 must not restyle the retired KPI card strip");
assert.match(
  v10,
  /affiliate-catalog-toolbar \{[\s\S]{0,280}?background:\s*#fff/,
  "Toolbar must sit on white paper like Taxonomy",
);
assert.match(
  v10,
  /affiliate-catalog-form \{[\s\S]{0,240}?background:\s*(?:transparent|#fff)/,
  "Product editor must flush to the worksheet, not a mint nested card",
);
assert.match(
  v10,
  /affiliate-catalog-toolbar__icon-btn[\s\S]{0,220}?async-button__label[\s\S]{0,180}?clip:/,
  "Icon-only buttons must hide the visible label",
);
assert.match(
  v10,
  /affiliate-catalog-note[\s\S]{0,360}?(?:#f4f8f6|var\(--pl-iq-mint\))/,
  "Note must sit on mint paper, not a red banner",
);
assert.match(
  v10,
  /affiliate-catalog-note[\s\S]{0,480}?(?:inset 2px 0 0 #2a4d41|inset 2px 0 0 var\(--pl-iq-label-strong\))/,
  "Note must use a strong ink spine",
);
assert.match(
  v10,
  /affiliate-catalog-table th[\s\S]{0,200}?(?:#f4f8f6|var\(--pl-iq-mint\))/,
  "Table header must use mint paper",
);
assert.match(
  v10,
  /affiliate-catalog-table td[\s\S]{0,200}?border-top:\s*1px solid #e8eeeb|inset 0 -1px 0 #e4eee9/,
  "Catalog rows must keep hairlines",
);
assert.match(v10, /affiliate-catalog-table \{[\s\S]{0,180}?table-layout:\s*fixed/, "Table columns must use a fixed editorial layout, not equal empty gaps");
assert.match(v10, /affiliate-catalog-status-cell \{[\s\S]{0,160}?display:\s*grid/, "Status cell must stack badge over timestamp");
assert.match(v10, /affiliate-catalog-product strong \{[\s\S]{0,80}?font-size:\s*0\.8/, "Product name must read as the row title");
assert.match(v10, /toolbar__icon-btn\.is-add \{[\s\S]{0,160}?background:\s*#2a4d41/, "Add must use the strong ink fill");
assert.match(v10, /affiliate-catalog-actions \{[\s\S]{0,120}?justify-content:\s*flex-end/, "Row actions must sit on the trailing edge");
assert.doesNotMatch(
  cssFull,
  /\.affiliate-catalog-table td:nth-child\(4\) \{ display: grid/,
  "Never set display:grid on the commission <td>; it punches a white gutter between STATUS and ACTIONS",
);
assert.match(
  v10,
  /affiliate-catalog-table td:nth-child\(4\) \{[\s\S]{0,100}?display:\s*table-cell/,
  "Commission td must remain a table-cell; display:grid on the cell punches a white gutter on hover",
);
assert.match(
  v10,
  /tbody tr:hover \{[\s\S]{0,80}?background:\s*var\(--pl-iq-mint\)/,
  "Row hover must paint the whole tr so wrap-white cannot show between cells",
);
assert.match(
  v10,
  /affiliate-catalog-table \.affiliate-catalog-toolbar__icon-btn \{[\s\S]{0,140}?background:\s*transparent/,
  "Row action icons must not sit on white chips during hover",
);
assert.match(
  v10,
  /tbody tr:hover[\s\S]{0,220}?affiliate-catalog-toolbar__icon-btn \{[\s\S]{0,140}?background:\s*var\(--pl-iq-mint\)/,
  "Row hover must recolor action icons to mint so global button #fff cannot punch chips",
);

assert.match(page, /affiliate-catalog-form is-v12 is-v13 is-v14 is-v15/, "Create/edit must use the v15 Taxonomy field grid");
assert.match(page, /affiliate-catalog-form-grid[\s\S]{0,220}?is-cover/, "Cover is the first cell of one fields grid, not a separate identity band");
assert.match(page, /is-name/, "Product name spans the tracks beside the cover");
assert.doesNotMatch(page, /affiliate-catalog-form__identity/, "Identity band must not compete with the shared fields grid");
assert.doesNotMatch(page, /affiliate-catalog-form-zone/, "Link/copy zones must not use a second grid system");
assert.match(page, /affiliate-catalog-topic-chip/, "Topic mapping must be clickable chips");
assert.match(page, /aria-pressed=\{draft\.topic_ids\.includes\(topic\.id\)\}/, "Topic chips must expose pressed state");
assert.doesNotMatch(page, /<select multiple/, "Topic mapping must not use a native multi-select listbox");
assert.doesNotMatch(page, /affiliateCatalog\.affiliateUrlHint/, "Affiliate URL must not show the long essay by default");
assert.doesNotMatch(page, /affiliateCatalog\.topicHint/, "Ctrl/Cmd-click hint must leave with the listbox");
assert.doesNotMatch(page, /affiliateCatalog\.imageUrlHint/, "Image URL must not sit under a Facebook-fetch essay");
assert.match(page, /title=\{t\("affiliateCatalog\.uploadImageHint"\)\}/, "Upload tunnel/sanitizer copy stays on the cover title only");
assert.match(page, /affiliate-catalog-form-grid__offer/, "Price, commission, and availability must share one offer row");
assert.match(page, /type="file"[\s\S]{0,240}?visually-hidden|className="visually-hidden"[\s\S]{0,160}?type="file"/, "Cover must hide the native file picker chrome");
assert.match(
  v12,
  /affiliate-catalog-topic-chip\.is-on \{[\s\S]{0,180}?background:\s*(?:#2a4d41|var\(--pl-iq-mint\))/,
  "Selected topic chips must use Intelligence fill, not a Windows listbox",
);
assert.match(
  v12,
  /affiliate-catalog-form\.is-v12[\s\S]{0,900}?aspect-ratio:\s*1/,
  "Cover must be a square click target, not a dashed native file row",
);
assert.match(
  v12,
  /affiliate-catalog-cover-url input \{[\s\S]{0,80}?width:\s*100%/,
  "Cover URL field must span the same column width as the square",
);
assert.match(
  page,
  /draft\.image_url \? "affiliateCatalog\.imageUrl" : "affiliateCatalog\.pasteImageUrl"/,
  "Empty cover says paste URL; existing cover says Image URL, not Or paste",
);
assert.match(page, /aria-required=\{true\}/, "Affiliate URL must be marked required for assistive tech");
assert.match(page, /affiliateCatalog\.affiliateUrl[\s\S]{0,80}?affiliateCatalog\.required/, "Affiliate URL label must show Required");
assert.match(page, /affiliateCatalog\.productUrl[\s\S]{0,80}?affiliateCatalog\.optional/, "Product URL must read as optional so it is not confused with Affiliate URL");
const v14Start = cssFull.indexOf("/* Publishing Settings Affiliate Catalog v14");
assert.ok(v14Start >= 0, "v14 editorial form CSS block must exist");
const v14 = cssFull.slice(v14Start, v14Start + 4500);
assert.match(
  v14,
  /label > span \{[\s\S]{0,160}?text-transform:\s*uppercase/,
  "Field labels must match Taxonomy uppercase quiet marks",
);
assert.match(
  v14,
  /topic-chip\.is-on \{[\s\S]{0,140}?background:\s*#2a4d41/,
  "Selected topic chips must use strong ink so mapping is readable at a glance",
);
const v15Start = cssFull.indexOf("/* Publishing Settings Affiliate Catalog v15");
assert.ok(v15Start >= 0, "v15 Taxonomy field-grid CSS block must exist");
const v15 = cssFull.slice(v15Start, v15Start + 4000);
assert.match(
  v15,
  /form-grid \{[\s\S]{0,220}?grid-template-columns:\s*6\.75rem repeat\(3/,
  "All fields must share Taxonomy's 4-track grid so edges line up",
);
assert.match(
  v15,
  /is-cover \{[\s\S]{0,160}?grid-row:\s*span 2/,
  "Cover occupies the first column across the name and source rows",
);
assert.match(
  v15,
  /form-grid__offer \{[\s\S]{0,80}?display:\s*contents/,
  "Offer cells must sit on the same 4 tracks, not a nested unequal grid",
);
assert.match(page, /CatalogGlyph kind="link"/, "Affiliate URL must be an icon on the name row, not a third text line");
assert.match(page, /aria-label=\{t\("affiliateCatalog\.openLink"\)\}/, "Affiliate link icon must keep an accessible name");
assert.doesNotMatch(
  page,
  />\{t\("affiliateCatalog\.openLink"\)\}</,
  "Affiliate link must not print Open affiliate link under every product",
);
assert.doesNotMatch(
  page,
  /affiliate-catalog-metric[\s\S]{0,400}?price_amount/,
  "Commission column must show %, not price under a Commission header",
);
const v16Start = cssFull.indexOf("/* Publishing Settings Affiliate Catalog v16");
assert.ok(v16Start >= 0, "v16 dense catalog-row CSS block must exist");
const v16 = cssFull.slice(v16Start, v16Start + 3500);
assert.match(
  v16,
  /affiliate-catalog-table td \{[\s\S]{0,80}?padding:\s*0\.55rem/,
  "Catalog rows must use Taxonomy/Matching density, not card padding",
);
assert.match(
  v16,
  /affiliate-catalog-product > img[\s\S]{0,120}?height:\s*2\.25rem/,
  "Product thumb must be 36px so the row stays a scan line",
);
assert.match(
  v16,
  /topic-list em \{[\s\S]{0,120}?color:\s*#2a4d41/,
  "Topic chips in the list must use strong ink so they stay readable on mint",
);
assert.match(
  page,
  /\{!showForm && !coldLoading \?[\s\S]{0,900}?affiliate-catalog-table-wrap/,
  "Create/edit must hide the catalog list so the editor is the only job on screen",
);

assert.match(page, /affiliate-catalog-page is-v10[\s\S]*is-v18/, "Catalog workbench must mark is-v18 fact-strip meta");
assert.match(
  page,
  /outOfStockCount > 0 \? "affiliate-catalog-meta is-warning" : "affiliate-catalog-meta"/,
  "Out-of-stock warning tint must apply only when the count is greater than zero",
);
assert.doesNotMatch(
  page,
  /affiliate-catalog-meta is-active/,
  "Active must not keep a permanent green pill mark; facts share one quiet strip",
);
const v18Start = cssFull.indexOf("/* Publishing Settings Affiliate Catalog v18");
assert.ok(v18Start >= 0, "v18 fact-strip CSS block must exist");
const v18 = cssFull.slice(v18Start, v18Start + 3500);
assert.match(
  v18,
  /affiliate-catalog-meta \{[\s\S]{0,280}?background:\s*transparent/,
  "Meta facts must drop pill fills",
);
assert.match(
  v18,
  /affiliate-catalog-meta \{[\s\S]{0,280}?border:\s*(?:0|none)/,
  "Meta facts must drop pill borders",
);
assert.match(
  v18,
  /affiliate-catalog-meta\.is-version \{[\s\S]{0,220}?font-family:\s*ui-monospace/,
  "V1 must read as a mono schema footnote, not a metric chip",
);
assert.match(
  v18,
  /affiliate-catalog-meta\.is-warning \{[\s\S]{0,200}?color:\s*#91600c/,
  "Warning fact must use amber ink only when marked",
);
assert.match(
  skeleton,
  /pl-iq-data-skeleton__catalog-meta[\s\S]{0,200}?is-fact/,
  "Cold-load worksheet meta must mirror the fact strip, not pill chips",
);

console.log("affiliate-catalog-settings-polish: PASS");
